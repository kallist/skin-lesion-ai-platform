"""Detection orchestration: inference + encrypted history + export.

Ordering guarantees (see docs/engineering/ARCHITECTURE.md)
----------------------------------------------
1. validate / decode the upload (rejects spoofed or corrupt files),
2. run inference,
3. encrypt the image to a temp file, then atomically rename it into place,
4. insert the detection row inside a transaction and commit,
5. if step 4 fails, delete the file written in step 3.

Idempotency is enforced by a database UNIQUE constraint on
``(user_id, idempotency_key)`` and by translating the resulting IntegrityError
into "return the existing record", so a network retry can never create two rows.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any, Iterable

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from ..core.config import get_settings
from ..core.errors import ForbiddenError, NotFoundError, StorageError
from ..db.models import Detection, User
from ..ml.model_service import ModelService, get_model_service
from ..schemas import DetectionListItem, DetectionOut, Probabilities
from .image_store import EncryptedImageStore, get_image_store

LOGGER = logging.getLogger("app.detection")

DISCLAIMER = "本系统仅作为皮肤健康辅助自检工具，检测结果仅供参考，不能替代专业医生诊断。"

ADVICE = {
    "malignant": (
        "模型检测结果倾向于恶性风险。该结果不能替代医生诊断，建议尽快由皮肤科专业人员"
        "进一步评估；若皮损出现快速增大、颜色改变、破溃或出血，请尽快就医。"
    ),
    "benign": (
        "模型检测结果倾向于良性，但 AI 检测不能完全排除风险。如皮损持续变化、出现不适或"
        "你仍有疑虑，建议咨询皮肤科医生。"
    ),
}

CSV_COLUMNS = [
    "id",
    "created_at",
    "prediction",
    "confidence",
    "benign_probability",
    "malignant_probability",
    "model_version",
    "original_filename",
    "inference_latency_ms",
]


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------
def detection_to_out(detection: Detection, store: EncryptedImageStore | None = None) -> DetectionOut:
    store = store or get_image_store()
    return DetectionOut(
        id=detection.id,
        prediction=detection.prediction,  # type: ignore[arg-type]
        confidence=round(detection.confidence, 6),
        probabilities=Probabilities(
            benign=round(detection.benign_probability, 6),
            malignant=round(detection.malignant_probability, 6),
        ),
        model_version=detection.model_version,
        original_filename=detection.original_filename,
        image_available=store.exists(detection.encrypted_image_path),
        disclaimer=DISCLAIMER,
        advice=ADVICE.get(detection.prediction, ADVICE["benign"]),
        created_at=detection.created_at,
    )


def detection_to_list_item(detection: Detection, store: EncryptedImageStore | None = None) -> DetectionListItem:
    store = store or get_image_store()
    return DetectionListItem(
        id=detection.id,
        prediction=detection.prediction,  # type: ignore[arg-type]
        confidence=round(detection.confidence, 6),
        probabilities=Probabilities(
            benign=round(detection.benign_probability, 6),
            malignant=round(detection.malignant_probability, 6),
        ),
        model_version=detection.model_version,
        original_filename=detection.original_filename,
        image_available=store.exists(detection.encrypted_image_path),
        created_at=detection.created_at,
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------
async def create_detection(
    db: OrmSession,
    user: User,
    image: Image.Image,
    *,
    original_filename: str,
    save_history: bool = True,
    idempotency_key: str | None = None,
    image_sha256: str | None = None,
    image_bytes: int | None = None,
    model_service: ModelService | None = None,
    store: EncryptedImageStore | None = None,
) -> tuple[DetectionOut, bool]:
    """Run a detection. Returns ``(result, created)``.

    ``created`` is False when an idempotent replay returned an existing record.
    """
    service = model_service or get_model_service()
    store = store or get_image_store()

    if idempotency_key:
        existing = db.scalar(
            select(Detection).where(
                Detection.user_id == user.id,
                Detection.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            LOGGER.info("idempotent replay for key=%s***", idempotency_key[:4])
            return detection_to_out(existing, store), False

    result = await service.predict(image)

    stored_path: str | None = None
    if save_history:
        stored_path, _digest = store.save(image, prefix="det_")

    detection = Detection(
        user_id=user.id,
        prediction=result.prediction,
        confidence=result.confidence,
        benign_probability=result.benign_probability,
        malignant_probability=result.malignant_probability,
        model_version=result.model_version,
        encrypted_image_path=stored_path,
        original_filename=original_filename[:255],
        image_sha256=image_sha256,
        image_bytes=image_bytes,
        image_width=image.width,
        image_height=image.height,
        inference_latency_ms=result.inference_latency_ms,
        idempotency_key=idempotency_key,
    )
    db.add(detection)
    try:
        db.commit()
    except IntegrityError:
        # concurrent replay with the same idempotency key won the race
        db.rollback()
        store.delete(stored_path)
        if idempotency_key:
            existing = db.scalar(
                select(Detection).where(
                    Detection.user_id == user.id,
                    Detection.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return detection_to_out(existing, store), False
        raise
    except Exception:
        db.rollback()
        store.delete(stored_path)  # no orphan files when the DB write fails
        raise
    db.refresh(detection)
    return detection_to_out(detection, store), True


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------
def list_detections(
    db: OrmSession,
    user: User,
    *,
    page: int = 1,
    page_size: int = 20,
    prediction: str | None = None,
    store: EncryptedImageStore | None = None,
) -> dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    filters = [Detection.user_id == user.id]
    if prediction in {"benign", "malignant"}:
        filters.append(Detection.prediction == prediction)

    total = db.scalar(select(func.count()).select_from(Detection).where(*filters)) or 0
    rows = db.scalars(
        select(Detection)
        .where(*filters)
        .order_by(Detection.created_at.desc(), Detection.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [detection_to_list_item(d, store) for d in rows]
    return {
        "items": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "pages": max(1, (int(total) + page_size - 1) // page_size) if total else 0,
    }


def get_detection(
    db: OrmSession, user: User, detection_id: int, store: EncryptedImageStore | None = None
) -> DetectionOut:
    """Fetch one detection; raises NotFoundError for foreign IDs (IDOR guard)."""
    detection = db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if detection is None:
        # Do not reveal whether the ID exists but belongs to someone else.
        raise NotFoundError("检测记录不存在")
    return detection_to_out(detection, store)


def get_detection_row(db: OrmSession, user: User, detection_id: int) -> Detection:
    detection = db.scalar(
        select(Detection).where(Detection.id == detection_id, Detection.user_id == user.id)
    )
    if detection is None:
        raise NotFoundError("检测记录不存在")
    return detection


def load_detection_image(
    db: OrmSession, user: User, detection_id: int, store: EncryptedImageStore | None = None
) -> bytes:
    """Decrypt a stored image after an ownership check."""
    store = store or get_image_store()
    detection = get_detection_row(db, user, detection_id)
    if not detection.encrypted_image_path:
        raise NotFoundError("该检测记录没有保存图片")
    return store.load(detection.encrypted_image_path)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def delete_detection(
    db: OrmSession, user: User, detection_id: int, store: EncryptedImageStore | None = None
) -> None:
    store = store or get_image_store()
    detection = get_detection_row(db, user, detection_id)
    path = detection.encrypted_image_path
    db.delete(detection)
    db.commit()
    if path:
        store.delete(path)


def collect_image_paths_for_user(db: OrmSession, user: User) -> list[str]:
    """Return the stored ciphertext paths owned by ``user`` (no deletion)."""
    return [
        row
        for row in db.scalars(
            select(Detection.encrypted_image_path).where(Detection.user_id == user.id)
        ).all()
        if row
    ]


def purge_image_paths(
    paths: list[str], store: EncryptedImageStore | None = None
) -> int:
    """Delete ciphertext files after their database rows are gone.

    Called *after* a successful commit: if the file removal fails the only
    consequence is an orphan file (cleaned up by the sweep), never a database
    row pointing at a missing image.
    """
    store = store or get_image_store()
    return sum(1 for path in paths if store.delete(path))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _csv_safe(value: Any) -> Any:
    """Neutralise spreadsheet formula injection.

    A filename such as ``=cmd|'/c calc'!A0`` becomes an executable formula when
    the exported CSV is opened in Excel/Sheets, so values starting with
    ``= + - @`` (or a tab/CR) are prefixed with an apostrophe.
    """
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value


def export_csv(
    db: OrmSession,
    user: User,
    *,
    prediction: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> str:
    filters = [Detection.user_id == user.id]
    if prediction in {"benign", "malignant"}:
        filters.append(Detection.prediction == prediction)
    if date_from:
        filters.append(Detection.created_at >= date_from)
    if date_to:
        filters.append(Detection.created_at <= date_to)

    rows = db.scalars(
        select(Detection).where(*filters).order_by(Detection.created_at.desc())
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.prediction,
                f"{row.confidence:.6f}",
                f"{row.benign_probability:.6f}",
                f"{row.malignant_probability:.6f}",
                _csv_safe(row.model_version),
                _csv_safe(row.original_filename),
                f"{row.inference_latency_ms:.2f}" if row.inference_latency_ms is not None else "",
            ]
        )
    # CSV contains no image data, only the recorded prediction metadata.
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
def sweep_orphan_images(
    db: OrmSession,
    store: EncryptedImageStore | None = None,
    *,
    min_age_seconds: int = 3600,
) -> int:
    store = store or get_image_store()
    known = {
        row
        for row in db.scalars(select(Detection.encrypted_image_path)).all()
        if row
    }
    return store.sweep_orphans(known, min_age_seconds=min_age_seconds)
