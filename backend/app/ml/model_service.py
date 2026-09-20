"""Model serving layer.

* Loads the trained checkpoint **once** per process (never per request).
* Runs the blocking PyTorch forward pass in a worker thread so the FastAPI event
  loop is never blocked.
* Bounds concurrency with a semaphore so several large uploads cannot saturate
  the CPU/GPU or trigger an out-of-memory condition.
* Provides a deterministic *stub* backend that is only used when explicitly
  configured (``MODEL_BACKEND=stub``) for UI/E2E tests, so that real inference
  remains the default and is always exercised by the smoke test.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from ..core.config import get_settings
from ..core.errors import InferenceFailedError, ModelUnavailableError

LOGGER = logging.getLogger("app.ml")


@dataclass
class PredictionResult:
    prediction: str
    confidence: float
    benign_probability: float
    malignant_probability: float
    model_version: str
    inference_latency_ms: float
    backend: str


class BaseModelBackend:
    name = "base"

    def predict(self, image: Image.Image) -> PredictionResult:  # pragma: no cover
        raise NotImplementedError

    @property
    def info(self) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class RealModelBackend(BaseModelBackend):
    """Thin wrapper around :class:`ml.infer.SkinLesionPredictor`."""

    name = "real"

    def __init__(self, model_path: str | Path) -> None:
        from ml.infer import SkinLesionPredictor  # imported lazily: torch is heavy

        self.predictor = SkinLesionPredictor(model_path)
        self.model_version = self.predictor.model_version

    def predict(self, image: Image.Image) -> PredictionResult:
        result = self.predictor.predict_image(image)
        return PredictionResult(
            prediction=result["prediction"],
            confidence=float(result["confidence"]),
            benign_probability=float(result["probabilities"]["benign"]),
            malignant_probability=float(result["probabilities"]["malignant"]),
            model_version=result["model_version"],
            inference_latency_ms=float(result.get("inference_latency_ms", 0.0)),
            backend=self.name,
        )

    @property
    def info(self) -> dict[str, Any]:
        info = dict(self.predictor.info)
        info["backend"] = self.name
        info["available"] = True
        return info


class StubModelBackend(BaseModelBackend):
    """Deterministic test double.

    Only selected with ``MODEL_BACKEND=stub``.  It hashes the image content so
    the same picture always yields the same probabilities, which keeps E2E and
    component tests deterministic without pretending to be a trained model.
    """

    name = "stub"
    model_version = "stub-deterministic-v1"

    def predict(self, image: Image.Image) -> PredictionResult:
        digest = hashlib.sha256(image.tobytes()).digest()
        raw = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        malignant = 0.15 + 0.70 * raw  # keep both classes reachable
        benign = 1.0 - malignant
        prediction = "malignant" if malignant >= benign else "benign"
        return PredictionResult(
            prediction=prediction,
            confidence=malignant if prediction == "malignant" else benign,
            benign_probability=benign,
            malignant_probability=malignant,
            model_version=self.model_version,
            inference_latency_ms=0.5,
            backend=self.name,
        )

    @property
    def info(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "architecture": "stub",
            "input_size": 224,
            "class_names": ["benign", "malignant"],
            "class_mapping": {"benign": 0, "malignant": 1},
            "trained_at": "",
            "device": "cpu",
            "calibration": "NOT IMPLEMENTED",
            "backend": self.name,
            "available": True,
        }


class ModelService:
    """Process-wide singleton model service."""

    def __init__(self) -> None:
        settings = get_settings()
        self._lock = threading.Lock()
        self._backend: BaseModelBackend | None = None
        self._load_error: str | None = None
        self._load_seconds = 0.0
        self._semaphore = threading.BoundedSemaphore(max(1, settings.inference_concurrency))
        self._pool = ThreadPoolExecutor(
            max_workers=max(2, settings.inference_concurrency * 2),
            thread_name_prefix="inference",
        )
        self._requests = 0
        self._total_inference_ms = 0.0
        self._lazy_attempted = False

    # ------------------------------------------------------------------
    def load(self, *, force: bool = False) -> None:
        """Load the backend once. Records the failure instead of crashing."""
        settings = get_settings()
        with self._lock:
            if self._backend is not None and not force:
                return
            self._load_error = None
            self._lazy_attempted = False
            backend = settings.model_backend.lower()
            started = time.perf_counter()
            try:
                if backend == "stub":
                    LOGGER.warning(
                        "MODEL_BACKEND=stub: using the deterministic test double, "
                        "NOT the trained model"
                    )
                    self._backend = StubModelBackend()
                else:
                    self._backend = RealModelBackend(settings.model_path)
            except Exception as exc:  # noqa: BLE001
                self._load_error = f"{type(exc).__name__}: {exc}"
                self._backend = None
                LOGGER.error("model load failed: %s", self._load_error)
            self._load_seconds = time.perf_counter() - started
            if self._backend is not None:
                LOGGER.info(
                    "model backend '%s' ready in %.2fs (version=%s)",
                    self._backend.name,
                    self._load_seconds,
                    self._backend.model_version,
                )

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        return self._backend is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    @property
    def _public_load_error(self) -> str | None:
        """Exception type only (never a path or model internals)."""
        if not self._load_error:
            return None
        return self._load_error.split(":", 1)[0]

    @property
    def load_seconds(self) -> float:
        return self._load_seconds

    @property
    def info(self) -> dict[str, Any]:
        if self._backend is None:
            return {
                "model_version": "unavailable",
                "architecture": "unknown",
                "input_size": 224,
                "class_names": ["benign", "malignant"],
                "class_mapping": {"benign": 0, "malignant": 1},
                "trained_at": "",
                "device": "cpu",
                "calibration": "NOT IMPLEMENTED",
                "backend": "none",
                "available": False,
                # Only the exception type is exposed: a raw message can contain
                # filesystem paths and must stay in the server log.
                "error": self._public_load_error,
            }
        info = dict(self._backend.info)
        info["requests_served"] = self._requests
        info["avg_inference_ms"] = (
            round(self._total_inference_ms / self._requests, 2) if self._requests else None
        )
        return info

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "requests_served": self._requests,
            "avg_inference_ms": (
                round(self._total_inference_ms / self._requests, 2) if self._requests else None
            ),
            "concurrency_limit": self._semaphore._initial_value,  # noqa: SLF001
        }

    # ------------------------------------------------------------------
    def _predict_sync(self, image: Image.Image) -> PredictionResult:
        if self._backend is None:
            # One lazy attempt (covers MODEL_WARMUP=false and a model file that
            # appeared after startup).  A failed load is remembered and not
            # retried on every request.
            if not self._lazy_attempted:
                self._lazy_attempted = True
                self.load()
            if self._backend is None:
                raise ModelUnavailableError()
        acquired = self._semaphore.acquire(timeout=30)
        if not acquired:
            raise ModelUnavailableError("模型当前繁忙，请稍后重试")
        try:
            return self._backend.predict(image)
        except (ModelUnavailableError, InferenceFailedError):
            raise
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("inference failed: %s", type(exc).__name__)
            raise InferenceFailedError() from exc
        finally:
            self._semaphore.release()

    async def predict(self, image: Image.Image) -> PredictionResult:
        """Async entry point: runs the blocking forward pass in a worker thread."""
        import anyio

        if self._backend is None:
            raise ModelUnavailableError()
        result = await anyio.to_thread.run_sync(self._predict_sync, image)
        self._requests += 1
        self._total_inference_ms += result.inference_latency_ms
        return result

    def predict_sync(self, image: Image.Image) -> PredictionResult:
        result = self._predict_sync(image)
        self._requests += 1
        self._total_inference_ms += result.inference_latency_ms
        return result

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


_model_service: ModelService | None = None
_service_lock = threading.Lock()


def get_model_service() -> ModelService:
    global _model_service
    if _model_service is None:
        with _service_lock:
            if _model_service is None:
                _model_service = ModelService()
    return _model_service


def reset_model_service() -> None:
    """Test helper."""
    global _model_service
    if _model_service is not None:
        _model_service.shutdown()
    _model_service = None
