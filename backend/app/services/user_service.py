"""User profile service."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from ..core.errors import ConflictError, NotFoundError
from ..db.models import User

LOGGER = logging.getLogger("app.users")


def get_user(db: OrmSession, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    return user


def get_by_email_or_username(db: OrmSession, identifier: str) -> User | None:
    return db.scalar(
        select(User).where(
            (User.email == identifier.strip().lower()) | (User.username == identifier.strip())
        )
    )


def update_profile(
    db: OrmSession,
    user: User,
    *,
    full_name: str | None = None,
    username: str | None = None,
) -> User:
    changed = False
    if username is not None and username != user.username:
        clash = db.scalar(select(User).where(User.username == username, User.id != user.id))
        if clash:
            raise ConflictError("该用户名已被占用", details={"field": "username"})
        user.username = username
        changed = True
    if full_name is not None and full_name != user.full_name:
        user.full_name = full_name or None
        changed = True
    if changed:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ConflictError("用户名已被占用") from exc
        db.refresh(user)
    return user


def delete_account(db: OrmSession, user: User) -> None:
    """Delete the account and (via cascade) its sessions and detections.

    Ordering matters: the database rows are committed **first**, then the
    ciphertext files are removed.  If the commit fails nothing is lost; if the
    file removal fails the leftovers are orphan files that the startup sweep
    removes, instead of rows pointing at unreadable images.
    """
    from ..services.detection_service import collect_image_paths_for_user, purge_image_paths

    user_id = user.id
    paths = collect_image_paths_for_user(db, user)
    db.delete(user)
    db.commit()
    removed = purge_image_paths(paths)
    LOGGER.info("user id=%s deleted (%d encrypted image(s) removed)", user_id, removed)
