"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from . import auth, detections, system, users

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(detections.router)

__all__ = ["api_router"]
