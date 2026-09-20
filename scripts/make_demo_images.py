"""Generate synthetic, clearly non-clinical demo images for public screenshots.

The public README must not republish third-party lesion images (the dataset used
for training/evaluation has no confirmed redistribution licence), and a real
patient photo would be a privacy problem.  So the screenshots are taken with
images generated here: a synthetic skin-like background with a painted lesion.

These are **not** medical images and must never be presented as real cases --
the README says so explicitly.  Their only job is to let the real UI, the real
upload path and the real model inference be captured without publishing
third-party data.

Usage (repository root):
    .\\.venv\\Scripts\\python.exe -X utf8 scripts\\make_demo_images.py
    # -> docs/assets/demo/demo_lesion_a.jpg, demo_lesion_b.jpg
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parents[1]
OUT_DIR = REPO / "docs" / "assets" / "demo"
SIZE = 512


def skin_background(rng: random.Random) -> Image.Image:
    """A soft, slightly uneven skin-like tone with fine grain."""
    base = Image.new("RGB", (SIZE, SIZE), (226, 186, 162))
    pixels = base.load()
    for y in range(SIZE):
        for x in range(SIZE):
            # gentle vignette + low-frequency variation
            dx = (x - SIZE / 2) / (SIZE / 2)
            dy = (y - SIZE / 2) / (SIZE / 2)
            falloff = 1.0 - 0.10 * (dx * dx + dy * dy)
            wave = 4.0 * math.sin(x / 37.0) + 3.0 * math.cos(y / 29.0)
            grain = rng.uniform(-3.5, 3.5)
            r = 226 * falloff + wave + grain
            g = 186 * falloff + wave * 0.8 + grain
            b = 162 * falloff + wave * 0.6 + grain
            pixels[x, y] = (
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )
    return base.filter(ImageFilter.GaussianBlur(0.6))


def draw_lesion(
    image: Image.Image,
    rng: random.Random,
    center: tuple[int, int],
    radius: int,
    colour: tuple[int, int, int],
) -> None:
    """Paint an irregular, asymmetrical blotch with a soft border."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    points: list[tuple[float, float]] = []
    steps = 72
    for index in range(steps):
        angle = 2 * math.pi * index / steps
        # radius varies with angle -> irregular, asymmetric shape
        wobble = 1.0 + 0.22 * math.sin(3 * angle + rng.random() * 0.4)
        wobble *= 1.0 + 0.14 * math.cos(5 * angle + 1.1)
        r = radius * wobble
        points.append((center[0] + r * math.cos(angle), center[1] + r * math.sin(angle)))

    draw.polygon(points, fill=(*colour, 235))
    overlay = overlay.filter(ImageFilter.GaussianBlur(3.2))

    # a few darker speckles inside the lesion
    speckles = Image.new("RGBA", image.size, (0, 0, 0, 0))
    speckle_draw = ImageDraw.Draw(speckles)
    for _ in range(14):
        angle = rng.uniform(0, 2 * math.pi)
        distance = rng.uniform(0, radius * 0.65)
        cx = center[0] + distance * math.cos(angle)
        cy = center[1] + distance * math.sin(angle)
        dot = rng.uniform(2.5, 6.5)
        shade = tuple(max(0, channel - rng.randint(18, 45)) for channel in colour)
        speckle_draw.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=(*shade, 200))
    speckles = speckles.filter(ImageFilter.GaussianBlur(1.4))

    image.alpha_composite(overlay)
    image.alpha_composite(speckles)


def build(seed: int, centre_ratio: float, radius: int, colour: tuple[int, int, int]) -> Image.Image:
    rng = random.Random(seed)
    canvas = skin_background(rng).convert("RGBA")
    draw_lesion(
        canvas,
        rng,
        center=(int(SIZE * centre_ratio), int(SIZE * (centre_ratio + 0.02))),
        radius=radius,
        colour=colour,
    )
    return canvas.convert("RGB")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    variants = {
        # (seed, centre ratio, radius, colour) — visually distinct synthetic lesions
        "demo_lesion_a.jpg": (20260919, 0.48, 78, (120, 84, 66)),
        "demo_lesion_b.jpg": (20260920, 0.52, 62, (96, 66, 58)),
        "demo_lesion_c.jpg": (20260921, 0.50, 112, (74, 52, 48)),
    }
    for name, args in variants.items():
        image = build(*args)
        path = OUT_DIR / name
        image.save(path, format="JPEG", quality=92)
        print(f"wrote {path.relative_to(REPO).as_posix()} ({path.stat().st_size} bytes)")
    print("\nThese images are synthetic placeholders, not medical images.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
