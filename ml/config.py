"""Central ML configuration.

This module is the single source of truth for the *preprocessing contract*
shared by training, evaluation, external-test evaluation and production
serving.  Changing anything here invalidates existing checkpoints, so the
values are also persisted into ``models/model_meta.json`` at training time and
verified at load time by the backend model service.
"""

from __future__ import annotations

import json
import os
import platform
import random
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
MANIFEST_DIR = DATA_DIR / "manifests"
EXTERNAL_TEST_DIR = DATA_DIR / "external_test"
MODELS_DIR = PROJECT_ROOT / "models"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
DOCS_DIR = PROJECT_ROOT / "docs"
# generated reports live inside the categorised docs tree
DATASET_REPORT_PATH = DOCS_DIR / "ml" / "DATASET_REPORT.md"

# --------------------------------------------------------------------------
# Label contract
# --------------------------------------------------------------------------
# Index order is fixed: 0 = benign, 1 = malignant.
CLASS_NAMES: tuple[str, str] = ("benign", "malignant")
CLASS_TO_IDX: dict[str, int] = {name: idx for idx, name in enumerate(CLASS_NAMES)}
IDX_TO_CLASS: dict[int, str] = {idx: name for name, idx in CLASS_TO_IDX.items()}
MALIGNANT_IDX = CLASS_TO_IDX["malignant"]

# Directory names in the raw dataset that map onto the label contract.
# The raw dataset ships with explicit ``benign`` / ``malignant`` folders, so
# the mapping is documentation, not inference.
RAW_CLASS_DIRS: dict[str, str] = {"benign": "benign", "malignant": "malignant"}

# --------------------------------------------------------------------------
# Image / preprocessing contract
# --------------------------------------------------------------------------
IMAGE_SIZE = 224
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

# --------------------------------------------------------------------------
# Training defaults
# --------------------------------------------------------------------------
SEED = 42
DEFAULT_MODEL = "resnet50"
DEFAULT_EPOCHS = 18
DEFAULT_BATCH_SIZE = 32
DEFAULT_LR_HEAD = 1e-3
DEFAULT_LR_FINETUNE = 1e-4
DEFAULT_WEIGHT_DECAY = 1e-4
DEFAULT_NUM_WORKERS = 4
DEFAULT_PATIENCE = 5
DEFAULT_VAL_FRACTION = 0.15
DEFAULT_TEST_FRACTION = 0.15
DEFAULT_HEAD_EPOCHS = 3

# Project version recorded inside every checkpoint.
PROJECT_VERSION = "1.0.0"


def set_global_seed(seed: int = SEED) -> None:
    """Seed python / numpy / torch RNGs for reproducibility."""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    # Windows consoles default to a legacy code page (GBK/cp1252); force UTF-8
    # so progress output never crashes the training run.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - non-reconfigurable streams
            pass
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:  # pragma: no cover - numpy always present in practice
        pass
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except Exception:  # pragma: no cover
        pass


def device_info() -> dict[str, Any]:
    """Return a JSON-serialisable description of the compute device."""
    info: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "device": "cpu",
    }
    try:
        import torch

        info["torch"] = torch.__version__
        if torch.cuda.is_available():
            info["device"] = "cuda"
            info["gpu"] = torch.cuda.get_device_name(0)
            info["cuda"] = torch.version.cuda
            info["gpu_memory_mb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 * 1024)
            )
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["device"] = "mps"
    except Exception:  # pragma: no cover
        pass
    return info


@dataclass
class ModelMeta:
    """Metadata persisted next to the trained weights."""

    model_version: str = PROJECT_VERSION
    architecture: str = DEFAULT_MODEL
    num_classes: int = 2
    class_names: tuple[str, str] = CLASS_NAMES
    class_mapping: dict[str, int] = field(default_factory=lambda: dict(CLASS_TO_IDX))
    input_size: int = IMAGE_SIZE
    normalization: dict[str, tuple[float, ...]] = field(
        default_factory=lambda: {"mean": IMAGENET_MEAN, "std": IMAGENET_STD}
    )
    seed: int = SEED
    trained_at: str = ""
    training_seconds: float = 0.0
    epochs_trained: int = 0
    best_epoch: int = 0
    best_val_metric: dict[str, float] = field(default_factory=dict)
    test_metrics: dict[str, float] = field(default_factory=dict)
    dataset: dict[str, Any] = field(default_factory=dict)
    hyperparameters: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    calibration: str = "NOT IMPLEMENTED"
    pretrained: str = "imagenet"
    notes: str = ""

    def to_json(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self)
        payload["class_names"] = list(self.class_names)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, path: str | Path) -> "ModelMeta":
        with Path(path).open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        payload["class_names"] = tuple(payload.get("class_names", CLASS_NAMES))
        payload["normalization"] = {
            "mean": tuple(payload.get("normalization", {}).get("mean", IMAGENET_MEAN)),
            "std": tuple(payload.get("normalization", {}).get("std", IMAGENET_STD)),
        }
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in known})


# Disclaimer strings used by the API and the frontend so that wording stays
# identical across the stack.
DISCLAIMER_SHORT = "AI辅助检测结果，仅供参考，不构成医学诊断。"
DISCLAIMER_LONG = (
    "本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，不能替代专业医生诊断。"
    "模型置信度并不等同于真实临床患病概率。"
)
