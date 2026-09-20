"""User profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ...schemas import MessageOut, UpdateProfileRequest, UserOut
from ...services import auth_service, user_service
from ..deps import CurrentUser, DbSession, require_csrf

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch(
    "/me",
    response_model=UserOut,
    dependencies=[Depends(require_csrf)],
)
def update_me(payload: UpdateProfileRequest, user: CurrentUser, db: DbSession) -> UserOut:
    updated = user_service.update_profile(
        db, user, full_name=payload.full_name, username=payload.username
    )
    return UserOut.model_validate(updated)


@router.delete(
    "/me",
    response_model=MessageOut,
    dependencies=[Depends(require_csrf)],
)
def delete_me(response: Response, user: CurrentUser, db: DbSession) -> MessageOut:
    """Delete the account, its detections and every stored image."""
    user_service.delete_account(db, user)
    response.delete_cookie("csrf_token", path="/")
    return MessageOut(message="账号及全部检测记录已删除")
