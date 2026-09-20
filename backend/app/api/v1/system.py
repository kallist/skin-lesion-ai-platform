"""Model info + system health endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter

from ...core.config import get_settings
from ...db import healthcheck as db_healthcheck
from ...ml.model_service import get_model_service
from ...schemas import HealthOut, ModelInfo

LOGGER = logging.getLogger("app.api.system")
router = APIRouter(tags=["system"])

_STARTED_AT = time.time()


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness/readiness probe used by Docker and the frontend banner."""
    settings = get_settings()
    service = get_model_service()
    db_ok = db_healthcheck()
    model_ok = service.available
    return HealthOut(
        status="ok" if (db_ok and model_ok) else "degraded",
        version=settings.app_version,
        environment=settings.app_env,
        database=db_ok,
        model=model_ok,
        model_version=service.info.get("model_version") if model_ok else None,
        uptime_seconds=round(time.time() - _STARTED_AT, 2),
    )


@router.get("/model/info", response_model=ModelInfo)
def model_info() -> ModelInfo:
    """Metadata of the currently served model (class mapping comes from here)."""
    service = get_model_service()
    info = service.info
    return ModelInfo(
        model_version=str(info.get("model_version", "unknown")),
        architecture=str(info.get("architecture", "unknown")),
        input_size=int(info.get("input_size", 224)),
        class_names=list(info.get("class_names", ["benign", "malignant"])),
        class_mapping=dict(info.get("class_mapping", {"benign": 0, "malignant": 1})),
        trained_at=str(info.get("trained_at", "")),
        device=str(info.get("device", "cpu")),
        calibration=str(info.get("calibration", "NOT IMPLEMENTED")),
        disclaimer="AI辅助检测结果，仅供参考，不构成医学诊断。",
        available=bool(info.get("available", False)),
        best_val_metric=dict(info.get("best_val_metric", {}) or {}),
    )
