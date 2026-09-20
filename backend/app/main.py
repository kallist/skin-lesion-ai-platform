"""FastAPI application factory.

Wiring:  API router -> services -> repositories (SQLAlchemy) -> SQLite,
with the ML path  DetectionService -> ModelService -> PyTorch.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from .api.v1.router import api_router
from .core.config import get_settings
from .core.errors import install_error_handlers
from .core.logging import configure_logging
from .db import init_db
from .db import SessionLocal
from .ml.model_service import get_model_service

LOGGER = logging.getLogger("app.main")

# Security headers applied to every response.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        return response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.2f}"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    LOGGER.info("starting %s v%s (%s)", settings.app_name, settings.app_version, settings.app_env)
    for warning in settings.validate_runtime():
        LOGGER.warning("config: %s", warning)

    init_db()

    service = get_model_service()
    if settings.model_warmup:
        service.load()
        if not service.available:
            LOGGER.error("model unavailable: %s", service.load_error)
    else:
        LOGGER.info("model warmup disabled (MODEL_WARMUP=false); loading lazily on first request")

    if settings.orphan_sweep_on_startup:
        try:
            from .services.detection_service import sweep_orphan_images

            with SessionLocal() as db:
                sweep_orphan_images(db)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("orphan sweep skipped: %s", type(exc).__name__)

    yield

    service.shutdown()
    LOGGER.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "皮肤病变良恶性辅助识别 API。AI辅助检测结果，仅供参考，不构成医学诊断。\n\n"
            "Detection results are for reference only and do not constitute a medical diagnosis."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    install_error_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_credentials=True,  # required for the session cookie
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
            expose_headers=["Content-Disposition", "X-Process-Time-Ms"],
            max_age=600,
        )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": settings.app_name,
                "version": settings.app_version,
                "docs": "/docs",
                "api_prefix": settings.api_prefix,
                "disclaimer": "AI辅助检测结果，仅供参考，不构成医学诊断。",
            }
        )

    return app


app = create_app()
