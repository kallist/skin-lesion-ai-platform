"""SQLAlchemy engine / session factory (SQLite by default)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from ..core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    path_part = url.split("///")[-1]
    if path_part in {"", ":memory:"}:
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)


def build_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    url = url or settings.database_url
    _ensure_sqlite_dir(url)
    connect_args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)
    if url.startswith("sqlite"):
        # WAL + foreign keys: durability and referential integrity for SQLite.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all(bind: Engine | None = None) -> None:
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=bind or engine)
