"""Security-focused tests: error contract, redaction, traversal, IDOR, headers."""

from __future__ import annotations

import io
import logging

import pytest

from .helpers import make_image_bytes

API = "/api/v1"


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("method", "path", "expected_status", "expected_code"),
    [
        ("get", f"{API}/users/me", 401, "UNAUTHENTICATED"),
        ("get", f"{API}/detections/999999", 401, "UNAUTHENTICATED"),
        ("get", "/api/v1/does-not-exist", 404, "NOT_FOUND"),
    ],
)
def test_error_contract_shape(app_client, method, path, expected_status, expected_code):
    response = getattr(app_client, method)(path)
    assert response.status_code == expected_status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == expected_code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]


def test_validation_error_contract(app_client, registered_user):
    response = app_client.get(f"{API}/detections", params={"page": 0})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["fields"]


def test_errors_never_leak_internals(app_client, registered_user):
    response = app_client.post(
        f"{API}/detections", files={"image": ("x.jpg", io.BytesIO(b"garbage"), "image/jpeg")}
    )
    text = response.text.lower()
    for forbidden in ("traceback", "sqlalchemy", "file \"", "/home/", "select ", "secret"):
        assert forbidden not in text


# ---------------------------------------------------------------------------
# Secret redaction in logs
# ---------------------------------------------------------------------------
def test_log_redaction_masks_secrets():
    from app.core.logging import RedactingFilter, redact

    samples = {
        "password=SuperSecret123": "SuperSecret123",
        "Authorization: Bearer abcdef123456": "abcdef123456",
        "session_secret: my-super-secret": "my-super-secret",
        "api_key=sk-live-1234567890": "sk-live-1234567890",
        "IMAGE_ENCRYPTION_KEY=Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWo=": "Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdoaWo=",
    }
    for raw, secret in samples.items():
        assert secret not in redact(raw)

    record = logging.LogRecord("t", logging.INFO, __file__, 1, "password=%s", ("hunter2",), None)
    assert RedactingFilter().filter(record) is True
    assert "hunter2" not in record.getMessage()


def test_logger_does_not_emit_image_bytes(caplog):
    from app.core.logging import redact

    blob = "A" * 400
    assert "A" * 400 not in redact(f"image data: {blob}")


def test_unhandled_exception_still_uses_json_error_contract(app_client):
    """A crash inside a route must not return a plain-text 500 or leak details."""
    from fastapi.testclient import TestClient

    app = app_client.app  # type: ignore[attr-defined]

    @app.get("/api/v1/_boom-for-test", include_in_schema=False)
    def _boom():  # pragma: no cover - only executed by this test
        raise RuntimeError("internal detail that must not leak")

    # raise_server_exceptions=False models a real server: the exception is
    # handled by the app's error handlers instead of propagating to the test.
    with TestClient(app, raise_server_exceptions=False) as raw_client:
        response = raw_client.get("/api/v1/_boom-for-test")
    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "internal detail" not in response.text
    assert "RuntimeError" not in response.text


def test_model_info_does_not_leak_paths_when_model_missing(app_client, monkeypatch):
    """/model/info must expose the exception type only, never a filesystem path."""
    from app.ml.model_service import get_model_service

    service = get_model_service()
    monkeypatch.setattr(service, "_backend", None, raising=False)
    monkeypatch.setattr(
        service,
        "_load_error",
        r"FileNotFoundError: Model file not found: C:\secret\path\best_model.pt",
        raising=False,
    )
    body = app_client.get(f"{API}/model/info").json()
    text = app_client.get(f"{API}/model/info").text
    assert body["available"] is False
    assert "C:" not in text
    assert "best_model.pt" not in text
    assert body.get("error") in (None, "FileNotFoundError")


def test_health_endpoint_does_not_leak_paths(app_client):
    text = app_client.get(f"{API}/health").text
    assert "C:" not in text and "\\\\" not in text
    assert "best_model.pt" not in text


# ---------------------------------------------------------------------------
# File handling
# ---------------------------------------------------------------------------
def _csrf_headers(app_client) -> dict[str, str]:
    return {"X-CSRF-Token": app_client.cookies.get("csrf_token") or ""}


def test_stored_filename_is_server_generated(app_client, registered_user, jpeg_bytes):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Detection

    response = app_client.post(
        f"{API}/detections",
        files={"image": ("../../../etc/passwd.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"save_history": "true"},
        headers=_csrf_headers(app_client),
    )
    assert response.status_code == 201
    with SessionLocal() as db:
        row = db.scalar(select(Detection).where(Detection.id == response.json()["id"]))
    assert row.encrypted_image_path is not None
    assert row.encrypted_image_path.endswith(".enc")
    assert "/" not in row.encrypted_image_path and "\\" not in row.encrypted_image_path
    assert "passwd" not in row.encrypted_image_path


def test_image_store_blocks_path_traversal(tmp_path):
    from app.services.image_store import EncryptedImageStore

    store = EncryptedImageStore(base_dir=tmp_path / "enc")
    with pytest.raises(ValueError):
        store._resolve("../../../windows/win.ini")  # noqa: SLF001
    # a plain name still resolves inside the base directory
    assert store._resolve("abc.enc").parent == (tmp_path / "enc").resolve()  # noqa: SLF001


def test_images_are_encrypted_on_disk(app_client, registered_user, jpeg_bytes):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import Detection
    from app.services.image_store import get_image_store

    detection_id = app_client.post(
        f"{API}/detections",
        files={"image": ("a.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
        data={"save_history": "true"},
        headers=_csrf_headers(app_client),
    ).json()["id"]

    with SessionLocal() as db:
        row = db.scalar(select(Detection).where(Detection.id == detection_id))
        path = get_image_store().base_dir / row.encrypted_image_path

    raw = path.read_bytes()
    # ciphertext must not contain the JPEG magic bytes or the original pixels
    assert not raw.startswith(b"\xff\xd8")
    assert b"\xff\xd8\xff" not in raw[:64]
    assert raw != jpeg_bytes


def test_exif_metadata_is_stripped(app_client, registered_user):
    """An image with EXIF must be stored without it."""
    import io as _io

    from PIL import Image

    image = Image.new("RGB", (48, 48), (10, 200, 10))
    exif = image.getexif()
    exif[0x010E] = "secret description"
    buffer = _io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)

    detection_id = app_client.post(
        f"{API}/detections",
        files={"image": ("exif.jpg", _io.BytesIO(buffer.getvalue()), "image/jpeg")},
        data={"save_history": "true"},
        headers=_csrf_headers(app_client),
    ).json()["id"]

    decrypted = app_client.get(f"{API}/detections/{detection_id}/image").content
    with Image.open(_io.BytesIO(decrypted)) as stored:
        assert not stored.getexif()


# ---------------------------------------------------------------------------
# Session / CSRF
# ---------------------------------------------------------------------------
def test_session_cookie_is_httponly(app_client, user_credentials):
    response = app_client.post(f"{API}/auth/register", json=user_credentials)
    header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header or "samesite=lax" in header.lower()


def test_invalid_session_cookie_is_rejected(app_client):
    app_client.cookies.set("skin_session", "not-a-real-token")
    assert app_client.get(f"{API}/users/me").status_code == 401


def test_csrf_token_mismatch_is_rejected(app_client, registered_user):
    response = app_client.patch(
        f"{API}/users/me", json={"full_name": "x"}, headers={"X-CSRF-Token": "wrong"}
    )
    assert response.status_code == 403


def test_cors_headers_for_configured_origin(app_client):
    response = app_client.get(
        f"{API}/health", headers={"Origin": "http://localhost:5173"}
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_does_not_allow_unknown_origin(app_client):
    response = app_client.get(f"{API}/health", headers={"Origin": "http://evil.example"})
    assert response.headers.get("access-control-allow-origin") != "http://evil.example"


# ---------------------------------------------------------------------------
# Encryption key handling
# ---------------------------------------------------------------------------
def test_invalid_encryption_key_is_rejected(tmp_path, monkeypatch):
    from app.core.config import get_settings
    from app.services.image_store import EncryptedImageStore

    settings = get_settings()
    monkeypatch.setattr(settings, "image_encryption_key", "not-a-valid-fernet-key", raising=False)
    with pytest.raises(Exception) as excinfo:
        EncryptedImageStore(base_dir=tmp_path / "e", key="not-a-valid-fernet-key")
    assert "IMAGE_ENCRYPTION_KEY" in str(excinfo.value)


def test_ciphertext_cannot_be_decrypted_with_another_key(tmp_path):
    from cryptography.fernet import Fernet
    from PIL import Image

    from app.services.image_store import EncryptedImageStore

    key_a, key_b = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    store_a = EncryptedImageStore(base_dir=tmp_path / "a", key=key_a)
    name, _digest = store_a.save(Image.new("RGB", (8, 8), (1, 2, 3)))
    store_b = EncryptedImageStore(base_dir=tmp_path / "a", key=key_b)
    with pytest.raises(Exception):
        store_b.load(name)


# ---------------------------------------------------------------------------
# Password storage
# ---------------------------------------------------------------------------
def test_password_hash_uses_argon2id(app_client, user_credentials):
    from sqlalchemy import select

    from app.db.base import SessionLocal
    from app.db.models import User

    app_client.post(f"{API}/auth/register", json=user_credentials)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == user_credentials["email"]))
    assert user.password_hash.startswith("$argon2id$")


def test_password_never_returned_by_api(app_client, registered_user, user_credentials):
    response = app_client.get(f"{API}/users/me")
    assert "password" not in response.text.lower()
    assert user_credentials["password"] not in response.text


def test_concurrent_registration_conflict_is_handled(app_client, user_credentials):
    assert app_client.post(f"{API}/auth/register", json=user_credentials).status_code == 201
    second = app_client.post(f"{API}/auth/register", json=user_credentials)
    assert second.status_code == 409
