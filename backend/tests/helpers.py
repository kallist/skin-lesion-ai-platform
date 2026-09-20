"""Shared test helpers (importable as ``tests.helpers``)."""

from __future__ import annotations

import io

from PIL import Image


def make_image_bytes(
    width: int = 64, height: int = 64, fmt: str = "JPEG", color=(180, 120, 90)
) -> bytes:
    """Create a real, decodable image in memory (never a fake byte blob)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_broken_jpeg() -> bytes:
    """Bytes that start with a JPEG SOI marker but are truncated."""
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64


def make_fake_png_header() -> bytes:
    """PNG signature followed by garbage: passes a MIME sniff, fails decode."""
    return b"\x89PNG\r\n\x1a\n" + b"not really a png" * 8


def make_bmp_bytes(width: int = 32, height: int = 32) -> bytes:
    return make_image_bytes(width, height, fmt="BMP")


def make_large_pixel_png(pixels: int = 60_000_000) -> bytes:
    """A tiny file that would decode to an enormous bitmap (decompression bomb).

    Pillow refuses to *create* such an image, so the bytes are crafted as a
    PNG IHDR with huge dimensions followed by an empty IDAT: the decode step
    fails fast and is rejected by the validator's pixel-count guard.
    """
    import struct
    import zlib

    width = height = int(pixels**0.5) + 1

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IEND", b"")
