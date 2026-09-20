"""Database bootstrap helpers."""

from __future__ import annotations

import logging

from sqlalchemy import text

from .base import Base, SessionLocal, build_engine, create_all, engine, get_db  # noqa: F401
from .models import Detection, Session, User  # noqa: F401

LOGGER = logging.getLogger("app.db")


def init_db() -> None:
    """Create tables and required indexes if they do not exist."""
    create_all()
    LOGGER.info("database ready: %s", engine.url.render_as_string(hide_password=True))


def healthcheck() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("database healthcheck failed: %s", type(exc).__name__)
        return False


def table_names() -> list[str]:
    from sqlalchemy import inspect

    return sorted(inspect(engine).get_table_names())
