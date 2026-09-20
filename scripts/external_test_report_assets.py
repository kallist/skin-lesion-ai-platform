"""Generate the assets referenced by the archived external test report.

* copies the three evaluator plots into docs/archive/project-origin/assets/external/ (so the
  Markdown report renders them) with descriptive English captions baked in
* writes artifacts/external_test/metric_comparison.json (internal vs external)

Only reads existing results - it never touches the model or the test data.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
EXT = REPO / "artifacts" / "external_test"
ASSETS = REPO / "docs" / "final" / "assets" / "external"
ASSETS.mkdir(parents=True, exist_ok=True)

metrics = json.loads((EXT / "external_metrics.json").read_text(encoding="utf-8"))
internal = json.loads((REPO / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
verification = json.loads((EXT / "verification.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- comparison json
keys = [
    "n", "accuracy", "precision", "recall_sensitivity", "specificity", "npv", "f1",
    "balanced_accuracy", "roc_auc", "pr_auc", "brier_score", "ece_10bin",
]
comparison = {
    "internal_test": {k: internal.get(k) for k in keys},
    "school_external_test": {k: metrics.get(k) for k in keys},
    "delta_external_minus_internal": {
        k: (metrics.get(k) - internal.get(k))
        for k in keys
        if isinstance(metrics.get(k), (int, float)) and isinstance(internal.get(k), (int, float))
    },
    "confusion_matrix": {
        "internal": internal["confusion_matrix"],
        "external": metrics["confusion_matrix"],
    },
    "targets": {
        "task_book_accuracy_ge_0.90": {
            "internal_test": bool(internal["accuracy"] >= 0.90),
            "school_external_test": bool(metrics["accuracy"] >= 0.90),
        }
    },
    "model_version": metrics["model_version"],
    "independent_verification": verification["verdict"],
}
(EXT / "metric_comparison.json").write_text(
    json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"[assets] metric_comparison.json -> {EXT / 'metric_comparison.json'}")

# ---------------------------------------------------------------- figure 1: confusion matrix
cm = metrics["confusion_matrix_matrix"]
fig, ax = plt.subplots(figsize=(5.6, 4.8))
ax.imshow(cm, cmap="Blues")
ax.set_xticks([0, 1], labels=["Pred benign", "Pred malignant"])
ax.set_yticks([0, 1], labels=["True benign", "True malignant"])
for i in range(2):
    for j in range(2):
        ax.text(j, i, str(cm[i][j]), ha="center", va="center", fontsize=15)
ax.set_title(
    f"School external test (n={metrics['n']})\n"
    f"accuracy={metrics['accuracy']:.4f}  recall={metrics['recall_sensitivity']:.4f}  "
    f"specificity={metrics['specificity']:.4f}"
)
fig.tight_layout()
fig.savefig(ASSETS / "confusion_matrix.png", dpi=150)
plt.close(fig)
print(f"[assets] confusion_matrix.png -> {ASSETS / 'confusion_matrix.png'}")

# ---------------------------------------------------------------- figure 2: metric bars
pairs = [
    ("Accuracy", internal["accuracy"], metrics["accuracy"]),
    ("Precision", internal["precision"], metrics["precision"]),
    ("Recall", internal["recall_sensitivity"], metrics["recall_sensitivity"]),
    ("Specificity", internal["specificity"], metrics["specificity"]),
    ("F1", internal["f1"], metrics["f1"]),
    ("ROC-AUC", internal["roc_auc"], metrics["roc_auc"]),
]
labels = [p[0] for p in pairs]
internal_values = [p[1] for p in pairs]
external_values = [p[2] for p in pairs]
x = range(len(labels))
fig, ax = plt.subplots(figsize=(7.6, 4.4))
bars_internal = ax.bar([i - 0.2 for i in x], internal_values, width=0.4,
                       label=f"Internal test (n={int(internal['n'])})")
bars_external = ax.bar([i + 0.2 for i in x], external_values, width=0.4,
                       label=f"School external (n={metrics['n']})")
# value labels on top of every bar so the two headline numbers (78.54 / 65.49)
# can be read straight off the figure
for container in (bars_internal, bars_external):
    ax.bar_label(container, labels=[f"{value * 100:.2f}" for value in container.datavalues],
                 fmt="%s", fontsize=7.5, padding=2)
ax.axhline(0.90, color="crimson", ls="--", lw=1.2, label="task-book target 90%")
ax.set_xticks(list(x), labels=labels)
ax.set_ylim(0, 1.15)
ax.set_ylabel("value")
ax.set_title("Internal vs school external test")
ax.legend(fontsize=8, loc="lower right")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(ASSETS / "internal_vs_external.png", dpi=150)
plt.close(fig)
print(f"[assets] internal_vs_external.png -> {ASSETS / 'internal_vs_external.png'}")

# ---------------------------------------------------------------- figure 3: score distribution
frame = pd.read_csv(EXT / "external_predictions.csv")
malignant = frame[frame["true_label"] == "malignant"]["malignant_probability"]
benign = frame[frame["true_label"] == "benign"]["malignant_probability"]
fig, ax = plt.subplots(figsize=(7.6, 4.2))
bins = [i / 20 for i in range(21)]
counts_b, _, _ = ax.hist(benign, bins=bins, alpha=0.65, label=f"true benign (n={len(benign)})", color="#2e7d32")
counts_m, _, _ = ax.hist(malignant, bins=bins, alpha=0.65, label=f"true malignant (n={len(malignant)})", color="#c62828")
# annotate the first bin: it is the overlap region behind the missed malignancies
if counts_m[0]:
    ax.annotate(
        f"{int(counts_m[0])} malignant images\nwith P(malignant) <= 0.05",
        xy=(0.025, counts_m[0]), xytext=(0.12, counts_m[0] + 12),
        fontsize=8.5, color="#8e0000",
        arrowprops=dict(arrowstyle="-|>", color="#8e0000", lw=1.0),
    )
if counts_b[0]:
    ax.annotate(
        f"{int(counts_b[0])} benign images\nwith P(malignant) <= 0.05",
        xy=(0.025, counts_b[0]), xytext=(0.30, counts_b[0] - 60),
        fontsize=8.5, color="#1b5e20",
        arrowprops=dict(arrowstyle="-|>", color="#1b5e20", lw=1.0),
    )
ax.axvline(0.5, color="black", ls="--", lw=1.2, label="decision threshold 0.5")
ax.set_xlabel("predicted P(malignant)")
ax.set_ylabel("number of images")
ax.set_title("School external test — predicted probability distribution")
ax.legend(fontsize=8)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
fig.savefig(ASSETS / "score_distribution.png", dpi=150)
plt.close(fig)
print(f"[assets] score_distribution.png -> {ASSETS / 'score_distribution.png'}")

# ---------------------------------------------------------------- copy evaluator plots
for name in ("roc_curve.png", "pr_curve.png"):
    shutil.copy2(EXT / name, ASSETS / name)
    print(f"[assets] {name} copied")
