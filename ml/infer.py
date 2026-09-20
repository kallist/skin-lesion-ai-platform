"""Single-image inference used by the backend model service and CLI tools.

The preprocessing here is intentionally the *same* code path as evaluation
(:func:`ml.transforms.build_eval_transform`), which is what makes the reported
test metrics meaningful for production requests.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

from .config import (
    CLASS_NAMES,
    CLASS_TO_IDX,
    DISCLAIMER_SHORT,
    IMAGE_SIZE,
    MALIGNANT_IDX,
    MODELS_DIR,
    device_info,
)
from .model import load_checkpoint
from .transforms import build_eval_transform

LOGGER = logging.getLogger("ml.infer")

# Reject absurd pixel counts before decoding (decompression-bomb guard).
MAX_PIXELS = 64_000_000


class SkinLesionPredictor:
    """Thread-safe, load-once predictor.

    The heavy model is loaded in ``__init__``; :meth:`predict` only runs the
    forward pass, so the FastAPI layer can keep a single instance and dispatch
    calls to a worker thread.
    """

    def __init__(
        self,
        model_path: str | Path = MODELS_DIR / "best_model.pt",
        *,
        device: str | None = None,
        input_size: int = IMAGE_SIZE,
        tta: bool = False,
    ) -> None:
        import torch

        self.model_path = Path(model_path)
        self.device_name = device or device_info()["device"]
        self.device = torch.device(self.device_name)
        self.input_size = input_size
        self.tta = tta

        started = time.perf_counter()
        self.model, self.payload = load_checkpoint(self.model_path, map_location="cpu")
        self.model.to(self.device).eval()
        self.load_seconds = time.perf_counter() - started

        meta = self.payload.get("meta", {}) or {}
        self.model_version = str(self.payload.get("model_version", meta.get("model_version", "unknown")))
        self.architecture = str(self.payload.get("architecture", meta.get("architecture", "unknown")))
        self.class_names = list(self.payload.get("class_names", CLASS_NAMES))
        self.class_mapping = dict(self.payload.get("class_mapping", CLASS_TO_IDX))
        normalization = self.payload.get("normalization") or meta.get("normalization") or {}
        mean = normalization.get("mean", (0.485, 0.456, 0.406))
        std = normalization.get("std", (0.229, 0.224, 0.225))
        self.transform = build_eval_transform(
            self.input_size, mean=tuple(mean), std=tuple(std)
        )
        self.trained_at = str(self.payload.get("trained_at", meta.get("trained_at", "")))
        self.best_val_metric = self.payload.get("best_val_metric", meta.get("best_val_metric", {}))
        LOGGER.info(
            "loaded %s (%s) on %s in %.2fs",
            self.model_path.name,
            self.architecture,
            self.device,
            self.load_seconds,
        )

    # ------------------------------------------------------------------
    @property
    def info(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "architecture": self.architecture,
            "input_size": self.input_size,
            "class_names": self.class_names,
            "class_mapping": self.class_mapping,
            "trained_at": self.trained_at,
            "best_val_metric": self.best_val_metric,
            "device": str(self.device),
            "model_file": self.model_path.name,
            "calibration": "NOT IMPLEMENTED",
        }

    # ------------------------------------------------------------------
    def preprocess(self, image: Image.Image):
        """PIL image -> normalised tensor batch of shape [1, 3, S, S]."""
        import torch

        if image.mode != "RGB":
            image = image.convert("RGB")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError(
                f"Image too large to process ({image.width}x{image.height} pixels)."
            )
        tensor = self.transform(image)
        return tensor.unsqueeze(0).to(self.device)

    def predict_tensor(self, batch) -> dict[str, Any]:
        import torch

        started = time.perf_counter()
        with torch.no_grad():
            logits = self.model(batch)
            probs = torch.softmax(logits.float(), dim=1)[0].detach().cpu().tolist()
        latency_ms = (time.perf_counter() - started) * 1000.0
        malignant_prob = float(probs[CLASS_TO_IDX["malignant"]])
        benign_prob = float(probs[CLASS_TO_IDX["benign"]])
        idx = int(MALIGNANT_IDX if malignant_prob >= benign_prob else CLASS_TO_IDX["benign"])
        prediction = CLASS_NAMES[idx]
        confidence = malignant_prob if prediction == "malignant" else benign_prob
        return {
            "prediction": prediction,
            "confidence": round(confidence, 6),
            "probabilities": {
                "benign": round(benign_prob, 6),
                "malignant": round(malignant_prob, 6),
            },
            "model_version": self.model_version,
            "disclaimer": DISCLAIMER_SHORT,
            "inference_latency_ms": round(latency_ms, 2),
        }

    def predict_image(self, image: Image.Image) -> dict[str, Any]:
        batch = self.preprocess(image)
        if not self.tta:
            return self.predict_tensor(batch)
        # optional horizontal-flip test-time augmentation (averaged probability)
        import torch

        with torch.no_grad():
            p1 = torch.softmax(self.model(batch).float(), dim=1)[0]
            p2 = torch.softmax(self.model(torch.flip(batch, dims=[3])).float(), dim=1)[0]
            probs = ((p1 + p2) / 2).detach().cpu().tolist()
        malignant_prob = float(probs[CLASS_TO_IDX["malignant"]])
        benign_prob = float(probs[CLASS_TO_IDX["benign"]])
        idx = int(MALIGNANT_IDX if malignant_prob >= benign_prob else CLASS_TO_IDX["benign"])
        prediction = CLASS_NAMES[idx]
        return {
            "prediction": prediction,
            "confidence": round(malignant_prob if prediction == "malignant" else benign_prob, 6),
            "probabilities": {
                "benign": round(benign_prob, 6),
                "malignant": round(malignant_prob, 6),
            },
            "model_version": self.model_version,
            "disclaimer": DISCLAIMER_SHORT,
            "tta": True,
        }

    def predict_path(self, path: str | Path) -> dict[str, Any]:
        with Image.open(path) as im:
            im.load()
            result = self.predict_image(im)
        result["path"] = str(path)
        return result

    def predict_many(self, paths: Iterable[str | Path], batch_size: int = 16):
        """Batch prediction used by the evaluation scripts."""
        import torch

        paths = list(paths)
        for start in range(0, len(paths), batch_size):
            chunk = paths[start : start + batch_size]
            tensors = []
            for p in chunk:
                with Image.open(p) as im:
                    im.load()
                    tensors.append(self.preprocess(im)[0])
            batch = torch.stack(tensors).to(self.device)
            with torch.no_grad():
                probs = torch.softmax(self.model(batch).float(), dim=1).detach().cpu().numpy()
            for path, row in zip(chunk, probs):
                yield path, float(row[CLASS_TO_IDX["benign"]]), float(row[CLASS_TO_IDX["malignant"]])


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Run inference on one or more images")
    p.add_argument("images", nargs="+")
    p.add_argument("--model", default=str(MODELS_DIR / "best_model.pt"))
    p.add_argument("--device", default=None)
    p.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    predictor = SkinLesionPredictor(args.model, device=args.device)
    results = []
    for image in args.images:
        r = predictor.predict_path(image)
        results.append(r)
        if args.json:
            continue
        print(
            f"{Path(image).name}: {r['prediction']} (confidence={r['confidence']:.4f}) "
            f"benign={r['probabilities']['benign']:.4f} malignant={r['probabilities']['malignant']:.4f}"
        )
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
