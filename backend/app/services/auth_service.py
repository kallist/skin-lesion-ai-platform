"""Authentication service: registration, login, sessions, logout."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from ..core.config import get_settings
from ..core.errors import ConflictError, ForbiddenError, RateLimitedError, UnauthenticatedError
from ..core.security import (
    constant_time_equals,
    hash_password,
    hash_token,
    new_csrf_token,
    new_session_token,
    password_strength_error,
    verify_password,
)
from ..db.models import Session, User

LOGGER = logging.getLogger("app.auth")

# Pre-computed Argon2 hash used to keep the verification timing of an unknown
# account comparable to a wrong password.  Computing it once at import time
# avoids paying ~64 MiB / 3 rounds of Argon2 on every failed login attempt,
# which would otherwise be a cheap resource-exhaustion vector.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-equalisation")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class LoginRateLimiter:
    """Small in-process sliding-window limiter for login attempts.

    Deliberately simple: it protects a single-process deployment without adding
    Redis (explicitly out of scope for this project).
    """

    def __init__(self) -> None:
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        settings = get_settings()
        now = utcnow().timestamp()
        window = settings.login_window_seconds
        attempts = [t for t in self._attempts.get(key, []) if now - t < window]
        self._attempts[key] = attempts
        if len(attempts) >= settings.login_max_attempts:
            raise RateLimitedError("登录尝试过于频繁，请稍后再试")

    def record_failure(self, key: str) -> None:
        self._attempts.setdefault(key, []).append(utcnow().timestamp())

    def reset(self, key: str) -> None:
        self._attempts.pop(key, None)


login_limiter = LoginRateLimiter()


# ---------------------------------------------------------------------------
# Registration / login
# ---------------------------------------------------------------------------
def register_user(
    db: OrmSession,
    *,
    email: str,
    username: str,
    password: str,
    full_name: str | None = None,
) -> User:
    settings = get_settings()
    if not settings.allow_registration:
        raise ForbiddenError("当前系统已关闭注册功能")

    error = password_strength_error(password, settings.password_min_length)
    if error:
        raise ConflictError(error, details={"field": "password"})

    email = email.strip().lower()
    username = username.strip()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise ConflictError("该邮箱已被注册", details={"field": "email"})
    existing = db.scalar(select(User).where(User.username == username))
    if existing:
        raise ConflictError("该用户名已被占用", details={"field": "username"})

    user = User(
        email=email,
        username=username,
        password_hash=hash_password(password),
        full_name=(full_name or None),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # concurrent duplicate registration
        db.rollback()
        LOGGER.info("duplicate registration blocked by unique constraint")
        raise ConflictError("该邮箱或用户名已被注册") from exc
    db.refresh(user)
    LOGGER.info("user registered id=%s", user.id)
    return user


def authenticate(db: OrmSession, *, identifier: str, password: str, client_key: str) -> User:
    login_limiter.check(client_key)
    identifier = identifier.strip()
    user = db.scalar(
        select(User).where(
            (User.email == identifier.lower()) | (User.username == identifier)
        )
    )
    # Always run a verification to keep the timing profile similar for
    # unknown users and wrong passwords.
    reference_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
    ok = verify_password(password, reference_hash)
    if not user or not ok or not user.is_active:
        login_limiter.record_failure(client_key)
        LOGGER.info("failed login attempt for identifier=%s", identifier[:3] + "***")
        raise UnauthenticatedError("邮箱/用户名或密码错误")
    login_limiter.reset(client_key)
    return user


def create_session(
    db: OrmSession, user: User, *, user_agent: str | None = None
) -> tuple[str, str, Session]:
    """Create a session row; returns ``(raw_token, csrf_token, session)``."""
    settings = get_settings()
    token = new_session_token()
    csrf = new_csrf_token()
    session = Session(
        user_id=user.id,
        token_hash=hash_token(token),
        csrf_token_hash=hash_token(csrf),
        user_agent=(user_agent or "")[:255] or None,
        expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return token, csrf, session


def resolve_session(db: OrmSession, token: str) -> Session | None:
    if not token:
        return None
    session = db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if session is None:
        return None
    if session.revoked_at is not None:
        return None
    if _as_aware(session.expires_at) <= utcnow():
        return None
    return session


def revoke_session(db: OrmSession, session: Session) -> None:
    session.revoked_at = utcnow()
    db.commit()


def revoke_all_sessions(db: OrmSession, user: User) -> int:
    sessions = db.scalars(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = utcnow()
    db.commit()
    return len(sessions)


def verify_csrf(session: Session, provided: str | None) -> None:
    """Double-submit CSRF check for cookie-authenticated state changes."""
    if not provided:
        raise ForbiddenError("缺少 CSRF 令牌")
    if not constant_time_equals(hash_token(provided), session.csrf_token_hash):
        raise ForbiddenError("CSRF 令牌无效，请刷新页面后重试")


def purge_expired_sessions(db: OrmSession) -> int:
    sessions = db.scalars(select(Session).where(Session.expires_at <= utcnow())).all()
    for session in sessions:
        db.delete(session)
    if sessions:
        db.commit()
    return len(sessions)
