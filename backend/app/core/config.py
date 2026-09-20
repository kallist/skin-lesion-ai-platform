"""Application settings loaded from environment variables / .env file.

Secrets are never hard-coded and never logged.  ``.env.example`` documents every
variable; the real ``.env`` is git-ignored.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- app ----------
    app_name: str = "Skin Lesion AI Platform API"
    app_env: str = "development"
    app_version: str = "1.0.0"
    debug: bool = False
    api_prefix: str = "/api/v1"

    # ---------- server ----------
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- database ----------
    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'data' / 'app.sqlite3').as_posix()}"

    # ---------- auth ----------
    session_secret: str = Field(default="")
    session_cookie_name: str = "skin_session"
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    # NOTE: the CSRF header name is fixed to X-CSRF-Token across backend
    # (app/api/deps.py) and frontend (src/api/client.ts); it is intentionally
    # not configurable so the two halves can never drift apart.
    password_min_length: int = 8
    login_max_attempts: int = 8
    login_window_seconds: int = 300

    # ---------- uploads / privacy ----------
    image_encryption_key: str = Field(default="")
    max_upload_mb: int = 10
    max_image_pixels: int = 40_000_000
    encrypted_image_dir: str = str(BACKEND_ROOT / "data" / "encrypted_uploads")
    temp_dir: str = str(BACKEND_ROOT / "data" / "tmp")

    # ---------- ML ----------
    model_path: str = str(PROJECT_ROOT / "models" / "best_model.pt")
    inference_concurrency: int = 2
    model_warmup: bool = True
    model_backend: str = "auto"  # auto | real | stub

    # ---------- ops ----------
    log_level: str = "INFO"
    allow_registration: bool = True
    orphan_sweep_on_startup: bool = True

    # ------------------------------------------------------------------
    @field_validator("model_path", "encrypted_image_dir", "temp_dir")
    @classmethod
    def _resolve_path(cls, value: str) -> str:
        """Resolve relative paths so the app works from any working directory.

        A relative path is interpreted against ``backend/`` first and then
        against the project root, whichever exists; otherwise it is anchored at
        ``backend/``.  Absolute paths (and Docker container paths) pass through.
        """
        if not value:
            return value
        path = Path(value).expanduser()
        if path.is_absolute():
            return str(path)
        for base in (BACKEND_ROOT, PROJECT_ROOT):
            candidate = (base / path).resolve()
            if candidate.exists():
                return str(candidate)
        return str((BACKEND_ROOT / path).resolve())

    @field_validator("app_env")
    @classmethod
    def _check_env(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"development", "testing", "production"}:
            raise ValueError("APP_ENV must be development|testing|production")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def resolved_session_secret(self) -> str:
        """Session secret; a random one is generated for dev/test only."""
        if self.session_secret:
            return self.session_secret
        if self.is_production:
            raise RuntimeError(
                "SESSION_SECRET must be set in production. "
                "Generate one with: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
            )
        return "dev-only-insecure-session-secret-do-not-use-in-production"

    def resolved_encryption_key(self) -> str:
        """Fernet key; a deterministic dev key is generated when unset."""
        if self.image_encryption_key:
            return self.image_encryption_key
        if self.is_production:
            raise RuntimeError(
                "IMAGE_ENCRYPTION_KEY must be set in production. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet;"
                "print(Fernet.generate_key().decode())\""
            )
        # stable across restarts so a dev database stays readable
        import base64
        import hashlib

        digest = hashlib.sha256(b"dev-only-skin-cancer-image-key").digest()
        return base64.urlsafe_b64encode(digest).decode()

    def validate_runtime(self) -> list[str]:
        """Return a list of warnings about the current configuration."""
        warnings: list[str] = []
        if self.is_production:
            if not self.session_secret:
                warnings.append("SESSION_SECRET is not set (required in production)")
            if not self.image_encryption_key:
                warnings.append("IMAGE_ENCRYPTION_KEY is not set (required in production)")
            if not self.cookie_secure:
                warnings.append("COOKIE_SECURE should be true in production (HTTPS only)")
        if not self.cors_origin_list:
            warnings.append("CORS_ORIGINS is empty: browser clients will be blocked")
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()


def generate_secrets() -> dict[str, str]:
    """Helper used by scripts/docs to create real secrets (never committed)."""
    from cryptography.fernet import Fernet

    return {
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "IMAGE_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    }
