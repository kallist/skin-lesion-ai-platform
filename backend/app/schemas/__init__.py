"""Pydantic request/response schemas (the public API contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Prediction = Literal["benign", "malignant"]


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def _username_charset(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("用户名不能为空")
        if not all(c.isalnum() or c in "._-" for c in value):
            raise ValueError("用户名只能包含字母、数字、下划线、点或短横线")
        return value

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.strip().lower()


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255, description="邮箱或用户名")
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    full_name: str | None = None
    created_at: datetime
    updated_at: datetime


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, min_length=3, max_length=64)

    @field_validator("username")
    @classmethod
    def _username_charset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not all(c.isalnum() or c in "._-" for c in value):
            raise ValueError("用户名只能包含字母、数字、下划线、点或短横线")
        return value


class AuthResponse(BaseModel):
    user: UserOut
    csrf_token: str
    message: str = "ok"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------
class Probabilities(BaseModel):
    benign: float = Field(ge=0.0, le=1.0)
    malignant: float = Field(ge=0.0, le=1.0)


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prediction: Prediction
    confidence: float
    probabilities: Probabilities
    model_version: str
    original_filename: str
    image_available: bool
    disclaimer: str
    advice: str
    created_at: datetime


class DetectionListItem(BaseModel):
    id: int
    prediction: Prediction
    confidence: float
    probabilities: Probabilities
    model_version: str
    original_filename: str
    image_available: bool
    created_at: datetime


class DetectionPage(BaseModel):
    items: list[DetectionListItem]
    total: int
    page: int
    page_size: int
    pages: int


# ---------------------------------------------------------------------------
# Model / system
# ---------------------------------------------------------------------------
class ModelInfo(BaseModel):
    model_version: str
    architecture: str
    input_size: int
    class_names: list[str]
    class_mapping: dict[str, int]
    trained_at: str
    device: str
    calibration: str
    disclaimer: str
    available: bool
    best_val_metric: dict = Field(default_factory=dict)


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: bool
    model: bool
    model_version: str | None = None
    uptime_seconds: float


class MessageOut(BaseModel):
    message: str
