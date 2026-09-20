"""Threshold sweep on the school external test - analysis only, never applied.

The report quotes the 0.3-threshold result (80.93%) as evidence that the gap is
not a pure threshold problem.  This script recomputes the whole sweep from the
frozen predictions and writes ``artifacts/external_test/threshold_sweep.json``
so the number is backed by an artifact instead of a scratch calculation.

It does NOT touch the model: no retraining, no re-inference, no threshold change
to the production decision rule (which stays at 0.5).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "artifacts" / "external_test"

predictions = pd.read_csv(OUT / "external_predictions.csv")

rows = []
for threshold in [round(0.05 * i, 2) for i in range(1, 20)]:
    predicted = (predictions["malignant_probability"] >= threshold).map({True: "malignant", False: "benign"})
    tp = int(((predicted == "malignant") & (predictions["true_label"] == "malignant")).sum())
    fp = int(((predicted == "malignant") & (predictions["true_label"] == "benign")).sum())
    tn = int(((predicted == "benign") & (predictions["true_label"] == "benign")).sum())
    fn = int(((predicted == "benign") & (predictions["true_label"] == "malignant")).sum())
    n = tp + tn + fp + fn
    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    rows.append({
        "threshold": threshold,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": round(accuracy, 6),
        "precision": round(precision, 6),
        "recall_sensitivity": round(recall, 6),
        "specificity": round(specificity, 6),
        "f1": round(f1, 6),
    })

report = {
    "note": (
        "Post-hoc analysis only. The production decision threshold remains 0.5; "
        "the model was not retrained, re-tuned or modified for this sweep."
    ),
    "source": "artifacts/external_test/external_predictions.csv",
    "n": int(len(predictions)),
    "default_threshold": 0.5,
    "sweep": rows,
    "reference_points": {
        "threshold_0.5_accuracy": next(r["accuracy"] for r in rows if r["threshold"] == 0.5),
        "threshold_0.3_accuracy": next(r["accuracy"] for r in rows if r["threshold"] == 0.3),
    },
}
(OUT / "threshold_sweep.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"[sweep] n={report['n']}  written -> {OUT / 'threshold_sweep.json'}")
for row in rows:
    if row["threshold"] in (0.3, 0.4, 0.5, 0.6, 0.7):
        print(f"  t={row['threshold']:.2f} acc={row['accuracy']:.4f} prec={row['precision']:.4f} "
              f"rec={row['recall_sensitivity']:.4f} f1={row['f1']:.4f} "
              f"tp={row['tp']} fp={row['fp']} tn={row['tn']} fn={row['fn']}")
