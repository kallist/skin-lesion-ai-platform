"""Detection endpoints: upload + inference, history, image, delete, export."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, Query, Response, UploadFile, status

from ...core.config import get_settings
from ...core.errors import ImageTooLargeError
from ...schemas import DetectionOut, DetectionPage, MessageOut
from ...services import detection_service
from ...services.image_store import ValidatedImage, validate_upload
from ..deps import CsrfProtected, CurrentUser, DbSession, require_csrf

LOGGER = logging.getLogger("app.api.detections")
router = APIRouter(prefix="/detections", tags=["detections"])


async def _read_image(
    image: UploadFile,
    content_length: int | None,
) -> ValidatedImage:
    settings = get_settings()
    limit = settings.max_upload_bytes
    if content_length is not None and content_length > limit + 1_000_000:
        raise ImageTooLargeError(f"上传体积超过上限 {settings.max_upload_mb} MB")
    data = await image.read(limit + 1)
    if len(data) > limit:
        raise ImageTooLargeError(f"图片大小超过上限 {settings.max_upload_mb} MB")
    return validate_upload(data, image.filename or "upload")


@router.post("", response_model=DetectionOut, status_code=status.HTTP_201_CREATED)
async def create_detection(
    user: CurrentUser,
    db: DbSession,
    _csrf: CsrfProtected,
    image: Annotated[UploadFile, File(description="皮肤病变图片 (jpg/png/webp/bmp)")],
    save_history: Annotated[bool, Form()] = True,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    content_length: Annotated[int | None, Header(alias="Content-Length")] = None,
) -> DetectionOut:
    """Run inference on an uploaded image.

    Requires a logged-in session **and** a valid CSRF token (this endpoint is a
    cookie-authenticated state change).  ``Idempotency-Key`` makes client
    retries safe.
    """
    validated = await _read_image(image, content_length)
    result, _created = await detection_service.create_detection(
        db,
        user,
        validated.image,
        original_filename=validated.original_filename,
        save_history=save_history,
        idempotency_key=idempotency_key,
        image_sha256=validated.sha256,
        image_bytes=validated.byte_size,
    )
    return result


@router.get("", response_model=DetectionPage)
def list_detections(
    user: CurrentUser,
    db: DbSession,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    prediction: Annotated[str | None, Query(pattern="^(benign|malignant)$")] = None,
) -> DetectionPage:
    data = detection_service.list_detections(
        db, user, page=page, page_size=page_size, prediction=prediction
    )
    return DetectionPage(**data)


@router.get("/export", response_class=Response)
def export_detections(
    user: CurrentUser,
    db: DbSession,
    prediction: Annotated[str | None, Query(pattern="^(benign|malignant)$")] = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Response:
    """Download the user's history as CSV (never contains image data)."""
    csv_text = detection_service.export_csv(
        db, user, prediction=prediction, date_from=date_from, date_to=date_to
    )
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="detection_history_{stamp}.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{detection_id}", response_model=DetectionOut)
def get_detection(detection_id: int, user: CurrentUser, db: DbSession) -> DetectionOut:
    return detection_service.get_detection(db, user, detection_id)


@router.get("/{detection_id}/image", response_class=Response)
def get_detection_image(detection_id: int, user: CurrentUser, db: DbSession) -> Response:
    """Decrypt and stream the stored image after an ownership check."""
    data = detection_service.load_detection_image(db, user, detection_id)
    return Response(
        content=data,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=60, no-store",
            "Content-Disposition": f'inline; filename="detection_{detection_id}.png"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/{detection_id}",
    response_model=MessageOut,
    dependencies=[Depends(require_csrf)],
)
def delete_detection(detection_id: int, user: CurrentUser, db: DbSession) -> MessageOut:
    detection_service.delete_detection(db, user, detection_id)
    return MessageOut(message="检测记录已删除")
