"""Auth endpoints: register / login / logout / session info."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from ...core.config import get_settings
from ...core.errors import UnauthenticatedError
from ...db.models import User
from ...schemas import AuthResponse, LoginRequest, MessageOut, RegisterRequest, UserOut
from ...services import auth_service
from ..deps import CurrentSession, CurrentUser, DbSession, get_client_ip, get_session_token
from typing import Annotated

from fastapi import Depends

LOGGER = logging.getLogger("app.api.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, token: str, csrf: str) -> None:
    settings = get_settings()
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )
    # CSRF token is readable by JS on purpose (double-submit pattern); it is
    # useless without the HttpOnly session cookie.
    response.set_cookie(
        key="csrf_token",
        value=csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie("csrf_token", path="/")


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> AuthResponse:
    user = auth_service.register_user(
        db,
        email=payload.email,
        username=payload.username,
        password=payload.password,
        full_name=payload.full_name,
    )
    token, csrf, _session = auth_service.create_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookies(response, token, csrf)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf, message="注册成功")


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: DbSession,
) -> AuthResponse:
    client_key = get_client_ip(request)
    user = auth_service.authenticate(
        db, identifier=payload.identifier, password=payload.password, client_key=client_key
    )
    token, csrf, _session = auth_service.create_session(
        db, user, user_agent=request.headers.get("user-agent")
    )
    _set_session_cookies(response, token, csrf)
    return AuthResponse(user=UserOut.model_validate(user), csrf_token=csrf, message="登录成功")


@router.post("/logout", response_model=MessageOut)
def logout(
    response: Response,
    db: DbSession,
    token: Annotated[str | None, Depends(get_session_token)],
) -> MessageOut:
    """Logout is idempotent and does not require a valid session."""
    if token:
        session = auth_service.resolve_session(db, token)
        if session is not None:
            auth_service.revoke_session(db, session)
    _clear_session_cookies(response)
    return MessageOut(message="已退出登录")


@router.get("/session", response_model=AuthResponse)
def current_session(session: CurrentSession) -> AuthResponse:
    """Return the current user (used by the SPA to restore state on reload)."""
    return AuthResponse(
        user=UserOut.model_validate(session.user), csrf_token="", message="ok"
    )


@router.post("/logout-all", response_model=MessageOut)
def logout_all(response: Response, db: DbSession, user: CurrentUser) -> MessageOut:
    count = auth_service.revoke_all_sessions(db, user)
    _clear_session_cookies(response)
    return MessageOut(message=f"已退出全部 {count} 个会话")
