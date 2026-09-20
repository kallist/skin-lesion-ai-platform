"""External (school) test-set evaluation — the "tomorrow" entry point.

CASE A — images only (no ground-truth labels):

    python ml/evaluate_external.py --input data/external_test --model models/best_model.pt

    -> data/external_test/external_predictions.csv
       columns: filename,prediction,confidence,benign_probability,malignant_probability

CASE B — images + ``labels.csv`` (``filename,label``):

    python ml/evaluate_external.py --input data/external_test \
        --labels data/external_test/labels.csv --model models/best_model.pt

    -> external_predictions.csv (same columns, plus ``true_label``/``correct``)
    -> external_metrics.json (accuracy / precision / recall / specificity / f1 /
       roc_auc / pr_auc / confusion matrix)
    -> confusion_matrix.png, roc_curve.png, pr_curve.png in the output dir

This script NEVER trains or tunes anything.  The external set is used for
acceptance only, exactly as required by the task book.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from pathlib import Path

import pandas as pd
from PIL import Image

from .config import EXTERNAL_TEST_DIR, MODELS_DIR
from .infer import SkinLesionPredictor
from .metrics import binary_metrics, pr_curve_points, roc_curve_points

LOGGER = logging.getLogger("ml.evaluate_external")
SUPPORTED = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
LABEL_ALIASES = {
    "benign": 0,
    "b": 0,
    "0": 0,
    "良性": 0,
    "normal": 0,
    "nevus": 0,
    "malignant": 1,
    "m": 1,
    "1": 1,
    "恶性": 1,
    "melanoma": 1,
    "cancer": 1,
}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Evaluate the trained model on the external test set")
    p.add_argument("--input", default=str(EXTERNAL_TEST_DIR), help="folder with test images")
    p.add_argument("--labels", default=None, help="optional labels.csv (filename,label)")
    p.add_argument("--model", default=str(MODELS_DIR / "best_model.pt"))
    p.add_argument("--output", default=None, help="output dir (default: --input)")
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--device", default=None)
    p.add_argument("--recursive", action="store_true", help="also scan sub-folders")
    return p.parse_args(argv)


def find_images(folder: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        p
        for p in sorted(folder.glob(pattern))
        if p.is_file() and p.suffix.lower() in SUPPORTED
    ]
    return files


def normalise_label(value) -> int | None:
    key = str(value).strip().lower()
    if key in LABEL_ALIASES:
        return LABEL_ALIASES[key]
    # tolerate labels like "malignant_1" / "1.0"
    match = re.search(r"(benign|malignant|\d)", key)
    if match:
        return LABEL_ALIASES.get(match.group(1))
    return None


def load_labels(path: Path) -> dict[str, int]:
    frame = pd.read_csv(path)
    cols = {c.lower().strip(): c for c in frame.columns}
    name_col = next((cols[c] for c in ("filename", "file", "image", "name", "image_name") if c in cols), None)
    label_col = next((cols[c] for c in ("label", "class", "target", "category", "diagnosis") if c in cols), None)
    if name_col is None or label_col is None:
        raise ValueError(
            f"labels.csv must contain a filename column and a label column; found {list(frame.columns)}"
        )
    out: dict[str, int] = {}
    unknown = []
    for _, row in frame.iterrows():
        label = normalise_label(row[label_col])
        if label is None:
            unknown.append(str(row[label_col]))
            continue
        out[Path(str(row[name_col]).strip()).name] = label
    if unknown:
        LOGGER.warning("ignored %d unparseable label values: %s", len(unknown), sorted(set(unknown))[:5])
    return out


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    in_dir = Path(args.input)
    if not in_dir.is_dir():
        raise SystemExit(f"Input folder not found: {in_dir}")
    images = find_images(in_dir, args.recursive)
    if not images:
        raise SystemExit(
            f"No images found in {in_dir}. Put the school test images there and re-run.\n"
            f"Supported extensions: {', '.join(sorted(SUPPORTED))}"
        )
    out_dir = Path(args.output) if args.output else in_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[external] {len(images)} images from {in_dir}")
    predictor = SkinLesionPredictor(args.model, device=args.device)
    print(f"[external] model={predictor.architecture} version={predictor.model_version} device={predictor.device}")

    labels = load_labels(Path(args.labels)) if args.labels else {}
    if args.labels:
        print(f"[external] {len(labels)} ground-truth labels loaded")

    rows = []
    for path, p_benign, p_malignant in predictor.predict_many(images, batch_size=args.batch_size):
        prediction = "malignant" if p_malignant >= p_benign else "benign"
        confidence = p_malignant if prediction == "malignant" else p_benign
        row = {
            "filename": Path(path).name,
            "prediction": prediction,
            "confidence": round(float(confidence), 6),
            "benign_probability": round(float(p_benign), 6),
            "malignant_probability": round(float(p_malignant), 6),
        }
        if labels:
            truth = labels.get(Path(path).name)
            row["true_label"] = None if truth is None else ("malignant" if truth else "benign")
            row["correct"] = None if truth is None else int(truth == (1 if prediction == "malignant" else 0))
        rows.append(row)

    df = pd.DataFrame(rows)
    pred_csv = out_dir / "external_predictions.csv"
    df.to_csv(pred_csv, index=False, encoding="utf-8-sig")
    print(f"[external] predictions -> {pred_csv}")

    if labels:
        labelled = [r for r in rows if r.get("true_label") is not None]
        if not labelled:
            print("[external] WARNING: labels.csv provided but no filename matched the images.")
            return 0
        y_true = [1 if r["true_label"] == "malignant" else 0 for r in labelled]
        y_pred = [1 if r["prediction"] == "malignant" else 0 for r in labelled]
        y_prob = [float(r["malignant_probability"]) for r in labelled]
        metrics = binary_metrics(y_true, y_pred, y_prob)
        metrics.update(
            {
                "source": "external_test",
                "model_version": predictor.model_version,
                "architecture": predictor.architecture,
                "n_images": len(images),
                "n_labelled": len(labelled),
                "unmatched": len(images) - len(labelled),
            }
        )
        (out_dir / "external_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _plots(y_true, y_prob, metrics, out_dir)

        print("\n===== EXTERNAL TEST METRICS (real, no tuning) =====")
        print(f"n={metrics['n']}  accuracy={metrics['accuracy']:.4f}")
        print(f"precision={metrics['precision']:.4f}  recall={metrics['recall_sensitivity']:.4f}")
        print(f"specificity={metrics['specificity']:.4f}  f1={metrics['f1']:.4f}")
        print(f"roc_auc={metrics.get('roc_auc')}  pr_auc={metrics.get('pr_auc')}")
        print(f"confusion={metrics['confusion_matrix']}")
        print(f"TARGET >=90%: {'ACHIEVED' if metrics['accuracy'] >= 0.90 else 'NOT ACHIEVED'}")
        print(f"[external] metrics -> {out_dir / 'external_metrics.json'}")
    else:
        print(
            "[external] no labels supplied — prediction CSV only.\n"
            "[external] if the school provides labels.csv, re-run with --labels <path>"
        )
    return 0


def _plots(y_true, y_prob, metrics: dict, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cm = metrics["confusion_matrix_matrix"]
    fig, ax = plt.subplots(figsize=(5, 4.4))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1], labels=["Pred benign", "Pred malignant"])
    ax.set_yticks([0, 1], labels=["True benign", "True malignant"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(cm[i][j]), ha="center", va="center", fontsize=14)
    ax.set_title(f"External test — accuracy={metrics['accuracy']:.4f}")
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.png", dpi=140)
    plt.close(fig)

    fpr, tpr, _ = roc_curve_points(y_true, y_prob)
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.plot(fpr, tpr, lw=2, label=f"AUC={metrics.get('roc_auc', float('nan')):.4f}")
    ax.plot([0, 1], [0, 1], "--", color="grey")
    ax.set_xlabel("1 - specificity")
    ax.set_ylabel("sensitivity")
    ax.set_title("External test ROC")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "roc_curve.png", dpi=140)
    plt.close(fig)

    recall, precision = pr_curve_points(y_true, y_prob)
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.plot(recall, precision, lw=2, label=f"AP={metrics.get('pr_auc', float('nan')):.4f}")
    ax.set_xlabel("recall")
    ax.set_ylabel("precision")
    ax.set_title("External test PR curve")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "pr_curve.png", dpi=140)
    plt.close(fig)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
