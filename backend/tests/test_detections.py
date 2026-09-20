"""Detection API tests: valid/invalid uploads, history, ownership, export."""

from __future__ import annotations

import io

import pytest

from .helpers import (
    make_bmp_bytes,
    make_broken_jpeg,
    make_fake_png_header,
    make_image_bytes,
    make_large_pixel_png,
)

API = "/api/v1"


def _detect(client, data: bytes, filename: str = "lesion.jpg", **kwargs):
    """POST an image to the detection endpoint.

    ``kwargs`` may contain ``save_history`` (form field) and ``headers``.
    The CSRF header is supplied automatically from the client cookie jar,
    matching what the browser client does.
    """
    save_history = kwargs.pop("save_history", "true")
    headers = dict(kwargs.pop("headers", None) or {})
    csrf = client.cookies.get("csrf_token")
    if csrf and "X-CSRF-Token" not in headers:
        headers["X-CSRF-Token"] = csrf
    return client.post(
        f"{API}/detections",
        files={"image": (filename, io.BytesIO(data), "image/jpeg")},
        data={"save_history": save_history},
        headers=headers or None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
def test_detect_jpeg_success(app_client, registered_user, jpeg_bytes):
    response = _detect(app_client, jpeg_bytes)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["prediction"] in {"benign", "malignant"}
    assert 0.0 <= body["confidence"] <= 1.0
    probs = body["probabilities"]
    assert probs["benign"] + probs["malignant"] == pytest.approx(1.0, abs=1e-4)
    assert body["model_version"]
    assert "不能替代专业医生诊断" in body["disclaimer"]
    assert body["advice"]
    assert body["image_available"] is True


def test_detect_png_success(app_client, registered_user, png_bytes):
    response = _detect(app_client, png_bytes, filename="lesion.png")
    assert response.status_code == 201, response.text


def test_detect_bmp_success(app_client, registered_user):
    response = _detect(app_client, make_bmp_bytes(), filename="lesion.bmp")
    assert response.status_code == 201


def test_detect_without_history(app_client, registered_user, jpeg_bytes):
    response = _detect(app_client, jpeg_bytes, save_history="false")
    assert response.status_code == 201
    assert response.json()["image_available"] is False
    listing = app_client.get(f"{API}/detections").json()
    assert listing["total"] == 1


def test_detect_requires_authentication(app_client, jpeg_bytes):
    response = app_client.post(
        f"{API}/detections",
        files={"image": ("a.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
    )
    assert response.status_code == 401


def test_detect_requires_csrf_token(app_client, registered_user, jpeg_bytes):
    """A cookie-authenticated multipart POST must be CSRF protected.

    Regression test: the upload endpoint previously accepted any cross-site
    multipart POST because the CSRF dependency was missing.
    """
    response = app_client.post(
        f"{API}/detections",
        files={"image": ("a.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"save_history": "true"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    # nothing was created
    assert app_client.get(f"{API}/detections").json()["total"] == 0


def test_detect_rejects_wrong_csrf_token(app_client, registered_user, jpeg_bytes):
    response = _detect(app_client, jpeg_bytes, headers={"X-CSRF-Token": "not-the-token"})
    assert response.status_code == 403
    assert app_client.get(f"{API}/detections").json()["total"] == 0


# ---------------------------------------------------------------------------
# Invalid uploads
# ---------------------------------------------------------------------------
def test_detect_rejects_invalid_image(app_client, registered_user):
    response = _detect(app_client, b"this is definitely not an image", "x.jpg")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


def test_detect_rejects_truncated_jpeg(app_client, registered_user):
    response = _detect(app_client, make_broken_jpeg(), "broken.jpg")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_IMAGE"


def test_detect_rejects_fake_mime(app_client, registered_user):
    """A .png extension with a fake PNG header must be rejected after decoding."""
    response = _detect(app_client, make_fake_png_header(), "fake.png")
    assert response.status_code in {400, 422}
    assert response.json()["error"]["code"] in {"INVALID_IMAGE", "UNSUPPORTED_IMAGE_TYPE"}


def test_detect_rejects_unsupported_extension(app_client, registered_user, jpeg_bytes):
    response = _detect(app_client, jpeg_bytes, "lesion.gif")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_IMAGE_TYPE"


def test_detect_rejects_oversized_file(app_client, registered_user):
    payload = b"\x00" * (11 * 1024 * 1024)
    response = _detect(app_client, payload, "huge.jpg")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_detect_rejects_decompression_bomb(app_client, registered_user):
    response = _detect(app_client, make_large_pixel_png(), "bomb.png")
    assert response.status_code in {400, 413}
    assert response.json()["error"]["code"] in {"FILE_TOO_LARGE", "INVALID_IMAGE"}


def test_validate_upload_rejects_real_png_bomb(monkeypatch, tmp_path):
    """A genuinely decodable high-pixel-count PNG must be rejected.

    Unlike the header-only fixture above this file really contains pixels, so
    the check that fires is the pixel-count / Pillow guard rather than a
    truncated-file error.
    """
    import io as _io

    from PIL import Image

    from app.core.config import get_settings
    from app.services.image_store import validate_upload

    settings = get_settings()
    monkeypatch.setattr(settings, "max_image_pixels", 200_000, raising=False)

    # 1000x1000 = 1,000,000 pixels > 200,000 limit, fully decodable
    buffer = _io.BytesIO()
    Image.new("RGB", (1000, 1000), (30, 60, 90)).save(buffer, format="PNG")
    with pytest.raises(Exception) as excinfo:
        validate_upload(buffer.getvalue(), "bomb.png")
    message = str(excinfo.value)
    assert "像素" in message or "图片" in message


def test_detect_rejects_empty_file(app_client, registered_user):
    response = _detect(app_client, b"", "empty.jpg")
    assert response.status_code == 400


def test_detect_rejects_path_traversal_filename(app_client, registered_user, jpeg_bytes):
    """A hostile filename must not influence the stored path."""
    response = _detect(app_client, jpeg_bytes, "../../evil.jpg")
    assert response.status_code == 201
    detection_id = response.json()["id"]
    detail = app_client.get(f"{API}/detections/{detection_id}").json()
    assert ".." not in detail["original_filename"]
    assert "/" not in detail["original_filename"]


# ---------------------------------------------------------------------------
# History / ownership
# ---------------------------------------------------------------------------
def test_history_creation_and_listing(app_client, registered_user, jpeg_bytes):
    for _ in range(3):
        assert _detect(app_client, jpeg_bytes).status_code == 201
    listing = app_client.get(f"{API}/detections").json()
    assert listing["total"] == 3
    assert len(listing["items"]) == 3
    assert listing["items"][0]["id"] > listing["items"][-1]["id"]  # newest first


def test_history_filter_by_prediction(app_client, registered_user, jpeg_bytes):
    _detect(app_client, jpeg_bytes)
    full = app_client.get(f"{API}/detections").json()
    prediction = full["items"][0]["prediction"]
    filtered = app_client.get(f"{API}/detections", params={"prediction": prediction}).json()
    assert filtered["total"] == 1
    other = "benign" if prediction == "malignant" else "malignant"
    assert app_client.get(f"{API}/detections", params={"prediction": other}).json()["total"] == 0


def test_history_pagination(app_client, registered_user, jpeg_bytes):
    for _ in range(5):
        _detect(app_client, jpeg_bytes)
    page1 = app_client.get(f"{API}/detections", params={"page": 1, "page_size": 2}).json()
    page2 = app_client.get(f"{API}/detections", params={"page": 2, "page_size": 2}).json()
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert {item["id"] for item in page1["items"]} & {item["id"] for item in page2["items"]} == set()


def test_history_ownership_isolation(app_client, registered_user, user_credentials, jpeg_bytes):
    """User B must not be able to read user A's detection (IDOR guard)."""
    created = _detect(app_client, jpeg_bytes).json()
    detection_id = created["id"]
    app_client.post(f"{API}/auth/logout")

    bob = {
        "email": "bob@example.com",
        "username": "bob",
        "password": "An0therPass!",
    }
    assert app_client.post(f"{API}/auth/register", json=bob).status_code == 201

    assert app_client.get(f"{API}/detections/{detection_id}").status_code == 404
    assert app_client.get(f"{API}/detections/{detection_id}/image").status_code == 404
    assert app_client.delete(
        f"{API}/detections/{detection_id}", headers={"X-CSRF-Token": app_client.cookies.get("csrf_token")}
    ).status_code == 404
    assert app_client.get(f"{API}/detections").json()["total"] == 0


def test_history_image_requires_authentication(app_client, registered_user, jpeg_bytes):
    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    app_client.post(f"{API}/auth/logout")
    assert app_client.get(f"{API}/detections/{detection_id}/image").status_code == 401


def test_history_image_is_decryptable_png(app_client, registered_user, jpeg_bytes):
    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    response = app_client.get(f"{API}/detections/{detection_id}/image")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    from PIL import Image

    with Image.open(io.BytesIO(response.content)) as image:
        assert image.size == (64, 64)


def test_history_delete_removes_record_and_image(app_client, registered_user, jpeg_bytes):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Detection
    from app.services.image_store import get_image_store

    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    with SessionLocal() as db:
        row = db.scalar(select(Detection).where(Detection.id == detection_id))
        stored = row.encrypted_image_path
    assert get_image_store().exists(stored)

    response = app_client.delete(
        f"{API}/detections/{detection_id}",
        headers={"X-CSRF-Token": app_client.cookies.get("csrf_token")},
    )
    assert response.status_code == 200
    assert app_client.get(f"{API}/detections/{detection_id}").status_code == 404
    assert not get_image_store().exists(stored)


def test_delete_requires_csrf(app_client, registered_user, jpeg_bytes):
    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    assert app_client.delete(f"{API}/detections/{detection_id}").status_code == 403


def test_account_deletion_commits_before_removing_files(app_client, registered_user, jpeg_bytes):
    """Files must be removed only after the account rows are committed."""
    from app.services import detection_service, user_service
    from app.services.image_store import get_image_store

    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    store = get_image_store()
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Detection

    with SessionLocal() as db:
        row = db.scalar(select(Detection).where(Detection.id == detection_id))
        stored = row.encrypted_image_path
    assert store.exists(stored)

    order: list[str] = []
    original_commit = detection_service.OrmSession.commit
    original_purge = detection_service.purge_image_paths

    def tracked_commit(self):  # noqa: ANN001
        order.append("commit")
        return original_commit(self)

    def tracked_purge(paths, *args, **kwargs):  # noqa: ANN001
        order.append("purge_files")
        return original_purge(paths, *args, **kwargs)

    detection_service.OrmSession.commit = tracked_commit
    detection_service.purge_image_paths = tracked_purge
    try:
        response = app_client.delete(
            f"{API}/users/me", headers={"X-CSRF-Token": app_client.cookies.get("csrf_token")}
        )
    finally:
        detection_service.OrmSession.commit = original_commit
        detection_service.purge_image_paths = original_purge

    assert response.status_code == 200
    assert order == ["commit", "purge_files"], f"wrong ordering: {order}"
    assert not store.exists(stored)
    assert app_client.get(f"{API}/users/me").status_code == 401


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def test_csv_export_contains_required_columns(app_client, registered_user, jpeg_bytes):
    _detect(app_client, jpeg_bytes)
    response = app_client.get(f"{API}/detections/export")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8")
    header = text.splitlines()[0]
    for column in (
        "created_at",
        "prediction",
        "confidence",
        "benign_probability",
        "malignant_probability",
        "model_version",
    ):
        assert column in header
    # no image payloads in the CSV
    assert len(text) < 5000


def test_csv_export_requires_authentication(app_client):
    assert app_client.get(f"{API}/detections/export").status_code == 401


def test_csv_export_is_scoped_to_the_user(app_client, registered_user, jpeg_bytes):
    _detect(app_client, jpeg_bytes)
    app_client.post(f"{API}/auth/logout")
    app_client.post(
        f"{API}/auth/register",
        json={"email": "carol@example.com", "username": "carol", "password": "C0ralPass!"},
    )
    text = app_client.get(f"{API}/detections/export").content.decode("utf-8")
    assert len(text.strip().splitlines()) == 1  # header only


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
def test_idempotency_key_prevents_duplicate_records(app_client, registered_user, jpeg_bytes):
    key = "idem-key-0001"
    first = _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": key})
    second = _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": key})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert app_client.get(f"{API}/detections").json()["total"] == 1


def test_idempotency_is_scoped_per_user(app_client, registered_user, jpeg_bytes):
    key = "shared-key"
    first = _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": key}).json()
    app_client.post(f"{API}/auth/logout")
    app_client.post(
        f"{API}/auth/register",
        json={"email": "dave@example.com", "username": "dave", "password": "Dav3Pass!!"},
    )
    second = _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": key}).json()
    assert second["id"] != first["id"]


def test_different_keys_create_separate_records(app_client, registered_user, jpeg_bytes):
    _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": "k1"})
    _detect(app_client, jpeg_bytes, headers={"Idempotency-Key": "k2"})
    assert app_client.get(f"{API}/detections").json()["total"] == 2


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------
def test_model_unavailable_returns_503(app_client, registered_user, jpeg_bytes, monkeypatch):
    from app.ml.model_service import get_model_service

    service = get_model_service()
    service._backend = None  # noqa: SLF001 - simulate a missing/broken checkpoint
    response = _detect(app_client, jpeg_bytes)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODEL_UNAVAILABLE"


def test_inference_failure_returns_500(app_client, registered_user, jpeg_bytes, monkeypatch):
    from app.ml.model_service import get_model_service

    service = get_model_service()

    class Boom:
        name = "boom"
        model_version = "boom"

        def predict(self, image):  # noqa: ANN001
            raise RuntimeError("tensor exploded")

        @property
        def info(self):
            return {"model_version": "boom", "available": True}

    service._backend = Boom()  # noqa: SLF001
    response = _detect(app_client, jpeg_bytes)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INFERENCE_FAILED"
    # no traceback leaked to the client
    assert "tensor exploded" not in response.text


def test_database_failure_rolls_back_image(app_client, registered_user, jpeg_bytes, monkeypatch):
    """If the DB commit fails, the just-written encrypted file must be removed."""
    from sqlalchemy.exc import OperationalError

    from app.services import detection_service
    from app.services.image_store import get_image_store

    store = get_image_store()
    before = len(list(store.base_dir.glob("*.enc")))

    original_commit = detection_service.OrmSession.commit

    def boom(self):  # noqa: ANN001
        raise OperationalError("INSERT", {}, Exception("database is locked"))

    monkeypatch.setattr(detection_service.OrmSession, "commit", boom, raising=False)
    with pytest.raises(Exception):
        _detect(app_client, jpeg_bytes)
    monkeypatch.setattr(detection_service.OrmSession, "commit", original_commit, raising=False)

    after = len(list(store.base_dir.glob("*.enc")))
    assert after == before, "orphaned encrypted image left behind after DB failure"


def test_orphan_sweep_removes_unreferenced_files(app_client, registered_user, jpeg_bytes):
    from app.db.base import SessionLocal
    from app.services.detection_service import sweep_orphan_images
    from app.services.image_store import get_image_store

    store = get_image_store()
    orphan = store.base_dir / "orphan-abc123.enc"
    orphan.write_bytes(b"leftover ciphertext")
    assert orphan.exists()
    with SessionLocal() as db:
        # min_age_seconds=0 so the freshly created file is eligible
        removed = sweep_orphan_images(db, store, min_age_seconds=0)
    assert removed >= 1
    assert not orphan.exists()


def test_missing_encrypted_image_is_reported(app_client, registered_user, jpeg_bytes):
    detection_id = _detect(app_client, jpeg_bytes).json()["id"]
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Detection
    from app.services.image_store import get_image_store

    store = get_image_store()
    with SessionLocal() as db:
        row = db.scalar(select(Detection).where(Detection.id == detection_id))
        store.delete(row.encrypted_image_path)

    response = app_client.get(f"{API}/detections/{detection_id}/image")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "STORAGE_ERROR"
    detail = app_client.get(f"{API}/detections/{detection_id}").json()
    assert detail["image_available"] is False


def test_health_endpoint(app_client):
    response = app_client.get(f"{API}/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] is True


def test_model_info_endpoint(app_client):
    body = app_client.get(f"{API}/model/info").json()
    assert body["input_size"] == 224
    assert body["class_mapping"] == {"benign": 0, "malignant": 1}
    assert "不构成医学诊断" in body["disclaimer"]


def test_security_headers_present(app_client):
    response = app_client.get(f"{API}/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_unknown_detection_returns_404(app_client, registered_user):
    assert app_client.get(f"{API}/detections/999999").status_code == 404
