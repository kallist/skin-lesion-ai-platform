"""ResNet training entry point.

python ml/train.py --epochs 18 --batch-size 32 --model resnet50

Design
------
* Stage 1: backbone frozen, classifier head trained with a larger LR.
* Stage 2: whole network fine-tuned with a small LR.
* Class imbalance handled with class-weighted CrossEntropyLoss (the shipped
  dataset is mildly imbalanced: 1040 benign vs 800 malignant).
* Model selection uses the **validation** split only.  The internal test split
  is touched exactly once, at the very end, by ``ml/evaluate.py``.
* Early stopping + best-checkpoint saving, plus per-epoch history and training
  curves.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .config import (
    ARTIFACTS_DIR,
    CLASS_NAMES,
    CLASS_TO_IDX,
    DEFAULT_BATCH_SIZE,
    DEFAULT_EPOCHS,
    DEFAULT_HEAD_EPOCHS,
    DEFAULT_LR_FINETUNE,
    DEFAULT_LR_HEAD,
    DEFAULT_MODEL,
    DEFAULT_NUM_WORKERS,
    DEFAULT_PATIENCE,
    DEFAULT_WEIGHT_DECAY,
    MANIFEST_DIR,
    MODELS_DIR,
    ModelMeta,
    PROJECT_VERSION,
    SEED,
    device_info,
    set_global_seed,
)
from .metrics import binary_metrics
from .model import build_model, count_parameters, freeze_backbone, save_checkpoint, unfreeze_backbone
from .transforms import build_eval_transform, build_train_transform

LOGGER = logging.getLogger("ml.train")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Train the skin lesion classifier")
    p.add_argument("--data", default=str(MANIFEST_DIR), help="manifest directory")
    p.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    p.add_argument("--head-epochs", type=int, default=DEFAULT_HEAD_EPOCHS)
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    p.add_argument("--lr", type=float, default=DEFAULT_LR_HEAD, help="stage-1 (head) LR")
    p.add_argument("--finetune-lr", type=float, default=DEFAULT_LR_FINETUNE)
    p.add_argument("--weight-decay", type=float, default=DEFAULT_WEIGHT_DECAY)
    p.add_argument("--model", default=DEFAULT_MODEL, help="resnet18|resnet34|resnet50|resnet101")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--output-dir", default=str(MODELS_DIR))
    p.add_argument("--artifacts-dir", default=str(ARTIFACTS_DIR))
    p.add_argument("--num-workers", type=int, default=DEFAULT_NUM_WORKERS)
    p.add_argument("--patience", type=int, default=DEFAULT_PATIENCE)
    p.add_argument("--run-name", default="run_a_resnet50")
    p.add_argument("--no-pretrained", action="store_true")
    p.add_argument("--no-amp", action="store_true")
    p.add_argument("--class-weights", choices=["auto", "none"], default="auto")
    p.add_argument("--vertical-flip", action="store_true")
    p.add_argument("--rotation", type=float, default=15.0)
    p.add_argument("--crop-scale-min", type=float, default=0.85)
    p.add_argument("--color-jitter", type=float, default=0.15)
    p.add_argument("--limit-train-batches", type=int, default=0, help="debug: cap batches/epoch")
    return p.parse_args(argv)


def _load_split(data_dir: Path, split: str, transform):
    from .dataset import make_dataset

    csv = data_dir / f"{split}.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"Manifest {csv} not found. Run `python -m ml.prepare_data` first."
        )
    return make_dataset(csv, transform=transform)


def evaluate_split(model, loader, device, *, amp: bool = True, desc: str = "eval") -> dict:
    import torch

    model.eval()
    all_true, all_pred, all_prob = [], [], []
    total_loss, n_batches = 0.0, 0
    criterion = torch.nn.CrossEntropyLoss()
    with torch.no_grad():
        for images, labels, _paths in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, enabled=amp and device.type == "cuda"):
                logits = model(images)
                loss = criterion(logits, labels)
            probs = torch.softmax(logits.float(), dim=1)
            preds = probs.argmax(dim=1)
            all_true.extend(labels.detach().cpu().tolist())
            all_pred.extend(preds.detach().cpu().tolist())
            all_prob.extend(probs[:, CLASS_TO_IDX["malignant"]].detach().cpu().tolist())
            total_loss += float(loss.item())
            n_batches += 1
    metrics = binary_metrics(all_true, all_pred, all_prob)
    metrics["loss"] = total_loss / max(n_batches, 1)
    metrics["_y_true"] = all_true
    metrics["_y_prob"] = all_prob
    LOGGER.info(
        "%s: n=%d acc=%.4f f1=%.4f auc=%.4f malignant_recall=%.4f loss=%.4f",
        desc,
        metrics["n"],
        metrics["accuracy"],
        metrics["f1"],
        metrics.get("roc_auc", float("nan")),
        metrics["malignant_recall"],
        metrics["loss"],
    )
    return metrics


def _selection_score(metrics: dict) -> float:
    """Validation model-selection criterion (never uses the test split)."""
    auc = metrics.get("roc_auc")
    if auc is not None and not math.isnan(auc):
        return float(auc)
    return float(metrics.get("balanced_accuracy", metrics.get("accuracy", 0.0)))


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    set_global_seed(args.seed)

    import torch
    from torch.utils.data import DataLoader

    info = device_info()
    device = torch.device(info["device"])
    print(f"[train] device={info['device']} torch={info.get('torch')} gpu={info.get('gpu', '-')}")

    data_dir = Path(args.data)
    train_ds = _load_split(
        data_dir,
        "train",
        build_train_transform(
            rotation=args.rotation,
            scale=(args.crop_scale_min, 1.0),
            color_jitter=args.color_jitter,
            vertical_flip=args.vertical_flip,
        ),
    )
    val_ds = _load_split(data_dir, "val", build_eval_transform())
    print(f"[train] train={len(train_ds)} val={len(val_ds)}")

    loader_kwargs = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=device.type == "cuda",
        persistent_workers=args.num_workers > 0,
    )
    train_loader = DataLoader(train_ds, shuffle=True, drop_last=False, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)

    # ---- class weights (real counts from the manifest) --------------------
    train_labels = train_ds.frame["label_idx"].to_numpy()
    counts = np.bincount(train_labels, minlength=len(CLASS_NAMES)).astype(float)
    class_weights = None
    if args.class_weights == "auto":
        inv = counts.sum() / (len(CLASS_NAMES) * np.maximum(counts, 1.0))
        class_weights = torch.tensor(inv, dtype=torch.float32, device=device)
        print(f"[train] class counts={counts.tolist()} weights={[round(w, 4) for w in inv.tolist()]}")

    model = build_model(args.model, len(CLASS_NAMES), pretrained=not args.no_pretrained)
    model.to(device)
    params = count_parameters(model)
    print(f"[train] model={args.model} params_total={params['total']:,}")

    criterion = torch.nn.CrossEntropyLoss(weight=class_weights)
    use_amp = (not args.no_amp) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    meta = ModelMeta(
        model_version=f"{PROJECT_VERSION}+{args.run_name}",
        architecture=args.model,
        num_classes=len(CLASS_NAMES),
        seed=args.seed,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        pretrained="none" if args.no_pretrained else "imagenet",
        environment=info,
        dataset={
            "train": int(len(train_ds)),
            "val": int(len(val_ds)),
            "train_class_counts": {
                CLASS_NAMES[i]: int(counts[i]) for i in range(len(CLASS_NAMES))
            },
            "manifest_dir": str(data_dir),
        },
        hyperparameters={
            "epochs": args.epochs,
            "head_epochs": args.head_epochs,
            "batch_size": args.batch_size,
            "lr_head": args.lr,
            "lr_finetune": args.finetune_lr,
            "weight_decay": args.weight_decay,
            "optimizer": "AdamW",
            "scheduler": "CosineAnnealingLR",
            "loss": "CrossEntropyLoss",
            "class_weights": "auto" if class_weights is not None else "none",
            "augmentation": {
                "random_resized_crop_scale": [args.crop_scale_min, 1.0],
                "rotation_deg": args.rotation,
                "horizontal_flip": True,
                "vertical_flip": args.vertical_flip,
                "color_jitter": args.color_jitter,
            },
            "amp": use_amp,
            "patience": args.patience,
            "run_name": args.run_name,
        },
    )

    history: list[dict] = []
    best_score = -1.0
    best_epoch = -1
    best_state = None
    epochs_without_improvement = 0
    started = time.time()
    total_epochs = args.epochs
    optimizer = None
    scheduler = None
    current_stage = ""

    for epoch in range(1, total_epochs + 1):
        stage = "head" if epoch <= args.head_epochs else "finetune"
        if stage != current_stage:
            # (re)build optimizer + scheduler once per stage so the cosine
            # schedule follows the full stage length instead of restarting.
            if stage == "head":
                freeze_backbone(model)
            else:
                unfreeze_backbone(model)
            lr = args.lr if stage == "head" else args.finetune_lr
            stage_length = (
                args.head_epochs if stage == "head" else max(total_epochs - args.head_epochs, 1)
            )
            optimizer = torch.optim.AdamW(
                (p for p in model.parameters() if p.requires_grad),
                lr=lr,
                weight_decay=args.weight_decay,
            )
            scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
                optimizer, T_max=stage_length, eta_min=lr * 0.05
            )
            current_stage = stage
            if stage == "finetune":
                LOGGER.info(
                    "stage 2: backbone unfrozen, LR=%g for %d epochs", lr, stage_length
                )
        lr = float(optimizer.param_groups[0]["lr"])

        model.train()
        running_loss, seen, correct = 0.0, 0, 0
        epoch_start = time.time()
        for step, (images, labels, _paths) in enumerate(train_loader):
            if args.limit_train_batches and step >= args.limit_train_batches:
                break
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                logits = model(images)
                loss = criterion(logits, labels)
            if use_amp:
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()

            running_loss += float(loss.item()) * labels.size(0)
            seen += labels.size(0)
            correct += int((logits.argmax(1) == labels).sum().item())
        scheduler.step()

        train_loss = running_loss / max(seen, 1)
        train_acc = correct / max(seen, 1)
        val_metrics = evaluate_split(model, val_loader, device, amp=use_amp, desc=f"val@{epoch}")
        score = _selection_score(val_metrics)

        record = {
            "epoch": epoch,
            "stage": stage,
            "lr": lr,
            "train_loss": train_loss,
            "train_accuracy": train_acc,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_f1": val_metrics["f1"],
            "val_roc_auc": val_metrics.get("roc_auc"),
            "val_malignant_recall": val_metrics["malignant_recall"],
            "val_specificity": val_metrics["specificity"],
            "seconds": round(time.time() - epoch_start, 1),
        }
        history.append(record)
        print(
            f"[epoch {epoch:02d}/{total_epochs}] {stage:8s} lr={lr:.2e} "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.4f} "
            f"val_acc={val_metrics['accuracy']:.4f} val_auc={score:.4f} "
            f"val_recall={val_metrics['malignant_recall']:.4f} ({record['seconds']}s)"
        )

        if score > best_score + 1e-6:
            best_score = score
            best_epoch = epoch
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            meta.best_val_metric = {
                k: v
                for k, v in val_metrics.items()
                if not k.startswith("_") and isinstance(v, (int, float))
            }
            meta.best_val_metric["selection_score"] = score
            meta.best_epoch = epoch
            epochs_without_improvement = 0
            print(f"           --> new best (score={score:.4f})")
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= args.patience:
                print(f"[train] early stopping at epoch {epoch} (no improvement for {args.patience})")
                break

    training_seconds = time.time() - started
    if best_state is None:
        raise RuntimeError("Training produced no checkpoint (no epoch completed).")
    model.load_state_dict(best_state)
    model.to(device)

    meta.epochs_trained = len(history)
    meta.training_seconds = round(training_seconds, 2)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / "best_model.pt"
    save_checkpoint(ckpt, model, meta, epoch=best_epoch)
    meta.to_json(out_dir / "model_meta.json")
    with (out_dir / "class_mapping.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "class_to_idx": dict(CLASS_TO_IDX),
                "idx_to_class": {str(k): v for k, v in {0: "benign", 1: "malignant"}.items()},
                "positive_class": "malignant",
                "note": "Index order is fixed by the training pipeline; clients must not guess it.",
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )

    artifacts = Path(args.artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)
    with (artifacts / "training_history.json").open("w", encoding="utf-8") as fh:
        json.dump(
            {
                "run_name": args.run_name,
                "architecture": args.model,
                "seed": args.seed,
                "best_epoch": best_epoch,
                "best_selection_score": best_score,
                "training_seconds": round(training_seconds, 2),
                "environment": info,
                "hyperparameters": meta.hyperparameters,
                "history": history,
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )
    _plot_training_curves(history, artifacts)

    print(
        f"[train] done in {training_seconds/60:.1f} min | best_epoch={best_epoch} "
        f"best_val_score={best_score:.4f} | checkpoint={ckpt}"
    )
    return 0


def _plot_training_curves(history: list[dict], artifacts: Path) -> None:
    if not history:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    epochs = [h["epoch"] for h in history]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    axes[0].plot(epochs, [h["train_loss"] for h in history], marker="o", label="train loss")
    axes[0].plot(epochs, [h["val_loss"] for h in history], marker="s", label="val loss")
    axes[0].set_xlabel("epoch")
    axes[0].set_ylabel("loss")
    axes[0].set_title("Training / validation loss")
    axes[0].grid(alpha=0.3)
    axes[0].legend()

    axes[1].plot(epochs, [h["train_accuracy"] for h in history], marker="o", label="train acc")
    axes[1].plot(epochs, [h["val_accuracy"] for h in history], marker="s", label="val acc")
    axes[1].plot(
        epochs,
        [h["val_roc_auc"] if h["val_roc_auc"] is not None else float("nan") for h in history],
        marker="^",
        label="val ROC-AUC",
    )
    axes[1].set_xlabel("epoch")
    axes[1].set_ylabel("score")
    axes[1].set_ylim(0.5, 1.01)
    axes[1].set_title("Accuracy / ROC-AUC")
    axes[1].grid(alpha=0.3)
    axes[1].legend()

    fig.suptitle("Skin lesion classifier — real training history")
    fig.tight_layout()
    fig.savefig(artifacts / "training_curves.png", dpi=140)
    plt.close(fig)
    # individual files required by the delivery spec
    for name, key, ylabel in (
        ("training_loss.png", "loss", "loss"),
        ("training_accuracy.png", "accuracy", "accuracy"),
    ):
        fig, ax = plt.subplots(figsize=(6.5, 4.5))
        if key == "loss":
            ax.plot(epochs, [h["train_loss"] for h in history], marker="o", label="train")
            ax.plot(epochs, [h["val_loss"] for h in history], marker="s", label="val")
        else:
            ax.plot(epochs, [h["train_accuracy"] for h in history], marker="o", label="train")
            ax.plot(epochs, [h["val_accuracy"] for h in history], marker="s", label="val")
        ax.set_xlabel("epoch")
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(artifacts / name, dpi=140)
        plt.close(fig)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
