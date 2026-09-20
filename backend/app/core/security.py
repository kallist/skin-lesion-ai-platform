"""Password hashing, session tokens and CSRF helpers.

* Passwords: Argon2id via ``argon2-cffi`` (never stored or logged in plaintext).
* Sessions: 256-bit random tokens; only the SHA-256 hash is persisted, so a
  database leak does not hand out usable sessions.
* CSRF: double-submit token tied to the session row; required for all
  state-changing cookie-authenticated requests.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

# Argon2id parameters: memory 64 MiB, 3 iterations, 2 lanes (OWASP baseline).
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 24


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Return an Argon2id hash. Raises ValueError on empty input."""
    if not password:
        raise ValueError("password must not be empty")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish verification; returns False instead of raising."""
    if not password or not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False
    except Exception:  # noqa: BLE001 - never leak hashing internals to the caller
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:  # noqa: BLE001
        return True


def password_strength_error(password: str, min_length: int = 8) -> str | None:
    """Return a human-readable error string, or ``None`` when acceptable."""
    if len(password) < min_length:
        return f"密码长度至少需要 {min_length} 个字符"
    if password.strip() != password:
        return "密码首尾不能包含空格"
    if password.lower() in {"password", "12345678", "qwertyui", "11111111"}:
        return "密码过于常见，请更换更复杂的密码"
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 2:
        return "密码需要包含大小写字母、数字或符号中的至少两类"
    return None


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------
def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(CSRF_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 of the raw token: what we store in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def new_idempotency_key() -> str:
    return secrets.token_urlsafe(18)
