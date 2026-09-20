"""FastAPI dependencies: DB session, current user, CSRF."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session as OrmSession

from ..core.config import Settings, get_settings
from ..core.errors import UnauthenticatedError
from ..db import get_db
from ..db.models import Session as SessionModel
from ..db.models import User
from ..services import auth_service

DbSession = Annotated[OrmSession, Depends(get_db)]


def get_session_token(request: Request, settings: Settings = Depends(get_settings)) -> str | None:
    return request.cookies.get(settings.session_cookie_name)


def get_client_ip(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Client address used for login rate limiting.

    Behind the nginx reverse proxy ``request.client.host`` is the proxy itself,
    which would collapse every user into one rate-limit bucket.  uvicorn is
    therefore started with ``--proxy-headers`` so that ``request.client`` is
    already the real peer; ``X-Forwarded-For`` is used only as a fallback.
    """
    if request.client and request.client.host:
        host = request.client.host
        # When uvicorn trusts the proxy, client.host is already rewritten; if it
        # still looks like a private proxy address, prefer the first forwarded hop.
        if host not in {"127.0.0.1", "::1", "localhost"}:
            return host
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def get_current_session(
    request: Request,
    db: DbSession,
    token: Annotated[str | None, Depends(get_session_token)],
) -> SessionModel:
    if not token:
        raise UnauthenticatedError()
    session = auth_service.resolve_session(db, token)
    if session is None:
        raise UnauthenticatedError("登录状态已失效，请重新登录")
    if not session.user or not session.user.is_active:
        raise UnauthenticatedError()
    return session


def get_current_user(session: Annotated[SessionModel, Depends(get_current_session)]) -> User:
    return session.user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSession = Annotated[SessionModel, Depends(get_current_session)]


def require_csrf(
    session: CurrentSession,
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """Dependency for cookie-authenticated state-changing endpoints."""
    auth_service.verify_csrf(session, csrf_token)


CsrfProtected = Annotated[None, Depends(require_csrf)]
