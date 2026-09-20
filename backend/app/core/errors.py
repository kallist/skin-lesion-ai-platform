"""Unified API error contract.

Every error response has the shape::

    {"error": {"code": "INVALID_IMAGE", "message": "...", "details": {...}}}

Internal details (tracebacks, file paths, SQL, secrets) are logged server-side
but never returned to the client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

LOGGER = logging.getLogger("app.errors")


class AppError(Exception):
    """Base class for domain errors that map onto the error contract."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "BAD_REQUEST"
    message: str = "请求无法处理"

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        super().__init__(message or self.message)
        if message:
            self.message = message
        self.details = details or {}

    def to_response(self) -> JSONResponse:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return JSONResponse(status_code=self.status_code, content={"error": payload})


class InvalidImageError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_IMAGE"
    message = "上传文件不是有效图片"


class UnsupportedImageTypeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "UNSUPPORTED_IMAGE_TYPE"
    message = "仅支持 JPEG / PNG / WEBP / BMP 格式的图片"


class ImageTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "FILE_TOO_LARGE"
    message = "上传图片超过大小限制"


class UnauthenticatedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHENTICATED"
    message = "请先登录"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "没有权限访问该资源"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "资源不存在"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "资源已存在"


class ModelUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "MODEL_UNAVAILABLE"
    message = "模型服务当前不可用，请稍后再试"


class InferenceFailedError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "INFERENCE_FAILED"
    message = "模型推理失败"


class StorageError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "STORAGE_ERROR"
    message = "图片存储失败"


class RateLimitedError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    message = "操作过于频繁，请稍后再试"


_HTTP_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            LOGGER.error("app error: %s (%s)", exc.message, exc.code, exc_info=exc)
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(x) for x in err.get("loc", [])[1:]) or "body",
                "message": err.get("msg", "invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "请求参数校验失败",
                    "details": {"fields": details},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": message}},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("unhandled server error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请稍后再试",
                }
            },
        )
