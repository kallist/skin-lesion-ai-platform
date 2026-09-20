"""Model factory + checkpoint (de)serialisation.

The backend model service imports :func:`build_model` and
:func:`load_checkpoint` so training and serving always share one architecture
definition.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .config import CLASS_NAMES, CLASS_TO_IDX, DEFAULT_MODEL

LOGGER = logging.getLogger("ml.model")

SUPPORTED_ARCHITECTURES = ("resnet50", "resnet101", "resnet18", "resnet34")


def build_model(
    architecture: str = DEFAULT_MODEL,
    num_classes: int = 2,
    *,
    pretrained: bool = True,
):
    """Create a torchvision ResNet with a fresh ``num_classes`` head."""
    import torch
    import torch.nn as nn
    from torchvision import models

    architecture = architecture.lower()
    if architecture not in SUPPORTED_ARCHITECTURES:
        raise ValueError(
            f"Unsupported architecture '{architecture}'. "
            f"Supported: {', '.join(SUPPORTED_ARCHITECTURES)}"
        )

    weights = None
    if pretrained:
        weight_enum = {
            "resnet18": models.ResNet18_Weights.IMAGENET1K_V1,
            "resnet34": models.ResNet34_Weights.IMAGENET1K_V1,
            "resnet50": models.ResNet50_Weights.IMAGENET1K_V2,
            "resnet101": models.ResNet101_Weights.IMAGENET1K_V2,
        }[architecture]
        weights = weight_enum

    model = getattr(models, architecture)(weights=weights)
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, num_classes)
    return model


def count_parameters(model) -> dict[str, int]:
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return {"total": int(total), "trainable": int(trainable)}


def freeze_backbone(model) -> None:
    for name, param in model.named_parameters():
        param.requires_grad = name.startswith("fc.")


def unfreeze_backbone(model) -> None:
    for param in model.parameters():
        param.requires_grad = True


def save_checkpoint(
    path: str | Path,
    model,
    meta,
    *,
    optimizer_state: dict[str, Any] | None = None,
    epoch: int | None = None,
) -> None:
    """Persist weights + metadata + class mapping in one file."""
    import torch

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "state_dict": model.state_dict(),
        "architecture": meta.architecture,
        "num_classes": meta.num_classes,
        "class_mapping": dict(CLASS_TO_IDX),
        "class_names": list(CLASS_NAMES),
        "input_size": meta.input_size,
        "normalization": meta.normalization,
        "model_version": meta.model_version,
        "seed": meta.seed,
        "trained_at": meta.trained_at,
        "best_epoch": meta.best_epoch,
        "best_val_metric": meta.best_val_metric,
        "meta": json.loads(json.dumps(meta.__dict__, default=str)),
    }
    if optimizer_state is not None:
        payload["optimizer_state_dict"] = optimizer_state
    if epoch is not None:
        payload["epoch"] = epoch
    torch.save(payload, path)
    LOGGER.info("saved checkpoint -> %s", path)


def load_checkpoint(path: str | Path, *, map_location: str = "cpu", strict: bool = True):
    """Load a checkpoint and rebuild the model.

    Returns ``(model, payload)``.  Raises ``FileNotFoundError`` /
    ``RuntimeError`` with a message that is safe to surface to operators
    (the API maps it to a 503).
    """
    import torch

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Model file not found: {path}")
    try:
        # weights_only=True: the checkpoint holds only tensors and plain
        # Python containers, so no arbitrary pickle code can execute if the
        # file is ever replaced.
        payload = torch.load(path, map_location=map_location, weights_only=True)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Model file is unreadable or corrupted: {exc}") from exc

    if not isinstance(payload, dict) or "state_dict" not in payload:
        raise RuntimeError("Model file does not contain a recognised checkpoint payload.")

    architecture = payload.get("architecture", DEFAULT_MODEL)
    num_classes = int(payload.get("num_classes", 2))
    model = build_model(architecture, num_classes, pretrained=False)
    try:
        model.load_state_dict(payload["state_dict"], strict=strict)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Checkpoint state_dict does not match architecture: {exc}") from exc
    model.eval()
    return model, payload
