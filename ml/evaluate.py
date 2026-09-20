"""Final evaluation on the held-out internal test split (+ full metric report).

python ml/evaluate.py --model models/best_model.pt --split test

The internal test split is used exactly once per delivered model.  Metrics are
written to ``artifacts/metrics.json`` and the plots required by the task book
are regenerated from real predictions.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    DOCS_DIR,
    MANIFEST_DIR,
    MODELS_DIR,
    ModelMeta,
    device_info,
)
from .infer import SkinLesionPredictor
from .metrics import binary_metrics, pr_curve_points, roc_curve_points

LOGGER = logging.getLogger("ml.evaluate")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Evaluate a trained checkpoint")
    p.add_argument("--model", default=str(MODELS_DIR / "best_model.pt"))
    p.add_argument("--data", default=str(MANIFEST_DIR))
    p.add_argument("--split", default="test", choices=["train", "val", "test"])
    p.add_argument("--device", default=None)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--artifacts-dir", default=str(ARTIFACTS_DIR))
    p.add_argument("--metrics-file", default=None)
    p.add_argument(
        "--update-model-meta",
        action="store_true",
        help="write the measured metrics back into model_meta.json next to the checkpoint",
    )
    p.add_argument("--no-plots", action="store_true")
    return p.parse_args(argv)


def resolve_manifest_paths(frame: pd.DataFrame, manifest: str | Path) -> list[str]:
    """Resolve manifest ``path`` entries, which are repository-relative.

    Resolution order: the recorded path itself (absolute entries from older
    manifests still work), the manifest directory's parent tree (project root),
    then the project root directly.
    """
    manifest_dir = Path(manifest).resolve().parent
    project_root = manifest_dir.parent if manifest_dir.name == "manifests" else manifest_dir
    resolved: list[str] = []
    for entry in frame["path"].tolist():
        candidate = Path(entry)
        options = [candidate]
        if not candidate.is_absolute():
            options += [project_root / entry, manifest_dir / entry]
        for option in options:
            if option.exists():
                resolved.append(str(option))
                break
        else:
            resolved.append(str(candidate))
    return resolved


def collect_predictions(predictor: SkinLesionPredictor, frame: pd.DataFrame, batch_size: int,
                        manifest: str | Path | None = None):
    paths = resolve_manifest_paths(frame, manifest) if manifest is not None else frame["path"].tolist()
    labels = frame["label_idx"].astype(int).tolist()
    y_prob, y_pred = [], []
    for path, p_benign, p_malignant in predictor.predict_many(paths, batch_size=batch_size):
        y_prob.append(p_malignant)
        y_pred.append(1 if p_malignant >= p_benign else 0)
    return np.asarray(labels), np.asarray(y_pred), np.asarray(y_prob)


def evaluate(
    model_path: str | Path,
    manifest: str | Path,
    *,
    device: str | None = None,
    batch_size: int = 16,
    artifacts_dir: str | Path = ARTIFACTS_DIR,
    metrics_file: str | Path | None = None,
    plots: bool = True,
) -> dict:
    frame = pd.read_csv(manifest)
    if frame.empty:
        raise ValueError(f"Empty manifest: {manifest}")
    predictor = SkinLesionPredictor(model_path, device=device)
    y_true, y_pred, y_prob = collect_predictions(predictor, frame, batch_size, manifest)
    metrics = binary_metrics(y_true, y_pred, y_prob)
    metrics["split"] = Path(manifest).stem
    metrics["model_version"] = predictor.model_version
    metrics["architecture"] = predictor.architecture
    metrics["model_file"] = Path(model_path).name
    metrics["device"] = str(predictor.device)
    metrics["environment"] = device_info()
    metrics["class_names"] = list(CLASS_NAMES)

    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out = Path(metrics_file) if metrics_file else artifacts_dir / "metrics.json"
    with out.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, ensure_ascii=False, indent=2)

    per_sample = frame.copy()
    per_sample["prob_benign"] = 1.0 - y_prob
    per_sample["prob_malignant"] = y_prob
    per_sample["pred_idx"] = y_pred
    per_sample["prediction"] = [CLASS_NAMES[i] for i in y_pred]
    per_sample["correct"] = (per_sample["label_idx"].astype(int) == per_sample["pred_idx"]).astype(int)
    per_sample.drop(columns=["path"], errors="ignore").to_csv(
        artifacts_dir / f"predictions_{Path(manifest).stem}.csv", index=False, encoding="utf-8"
    )

    if plots:
        plot_confusion(metrics, artifacts_dir)
        plot_roc(y_true, y_prob, metrics, artifacts_dir)
        plot_pr(y_true, y_prob, metrics, artifacts_dir)
        plot_probability_distribution(y_true, y_prob, artifacts_dir)
        plot_per_class_metrics(metrics, artifacts_dir)

    return metrics


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------
def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def plot_confusion(metrics: dict, out_dir: Path) -> None:
    plt = _mpl()
    cm = metrics["confusion_matrix_matrix"]
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks([0, 1], labels=[f"Pred\n{CLASS_NAMES[0]}", f"Pred\n{CLASS_NAMES[1]}"])
    ax.set_yticks([0, 1], labels=[f"True\n{CLASS_NAMES[0]}", f"True\n{CLASS_NAMES[1]}"])
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                str(cm[i][j]),
                ha="center",
                va="center",
                color="white" if cm[i][j] > max(max(row) for row in cm) / 2 else "black",
                fontsize=15,
            )
    ax.set_title(
        f"Confusion matrix — {metrics.get('split', '')}\n"
        f"accuracy={metrics['accuracy']:.4f}  malignant recall={metrics['malignant_recall']:.4f}"
    )
    fig.colorbar(im, ax=ax, shrink=0.8)
    fig.tight_layout()
    fig.savefig(out_dir / "confusion_matrix.png", dpi=140)
    plt.close(fig)


def plot_roc(y_true, y_prob, metrics: dict, out_dir: Path) -> None:
    plt = _mpl()
    fpr, tpr, _ = roc_curve_points(y_true, y_prob)
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    ax.plot(fpr, tpr, lw=2, label=f"ROC (AUC = {metrics.get('roc_auc', float('nan')):.4f})")
    ax.plot([0, 1], [0, 1], "--", color="grey", lw=1)
    ax.set_xlabel("False positive rate (1 - specificity)")
    ax.set_ylabel("True positive rate (sensitivity)")
    ax.set_title(f"ROC curve — {metrics.get('split', '')}")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(out_dir / "roc_curve.png", dpi=140)
    plt.close(fig)


def plot_pr(y_true, y_prob, metrics: dict, out_dir: Path) -> None:
    plt = _mpl()
    recall, precision = pr_curve_points(y_true, y_prob)
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    ax.plot(recall, precision, lw=2, label=f"PR (AP = {metrics.get('pr_auc', float('nan')):.4f})")
    ax.set_xlabel("Recall (malignant)")
    ax.set_ylabel("Precision (malignant)")
    ax.set_title(f"Precision-Recall curve — {metrics.get('split', '')}")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(out_dir / "pr_curve.png", dpi=140)
    plt.close(fig)


def plot_probability_distribution(y_true, y_prob, out_dir: Path) -> None:
    plt = _mpl()
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    ax.hist(y_prob[np.asarray(y_true) == 0], bins=20, alpha=0.65, label="true benign")
    ax.hist(y_prob[np.asarray(y_true) == 1], bins=20, alpha=0.65, label="true malignant")
    ax.set_xlabel("predicted P(malignant)")
    ax.set_ylabel("count")
    ax.set_title("Predicted probability distribution")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "probability_distribution.png", dpi=140)
    plt.close(fig)


def plot_per_class_metrics(metrics: dict, out_dir: Path) -> None:
    plt = _mpl()
    keys = ["accuracy", "precision", "recall_sensitivity", "specificity", "f1", "balanced_accuracy"]
    values = [metrics.get(k, float("nan")) for k in keys]
    if "roc_auc" in metrics:
        keys.append("roc_auc")
        values.append(metrics["roc_auc"])
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    bars = ax.bar(keys, values, color="#2b6cb0")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.01, f"{value:.3f}", ha="center", fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.set_title(f"Metric summary — {metrics.get('split', '')}")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "metric_summary.png", dpi=140)
    plt.close(fig)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    manifest = Path(args.data) / f"{args.split}.csv"
    metrics = evaluate(
        args.model,
        manifest,
        device=args.device,
        batch_size=args.batch_size,
        artifacts_dir=args.artifacts_dir,
        metrics_file=args.metrics_file,
        plots=not args.no_plots,
    )
    print(json.dumps({k: v for k, v in metrics.items() if not isinstance(v, (dict, list))}, indent=2))
    print(f"confusion matrix: {metrics['confusion_matrix']}")
    print(f"wrote {Path(args.artifacts_dir) / 'metrics.json'}")

    if args.update_model_meta:
        meta_path = Path(args.model).parent / "model_meta.json"
        if meta_path.exists():
            meta = ModelMeta.from_json(meta_path)
            key = f"{args.split}_metrics"
            stored = {
                k: float(v)
                for k, v in metrics.items()
                if isinstance(v, (int, float)) and not isinstance(v, bool)
            }
            meta.test_metrics = stored if args.split == "test" else meta.test_metrics
            extra = dict(meta.dataset)
            extra[key] = {
                "n": metrics.get("n"),
                "accuracy": metrics.get("accuracy"),
                "roc_auc": metrics.get("roc_auc"),
                "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "model_file": metrics.get("model_file"),
            }
            meta.dataset = extra
            if args.split == "test":
                meta.notes = (
                    "test metrics measured once on the held-out internal test split; "
                    "the test split was never used for model selection or tuning."
                )
            meta.to_json(meta_path)
            print(f"updated {meta_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
