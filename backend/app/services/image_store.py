"""Image validation + encrypted-at-rest storage.

Privacy design
--------------
* The uploaded bytes are decoded with Pillow before anything else, so a file
  that merely *claims* to be an image is rejected (MIME headers are not trusted).
* Pixel count, dimensions and byte size are bounded (decompression-bomb guard).
* EXIF and other metadata are dropped: only the decoded RGB pixels are stored.
* The stored file is a Fernet-encrypted blob (AES-128-CBC + HMAC) whose name is
  server-generated (``<uuid4>.enc``), so the original client filename can never
  influence a filesystem path.
* Writes go to a temporary file first and are then atomically renamed, which
  means a crash never leaves a half-written ciphertext in place.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, UnidentifiedImageError

from ..core.config import get_settings
from ..core.errors import (
    ImageTooLargeError,
    InvalidImageError,
    StorageError,
    UnsupportedImageTypeError,
)

LOGGER = logging.getLogger("app.images")

# Pillow-level backstop: the application enforces MAX_IMAGE_PIXELS explicitly
# (settings), but a crafted file can allocate memory *inside* Image.open /
# verify / load before that check runs, so Pillow's own guard is kept at a
# finite (configurable) limit instead of being disabled.
try:
    _pillow_limit = get_settings().max_image_pixels * 2
except Exception:  # pragma: no cover - settings always load in practice
    _pillow_limit = 80_000_000
Image.MAX_IMAGE_PIXELS = _pillow_limit

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MAX_DIMENSION = 12000


@dataclass
class ValidatedImage:
    """Result of validating an upload."""

    image: Image.Image  # RGB, metadata stripped
    content_type: str
    format: str
    width: int
    height: int
    sha256: str
    byte_size: int
    original_filename: str


def validate_upload(data: bytes, filename: str = "upload") -> ValidatedImage:
    """Decode and validate an uploaded image.

    Raises :class:`InvalidImageError`, :class:`UnsupportedImageTypeError` or
    :class:`ImageTooLargeError` with user-safe messages.
    """
    settings = get_settings()
    if not data:
        raise InvalidImageError("上传文件为空")

    if len(data) > settings.max_upload_bytes:
        raise ImageTooLargeError(
            f"图片大小 {len(data) / 1024 / 1024:.1f} MB 超过上限 {settings.max_upload_mb} MB"
        )

    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in ALLOWED_EXTENSIONS:
        raise UnsupportedImageTypeError(
            f"不支持的文件类型 {suffix}，请上传 JPG / PNG / WEBP / BMP 图片"
        )

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = (probe.format or "").upper()
            width, height = probe.size
            # force a real decode: truncated / spoofed files fail here
            probe.verify()
    except UnidentifiedImageError as exc:
        raise InvalidImageError("文件不是有效的图片（无法识别格式）") from exc
    except ImageTooLargeError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise InvalidImageError("图片文件损坏或无法解码") from exc

    if fmt not in ALLOWED_FORMATS:
        raise UnsupportedImageTypeError(f"不支持的图片格式：{fmt or 'unknown'}")
    if width <= 0 or height <= 0:
        raise InvalidImageError("图片尺寸无效")
    if width * height > settings.max_image_pixels:
        raise ImageTooLargeError(
            f"图片像素数 {width}x{height} 超过上限 {settings.max_image_pixels:,}"
        )
    if max(width, height) > MAX_DIMENSION:
        raise ImageTooLargeError(f"图片单边尺寸 {max(width, height)}px 超过上限 {MAX_DIMENSION}px")

    # Re-open (verify() invalidates the file object) and drop all metadata.
    try:
        with Image.open(io.BytesIO(data)) as src:
            src.load()
            image = src.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise InvalidImageError("图片文件损坏或无法解码") from exc

    clean = Image.new("RGB", image.size)
    clean.paste(image)
    clean.info = {}  # strip EXIF / ICC / text chunks

    return ValidatedImage(
        image=clean,
        content_type=f"image/{fmt.lower() if fmt != 'JPEG' else 'jpeg'}",
        format=fmt,
        width=clean.width,
        height=clean.height,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_size=len(data),
        original_filename=sanitise_filename(filename),
    )


def sanitise_filename(filename: str) -> str:
    """Keep only the basename, strip control chars and cap the length."""
    name = os.path.basename((filename or "upload").replace("\\", "/"))
    name = "".join(c for c in name if c.isprintable() and c not in {'"', "'", "\x00"})
    name = name.strip() or "upload"
    return name[:120]


class EncryptedImageStore:
    """Fernet-encrypted, filesystem-backed image store."""

    def __init__(self, base_dir: str | Path | None = None, key: str | None = None) -> None:
        settings = get_settings()
        self.base_dir = Path(base_dir or settings.encrypted_image_dir)
        self.temp_dir = Path(settings.temp_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        raw_key = (key or settings.resolved_encryption_key()).encode()
        try:
            self._fernet = Fernet(raw_key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(
                "IMAGE_ENCRYPTION_KEY 无效，必须是 Fernet.generate_key() 生成的 32 字节 base64 字符串"
            ) from exc

    # ------------------------------------------------------------------
    def _encrypt_bytes(self, image: Image.Image, fmt: str = "PNG") -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt, optimize=False)
        return self._fernet.encrypt(buffer.getvalue())

    def save(self, image: Image.Image, *, prefix: str = "") -> tuple[str, str]:
        """Encrypt + store an image; returns ``(relative_path, sha256)``."""
        payload = self._encrypt_bytes(image)
        digest = hashlib.sha256(payload).hexdigest()
        name = f"{prefix}{uuid.uuid4().hex}.enc"
        final_path = self.base_dir / name
        tmp_path = self.temp_dir / f".{name}.tmp"
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, final_path)  # atomic within the same volume
        except Exception as exc:  # noqa: BLE001
            _safe_unlink(tmp_path)
            LOGGER.error("failed to persist encrypted image: %s", type(exc).__name__)
            raise StorageError("图片存储失败，请稍后重试") from exc
        return name, digest

    def load(self, relative_path: str) -> bytes:
        """Decrypt and return the raw image bytes (PNG)."""
        path = self._resolve(relative_path)
        if not path.exists():
            raise StorageError("历史图片文件缺失（可能已被清理）")
        try:
            return self._fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise StorageError("图片无法解密（密钥不匹配或文件已损坏）") from exc

    def delete(self, relative_path: str | None) -> bool:
        if not relative_path:
            return False
        try:
            path = self._resolve(relative_path)
        except ValueError:
            return False
        return _safe_unlink(path)

    def exists(self, relative_path: str | None) -> bool:
        if not relative_path:
            return False
        try:
            return self._resolve(relative_path).exists()
        except ValueError:
            return False

    def _resolve(self, relative_path: str) -> Path:
        """Resolve a stored name, refusing anything that escapes the base dir.

        Stored names are always server-generated, so any separator, ``..`` or
        absolute path in the input is by definition an attack: it is rejected
        explicitly and the resolved path is verified to sit directly inside the
        base directory.
        """
        raw = str(relative_path)
        if not raw or raw in {".", ".."}:
            raise ValueError("empty image path")
        if "/" in raw or "\\" in raw or ".." in raw:
            raise ValueError("path traversal attempt blocked")
        name = Path(raw).name
        if name != raw:
            raise ValueError("path traversal attempt blocked")
        candidate = (self.base_dir / name).resolve()
        base = self.base_dir.resolve()
        if candidate.parent != base:
            raise ValueError("path traversal attempt blocked")
        return candidate

    # ------------------------------------------------------------------
    def list_orphans(self, known_paths: set[str], *, min_age_seconds: int = 3600) -> list[Path]:
        """Files on disk that no database row references (crash leftovers)."""
        now = time.time()
        orphans = []
        for path in self.base_dir.glob("*.enc"):
            if path.name in known_paths:
                continue
            if now - path.stat().st_mtime < min_age_seconds:
                continue
            orphans.append(path)
        return orphans

    def sweep_orphans(self, known_paths: set[str], *, min_age_seconds: int = 3600) -> int:
        removed = 0
        for path in self.list_orphans(known_paths, min_age_seconds=min_age_seconds):
            if _safe_unlink(path):
                removed += 1
        # also clear stale temp files
        for path in self.temp_dir.glob("*.tmp"):
            if time.time() - path.stat().st_mtime > 3600:
                _safe_unlink(path)
        if removed:
            LOGGER.info("removed %d orphaned encrypted image file(s)", removed)
        return removed


def _safe_unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("could not remove %s: %s", path.name, type(exc).__name__)
        return False


_store: EncryptedImageStore | None = None


def get_image_store() -> EncryptedImageStore:
    global _store
    if _store is None:
        _store = EncryptedImageStore()
    return _store


def reset_image_store() -> None:
    """Test helper: drop the cached store so new settings take effect."""
    global _store
    _store = None
