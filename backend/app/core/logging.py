"""Logging configuration with secret redaction.

Every log record passes through :class:`RedactingFilter`, which masks anything
that looks like a bearer token, cookie, password, API key or Fernet key.  Raw
image bytes / base64 blobs are never logged by the application at all.
"""

from __future__ import annotations

import logging
import re
import sys

REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(password[\"']?\s*[:=]\s*)[^,;&\s\"'}]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(session_secret[\"']?\s*[:=]\s*)[^,;&\s\"'}]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(image_encryption_key[\"']?\s*[:=]\s*)[^,;&\s\"'}]+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(authorization\s*:\s*bearer\s+)\S+", re.I), r"\1***REDACTED***"),
    (re.compile(r"(cookie\s*:\s*)\S+", re.I), r"\1***REDACTED***"),
    (re.compile(r"((?:api[_-]?key|token|secret|fernet)[\"']?\s*[:=]\s*)[^,;&\s\"'}]+", re.I), r"\1***REDACTED***"),
    # Fernet keys are 44-char url-safe base64 strings
    (re.compile(r"\b[A-Za-z0-9_\-]{43}=\b"), "***REDACTED-KEY***"),
    # long base64 payloads (image data) should never reach the logs
    (re.compile(r"\b[A-Za-z0-9+/]{120,}={0,2}\b"), "***REDACTED-BLOB***"),
]


def redact(text: str) -> str:
    for pattern, replacement in REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    )
    handler.addFilter(RedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # uvicorn keeps its own handlers; attach the redaction filter to them too
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.propagate = False
