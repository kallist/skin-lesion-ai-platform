"""Machine-learning pipeline for the skin lesion classifier.

Modules
-------
config            preprocessing / label / training contract
transforms        train & eval image transforms (serving uses the eval one)
dataset           audit, manifest building, leakage-safe splitting
model             ResNet factory + checkpoint IO
metrics           binary metrics, ROC/PR curves, ECE
train             two-stage transfer-learning training loop
evaluate          internal test evaluation + plots
evaluate_external external (school) test-set evaluation
infer             load-once predictor used by the backend
optimize_model    latency/size benchmark, dynamic quantization experiment
"""

from __future__ import annotations

__all__ = [
    "config",
    "transforms",
    "dataset",
    "model",
    "metrics",
    "train",
    "evaluate",
    "evaluate_external",
    "infer",
    "optimize_model",
]
