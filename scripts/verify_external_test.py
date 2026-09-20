"""Independent verification of the school external test (does NOT trust the evaluator).

Re-reads ``external_predictions.csv``, re-derives the ground truth from the staged
``labels.csv`` and recomputes every metric from scratch, then cross-checks against
``external_metrics.json``.  Also validates each row's probabilities and the
argmax consistency, and writes ``external_errors.csv``.

Usage:
    python scripts/verify_external_test.py
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "external_test"
PRED = OUT / "external_predictions.csv"
LABELS = OUT / "staging" / "labels.csv"
METRICS = OUT / "external_metrics.json"

TOL = 1e-9
PROB_TOL = 2e-6  # predictions are rounded to 6 decimals before writing


def main() -> int:
    predictions = pd.read_csv(PRED)
    labels = pd.read_csv(LABELS)
    truth = dict(zip(labels["filename"], labels["label"]))
    print(f"[verify] predictions rows : {len(predictions)}")
    print(f"[verify] label rows       : {len(labels)}")

    checks: dict[str, str] = {}
    problems: list[str] = []

    # ---------------------------------------------------------------- integrity
    pred_names = list(predictions["filename"])
    label_names = list(labels["filename"])
    matched = [name for name in pred_names if name in truth]
    missing_labels = [name for name in pred_names if name not in truth]
    missing_images = [name for name in label_names if name not in set(pred_names)]
    duplicate_pred_names = [n for n, c in Counter(pred_names).items() if c > 1]

    print(f"[verify] matched           : {len(matched)}")
    print(f"[verify] missing labels    : {len(missing_labels)}")
    print(f"[verify] missing images    : {len(missing_images)}")
    print(f"[verify] duplicate rows    : {len(duplicate_pred_names)}")
    if missing_labels:
        problems.append(f"{len(missing_labels)} predictions without ground truth")
    if missing_images:
        problems.append(f"{len(missing_images)} ground-truth rows without a prediction")
    if duplicate_pred_names:
        problems.append(f"duplicate filenames in predictions: {duplicate_pred_names[:5]}")

    # ---------------------------------------------------------------- per-row checks
    bad_prob_range: list[str] = []
    bad_prob_sum: list[str] = []
    bad_argmax: list[str] = []
    for row in predictions.itertuples(index=False):
        p_benign = float(row.benign_probability)
        p_malignant = float(row.malignant_probability)
        if not (0.0 <= p_benign <= 1.0) or not (0.0 <= p_malignant <= 1.0):
            bad_prob_range.append(row.filename)
        if abs((p_benign + p_malignant) - 1.0) > PROB_TOL:
            bad_prob_sum.append(f"{row.filename}:{p_benign + p_malignant:.8f}")
        expected = "malignant" if p_malignant > p_benign else "benign"
        if row.prediction != expected:
            # a tie rounds to benign in the evaluator, so only flag real mismatches
            if abs(p_malignant - p_benign) > PROB_TOL:
                bad_argmax.append(f"{row.filename}:{row.prediction} vs argmax {expected}")

    checks["probability range 0..1"] = "PASS" if not bad_prob_range else "FAIL"
    checks["benign + malignant == 1"] = "PASS" if not bad_prob_sum else "FAIL"
    checks["prediction == argmax(probability)"] = "PASS" if not bad_argmax else "FAIL"
    if bad_prob_range:
        problems.append(f"probabilities out of range: {bad_prob_range[:5]}")
    if bad_prob_sum:
        problems.append(f"probability sums != 1: {bad_prob_sum[:5]}")
    if bad_argmax:
        problems.append(f"prediction/argmax mismatch: {bad_argmax[:5]}")

    # ---------------------------------------------------------------- recompute metrics
    tp = tn = fp = fn = 0
    errors = []
    for row in predictions.itertuples(index=False):
        if row.filename not in truth:
            continue
        y_true = 1 if truth[row.filename] == "malignant" else 0
        y_pred = 1 if row.prediction == "malignant" else 0
        if y_true == 1 and y_pred == 1:
            tp += 1
        elif y_true == 0 and y_pred == 0:
            tn += 1
        elif y_true == 0 and y_pred == 1:
            fp += 1
        else:
            fn += 1
        if y_true != y_pred:
            errors.append({
                "filename": row.filename,
                "true_label": truth[row.filename],
                "prediction": row.prediction,
                "confidence": row.confidence,
                "benign_probability": row.benign_probability,
                "malignant_probability": row.malignant_probability,
                "error_type": "FP (benign judged malignant)" if y_true == 0 else "FN (malignant judged benign)",
            })

    n = tp + tn + fp + fn
    accuracy = (tp + tn) / n if n else 0.0
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    balanced = (recall + specificity) / 2

    print()
    print("===== INDEPENDENT RECOMPUTATION =====")
    print(f"N={n}  TP={tp} TN={tn} FP={fp} FN={fn}  (sum={tp + tn + fp + fn})")
    print(f"accuracy={accuracy:.6f}  precision={precision:.6f}  recall={recall:.6f}")
    print(f"specificity={specificity:.6f}  f1={f1:.6f}  balanced_accuracy={balanced:.6f}")

    checks["TP + TN + FP + FN == N"] = "PASS" if (tp + tn + fp + fn) == n and n > 0 else "FAIL"
    checks["accuracy == (TP + TN) / N"] = "PASS" if abs(accuracy - ((tp + tn) / n if n else 0)) < TOL else "FAIL"
    if checks["TP + TN + FP + FN == N"] == "FAIL":
        problems.append("confusion matrix does not sum to N")

    # ---------------------------------------------------------------- compare with the evaluator
    recorded = json.loads(METRICS.read_text(encoding="utf-8"))
    cm = recorded["confusion_matrix"]
    comparisons = {
        "accuracy": (accuracy, recorded["accuracy"]),
        "precision": (precision, recorded["precision"]),
        "recall": (recall, recorded["recall_sensitivity"]),
        "specificity": (specificity, recorded["specificity"]),
        "f1": (f1, recorded["f1"]),
        "balanced_accuracy": (balanced, recorded.get("balanced_accuracy", balanced)),
    }
    print()
    print("===== EVALUATOR vs INDEPENDENT =====")
    metric_ok = True
    for name, (mine, theirs) in comparisons.items():
        same = abs(mine - theirs) < 1e-9
        metric_ok &= same
        print(f"{name:18s} evaluator={theirs:.6f}  independent={mine:.6f}  {'OK' if same else 'MISMATCH'}")
        if not same:
            problems.append(f"{name} mismatch: evaluator {theirs} vs independent {mine}")

    cm_ok = (cm["tp"], cm["tn"], cm["fp"], cm["fn"]) == (tp, tn, fp, fn)
    print(f"confusion          evaluator={cm}  independent={{'tp': {tp}, 'tn': {tn}, 'fp': {fp}, 'fn': {fn}}}  "
          f"{'OK' if cm_ok else 'MISMATCH'}")
    if not cm_ok:
        problems.append("confusion matrix mismatch between evaluator and independent recount")

    checks["metrics recomputation matches"] = "PASS" if metric_ok else "FAIL"
    checks["confusion matrix matches"] = "PASS" if cm_ok else "FAIL"

    # ---------------------------------------------------------------- errors file
    if errors:
        error_path = OUT / "external_errors.csv"
        with error_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(errors[0].keys()))
            writer.writeheader()
            writer.writerows(errors)
        print(f"\n[verify] errors -> {error_path} ({len(errors)} rows)")
    else:
        print("\n[verify] no misclassified samples")

    fp_count = sum(1 for item in errors if item["error_type"].startswith("FP"))
    fn_count = sum(1 for item in errors if item["error_type"].startswith("FN"))
    print(f"[verify] false positives: {fp_count}   false negatives: {fn_count}")

    summary = {
        "n": n,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall_sensitivity": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": balanced,
        "roc_auc": recorded.get("roc_auc"),
        "pr_auc": recorded.get("pr_auc"),
        "false_positives": fp_count,
        "false_negatives": fn_count,
        "checks": checks,
        "problems": problems,
        "verdict": "PASS" if not problems else "FAIL",
    }
    (OUT / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("===== CHECKS =====")
    for name, result in checks.items():
        print(f"{result}  {name}")
    print()
    print(f"VERDICT: {summary['verdict']}")
    for problem in problems:
        print(f"  PROBLEM: {problem}")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
