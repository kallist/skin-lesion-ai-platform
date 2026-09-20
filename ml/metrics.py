"""Binary-classification metrics used by every evaluation script.

All metrics are computed from real predictions; nothing here is hard-coded.
Positive class = malignant (index 1), because a missed malignancy is the
costly error in this domain.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np

from .config import MALIGNANT_IDX


def confusion(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def binary_metrics(
    y_true: Sequence[int],
    y_pred: Sequence[int],
    y_prob: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Compute the full metric set for the malignant-positive task."""
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    n = len(y_true)
    if n == 0:
        return {"n": 0}
    cm = confusion(y_true, y_pred)
    tp, tn, fp, fn = cm["tp"], cm["tn"], cm["fp"], cm["fn"]

    accuracy = (tp + tn) / n
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    specificity = tn / (tn + fp) if (tn + fp) else 0.0
    npv = tn / (tn + fn) if (tn + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    balanced_acc = (recall + specificity) / 2

    metrics: dict[str, Any] = {
        "n": int(n),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall_sensitivity": float(recall),
        "specificity": float(specificity),
        "npv": float(npv),
        "f1": float(f1),
        "balanced_accuracy": float(balanced_acc),
        "malignant_recall": float(recall),
        "confusion_matrix": cm,
        "confusion_matrix_matrix": [[tn, fp], [fn, tp]],
        "positive_class": "malignant",
    }

    if y_prob is not None:
        y_prob = np.asarray(y_prob, dtype=float)
        if y_prob.size == n:
            metrics.update(_ranking_metrics(y_true, y_prob))
            metrics["brier_score"] = float(np.mean((y_prob - y_true) ** 2))
            metrics["ece_10bin"] = float(expected_calibration_error(y_true, y_prob, bins=10))
    return metrics


def _ranking_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    roc_auc = _auc(y_true, y_prob)
    pr_auc = _average_precision(y_true, y_prob)
    return {"roc_auc": float(roc_auc), "pr_auc": float(pr_auc)}


def _auc(y_true: np.ndarray, y_score: np.ndarray) -> float:
    """Rank-based ROC-AUC with tie handling (Mann-Whitney U)."""
    pos = y_score[y_true == 1]
    neg = y_score[y_true == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    order = np.argsort(y_score, kind="mergesort")
    ranks = np.empty(len(y_score), dtype=float)
    sorted_scores = y_score[order]
    i = 0
    while i < len(sorted_scores):
        j = i
        while j + 1 < len(sorted_scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks[order[i : j + 1]] = avg_rank
        i = j + 1
    n_pos, n_neg = pos.size, neg.size
    sum_pos_ranks = ranks[y_true == 1].sum()
    return float((sum_pos_ranks - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def _average_precision(y_true: np.ndarray, y_score: np.ndarray) -> float:
    if y_true.sum() == 0:
        return float("nan")
    order = np.argsort(-y_score, kind="mergesort")
    y_sorted = y_true[order]
    tp = np.cumsum(y_sorted)
    precision = tp / (np.arange(len(y_sorted)) + 1)
    recall = tp / y_true.sum()
    # step-wise AP (sklearn's average_precision_score definition)
    ap = 0.0
    prev_recall = 0.0
    for p, r in zip(precision, recall):
        if r > prev_recall:
            ap += p * (r - prev_recall)
            prev_recall = r
    return float(ap)


def expected_calibration_error(y_true: np.ndarray, y_prob: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    n = len(y_true)
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (y_prob > lo) & (y_prob <= hi) if i > 0 else (y_prob >= lo) & (y_prob <= hi)
        if not mask.any():
            continue
        conf = y_prob[mask].mean()
        acc = y_true[mask].mean()
        ece += (mask.sum() / n) * abs(acc - conf)
    return float(ece)


def roc_curve_points(y_true: Sequence[int], y_prob: Sequence[float], max_points: int = 400):
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    thresholds = np.unique(np.concatenate(([0.0, 1.0], y_prob)))
    thresholds = np.sort(thresholds)[::-1]
    tpr, fpr = [], []
    for thr in thresholds:
        pred = (y_prob >= thr).astype(int)
        cm = confusion(y_true, pred)
        tp, tn, fp, fn = cm["tp"], cm["tn"], cm["fp"], cm["fn"]
        tpr.append(tp / (tp + fn) if (tp + fn) else 0.0)
        fpr.append(fp / (fp + tn) if (fp + tn) else 0.0)
    if len(thresholds) > max_points:  # thin out for plotting
        idx = np.linspace(0, len(thresholds) - 1, max_points).astype(int)
        thresholds, tpr, fpr = thresholds[idx], np.asarray(tpr)[idx], np.asarray(fpr)[idx]
    return np.asarray(fpr), np.asarray(tpr), np.asarray(thresholds)


def pr_curve_points(y_true: Sequence[int], y_prob: Sequence[float], max_points: int = 400):
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_prob, dtype=float)
    order = np.argsort(-y_prob, kind="mergesort")
    y_sorted = y_true[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    precision = tp / np.maximum(tp + fp, 1)
    recall = tp / max(int(y_true.sum()), 1)
    if len(recall) > max_points:
        idx = np.linspace(0, len(recall) - 1, max_points).astype(int)
        precision, recall = precision[idx], recall[idx]
    return recall, precision
