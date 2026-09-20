"""Pytest fixtures: isolated app instance, temp database, test client."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for path in (str(PROJECT_ROOT), str(BACKEND_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope="session", autouse=True)
def _isolated_env() -> None:
    """Point the app at throwaway storage for the whole test session."""
    tmp = Path(tempfile.mkdtemp(prefix="skin-tests-"))
    os.environ.update(
        {
            "APP_ENV": "testing",
            "DATABASE_URL": f"sqlite:///{(tmp / 'test.sqlite3').as_posix()}",
            "ENCRYPTED_IMAGE_DIR": str(tmp / "encrypted"),
            "TEMP_DIR": str(tmp / "tmp"),
            "MODEL_BACKEND": os.environ.get("MODEL_BACKEND", "stub"),
            # the deterministic stub must be loaded so the API tests can run
            # without torch; individual tests override the backend when needed
            "MODEL_WARMUP": "true",
            "SESSION_SECRET": "test-session-secret-not-used-in-production",
            "COOKIE_SECURE": "false",
            "LOGIN_MAX_ATTEMPTS": "1000",
            "ORPHAN_SWEEP_ON_STARTUP": "false",
            "MAX_UPLOAD_MB": "10",
            "CORS_ORIGINS": "http://localhost:5173",
        }
    )
    yield
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def app_client(_isolated_env):
    """A fresh FastAPI TestClient with a freshly created schema."""
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.db.base import Base, build_engine
    from app.main import create_app
    from app.ml.model_service import reset_model_service
    from app.services.image_store import reset_image_store

    get_settings.cache_clear()
    reset_model_service()
    reset_image_store()

    settings = get_settings()
    engine = build_engine(settings.database_url)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # make the app use the same engine
    import app.db.base as db_base

    db_base.engine = engine
    from sqlalchemy.orm import sessionmaker

    db_base.SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    app = create_app()
    with TestClient(app) as client:
        client.app = app  # type: ignore[attr-defined]  # let tests inspect routes
        yield client

    reset_model_service()
    reset_image_store()


@pytest.fixture()
def user_credentials() -> dict[str, str]:
    return {
        "email": "alice@example.com",
        "username": "alice",
        "password": "Str0ngPass!",
        "full_name": "Alice Tester",
    }


@pytest.fixture()
def registered_user(app_client, user_credentials):
    response = app_client.post("/api/v1/auth/register", json=user_credentials)
    assert response.status_code == 201, response.text
    return response.json()


def make_image_bytes(width: int = 64, height: int = 64, fmt: str = "JPEG", color=(180, 120, 90)) -> bytes:
    """Create a real, decodable image in memory."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture()
def jpeg_bytes() -> bytes:
    return make_image_bytes()


@pytest.fixture()
def png_bytes() -> bytes:
    return make_image_bytes(fmt="PNG")
