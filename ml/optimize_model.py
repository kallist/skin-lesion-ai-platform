"""Model optimisation experiments: size, latency and accuracy impact.

python ml/optimize_model.py --model models/best_model.pt

What it does (all numbers are measured, never estimated):

1. Baseline: file size, parameter count, CPU latency (median of N runs), and
   optional accuracy on the internal test split.
2. ``torch.quantization.quantize_dynamic`` on the Linear layers — a genuine
   CPU dynamic-quantisation experiment.
3. Optional TorchScript export (``torch.jit.trace``) for deployment.

Honest reporting: if quantisation costs accuracy or is not beneficial, the
report says so and the baseline model remains the production model.  The
optimised model is **never** silently swapped into the API.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from pathlib import Path

import pandas as pd

from .config import ARTIFACTS_DIR, CLASS_TO_IDX, MANIFEST_DIR, MODELS_DIR, device_info
from .evaluate import resolve_manifest_paths
from .infer import SkinLesionPredictor
from .metrics import binary_metrics

LOGGER = logging.getLogger("ml.optimize")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Benchmark / optimise the trained model")
    p.add_argument("--model", default=str(MODELS_DIR / "best_model.pt"))
    p.add_argument("--data", default=str(MANIFEST_DIR))
    p.add_argument("--split", default="val", choices=["train", "val", "test"])
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--device", default="cpu")
    p.add_argument("--skip-quantization", action="store_true")
    p.add_argument("--torchscript", action="store_true")
    p.add_argument("--output", default=str(ARTIFACTS_DIR / "optimization_report.json"))
    return p.parse_args(argv)


def file_size_mb(path: Path) -> float:
    return round(path.stat().st_size / (1024 * 1024), 3)


def measure_latency(predictor: SkinLesionPredictor, image_paths: list[Path], runs: int, warmup: int):
    """Return per-image latency statistics in milliseconds."""
    import torch

    for path in image_paths[:warmup]:
        predictor.predict_path(path)
    if predictor.device.type == "cuda":
        torch.cuda.synchronize()

    samples: list[float] = []
    for i in range(runs):
        path = image_paths[i % len(image_paths)]
        t0 = time.perf_counter()
        predictor.predict_path(path)
        if predictor.device.type == "cuda":
            torch.cuda.synchronize()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "runs": runs,
        "mean_ms": round(statistics.fmean(samples), 3),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(sorted(samples)[max(int(len(samples) * 0.95) - 1, 0)], 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
        "throughput_images_per_sec": round(1000.0 / statistics.fmean(samples), 2),
    }


def accuracy_on_split(predictor: SkinLesionPredictor, manifest: Path, batch_size: int = 16) -> dict:
    if not manifest.exists():
        return {}
    frame = pd.read_csv(manifest)
    paths = resolve_manifest_paths(frame, manifest)
    labels = frame["label_idx"].astype(int).tolist()
    y_true, y_pred, y_prob = [], [], []
    for index, (_path, p_benign, p_malignant) in enumerate(
        predictor.predict_many(paths, batch_size)
    ):
        y_true.append(labels[index])
        y_pred.append(1 if p_malignant >= p_benign else 0)
        y_prob.append(p_malignant)
    return binary_metrics(y_true, y_pred, y_prob)


def dynamic_quantize(model):
    import torch

    return torch.ao.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    model_path = Path(args.model)
    predictor = SkinLesionPredictor(model_path, device=args.device)
    manifest = Path(args.data) / f"{args.split}.csv"
    images = []
    if manifest.exists():
        frame = pd.read_csv(manifest)
        images = [Path(p) for p in resolve_manifest_paths(frame, manifest)[:50]]
    if not images:
        raise SystemExit(f"No images found via manifest {manifest}")

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": device_info(),
        "device": str(predictor.device),
        "baseline": {
            "model_file": model_path.name,
            "size_mb": file_size_mb(model_path),
            "parameters": int(sum(p.numel() for p in predictor.model.parameters())),
            "load_seconds": round(predictor.load_seconds, 3),
            "latency": measure_latency(predictor, images, args.runs, args.warmup),
            "metrics": accuracy_on_split(predictor, manifest),
        },
        "torchscript": None,
        "dynamic_quantization": None,
        "notes": [],
    }
    base = report["baseline"]
    print(
        f"[optimize] baseline: {base['size_mb']} MB, {base['parameters']:,} params, "
        f"median {base['latency']['median_ms']} ms/img, load {base['load_seconds']} s"
    )
    if base["metrics"]:
        print(
            f"[optimize] baseline {args.split} accuracy={base['metrics']['accuracy']:.4f} "
            f"auc={base['metrics'].get('roc_auc')}"
        )

    # ---------------- TorchScript export ----------------
    if args.torchscript:
        import torch

        out = model_path.with_name("best_model_torchscript.pt")
        try:
            from PIL import Image as PILImage

            with PILImage.open(images[0]) as im:
                example = predictor.preprocess(im.convert("RGB"))
            with torch.no_grad():
                traced = torch.jit.trace(predictor.model.cpu(), example.cpu())
            traced.save(str(out))
            # verify the traced module produces the same probabilities
            with torch.no_grad():
                ref = torch.softmax(predictor.model.cpu()(example.cpu()), dim=1)
                got = torch.softmax(traced(example.cpu()), dim=1)
            max_diff = float((ref - got).abs().max())
            report["torchscript"] = {
                "file": out.name,
                "size_mb": file_size_mb(out),
                "max_probability_diff": round(max_diff, 8),
                "used_in_production": False,
            }
            print(f"[optimize] TorchScript saved -> {out} (max diff {max_diff:.2e})")
            predictor.model.to(predictor.device)
        except Exception as exc:  # noqa: BLE001
            report["torchscript"] = {"error": f"{type(exc).__name__}: {exc}"}
            report["notes"].append(f"TorchScript export failed: {exc}")
            print(f"[optimize] TorchScript export FAILED: {exc}")

    # ---------------- dynamic quantization ----------------
    if not args.skip_quantization:
        try:
            q_model = dynamic_quantize(predictor.model.to("cpu"))
            q_predictor = SkinLesionPredictor.__new__(SkinLesionPredictor)
            q_predictor.model = q_model
            q_predictor.device = __import__("torch").device("cpu")
            q_predictor.model_path = model_path
            q_predictor.transform = predictor.transform
            q_predictor.input_size = predictor.input_size
            q_predictor.model_version = predictor.model_version + "+int8dyn"
            q_predictor.architecture = predictor.architecture
            q_predictor.class_names = predictor.class_names
            q_predictor.class_mapping = predictor.class_mapping
            q_predictor.load_seconds = 0.0
            q_predictor.tta = False

            q_metrics = accuracy_on_split(q_predictor, manifest)
            q_latency = measure_latency(q_predictor, images, args.runs, args.warmup)
            q_path = model_path.with_name("best_model_int8_dynamic.pt")
            import torch

            torch.save({"state_dict": q_model.state_dict(), "architecture": predictor.architecture,
                        "num_classes": 2, "class_mapping": dict(CLASS_TO_IDX),
                        "class_names": predictor.class_names, "model_version": q_predictor.model_version,
                        "quantized": "dynamic-int8-linear"}, q_path)
            entry = {
                "file": q_path.name,
                "size_mb": file_size_mb(q_path),
                "latency": q_latency,
                "metrics": q_metrics,
                "accuracy_delta": (
                    round(q_metrics["accuracy"] - base["metrics"]["accuracy"], 6)
                    if q_metrics and base["metrics"]
                    else None
                ),
                "used_in_production": False,
            }
            report["dynamic_quantization"] = entry
            print(
                f"[optimize] int8-dynamic: {entry['size_mb']} MB, median "
                f"{q_latency['median_ms']} ms/img, accuracy_delta={entry['accuracy_delta']}"
            )
        except Exception as exc:  # noqa: BLE001
            report["dynamic_quantization"] = {"error": f"{type(exc).__name__}: {exc}"}
            report["notes"].append(f"Dynamic quantization failed: {exc}")
            print(f"[optimize] dynamic quantization FAILED: {exc}")

    report["notes"] += [
        "Latency measured with a warm model on a single process; numbers depend on hardware.",
        "The quantised model is experimental and is NOT used by the production API.",
        "Production deployment keeps the FP32 checkpoint because it is the accuracy reference.",
    ]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[optimize] report -> {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
