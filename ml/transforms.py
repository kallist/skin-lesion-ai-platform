"""Image transforms shared by training, evaluation and serving.

The evaluation/serving pipeline here is the *authoritative* preprocessing
contract: :func:`build_eval_transform` is imported by the backend model
service so that a production request is preprocessed exactly like the images
used to measure accuracy.
"""

from __future__ import annotations

from typing import Sequence

from torchvision import transforms

from .config import IMAGE_SIZE, IMAGENET_MEAN, IMAGENET_STD


def build_train_transform(
    image_size: int = IMAGE_SIZE,
    *,
    scale: tuple[float, float] = (0.85, 1.0),
    rotation: float = 15.0,
    color_jitter: float = 0.15,
    vertical_flip: bool = False,
) -> transforms.Compose:
    """Augmentation used for the training split.

    Augmentation is deliberately mild: aggressive crops/rotations on
    dermoscopic lesions destroy the very structures (asymmetry, border, colour
    variation) the model is supposed to learn from.
    """
    ops: list = [
        transforms.RandomResizedCrop(image_size, scale=scale, ratio=(0.9, 1.111)),
        transforms.RandomRotation(degrees=rotation, fill=0),
        transforms.RandomHorizontalFlip(p=0.5),
    ]
    if vertical_flip:
        ops.append(transforms.RandomVerticalFlip(p=0.5))
    ops += [
        transforms.ColorJitter(
            brightness=color_jitter,
            contrast=color_jitter,
            saturation=color_jitter,
            hue=0.02,
        ),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ]
    return transforms.Compose(ops)


def build_eval_transform(
    image_size: int = IMAGE_SIZE,
    mean: Sequence[float] = IMAGENET_MEAN,
    std: Sequence[float] = IMAGENET_STD,
) -> transforms.Compose:
    """Deterministic preprocessing for validation / test / serving."""
    return transforms.Compose(
        [
            transforms.Resize(int(round(image_size * 1.14))),
            transforms.CenterCrop(image_size),
            transforms.ToTensor(),
            transforms.Normalize(tuple(mean), tuple(std)),
        ]
    )


def build_square_transform(image_size: int = IMAGE_SIZE) -> transforms.Compose:
    """Resize only (used for thumbnails / dataset inspection)."""
    return transforms.Compose([transforms.Resize((image_size, image_size))])
