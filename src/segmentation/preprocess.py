"""Letterbox-based preprocessing for inference (preserves aspect ratio)."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class LetterboxInfo:
    orig_h: int
    orig_w: int
    target_size: int
    scale: float
    pad_top: int
    pad_left: int
    pad_bottom: int
    pad_right: int


def letterbox(image: np.ndarray, target_size: int = 768,
              fill_value: int = 255) -> tuple[np.ndarray, LetterboxInfo]:
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_top = (target_size - new_h) // 2
    pad_bottom = target_size - new_h - pad_top
    pad_left = (target_size - new_w) // 2
    pad_right = target_size - new_w - pad_left

    padded = cv2.copyMakeBorder(
        resized, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=(fill_value, fill_value, fill_value),
    )
    return padded, LetterboxInfo(
        orig_h=h, orig_w=w, target_size=target_size, scale=scale,
        pad_top=pad_top, pad_left=pad_left,
        pad_bottom=pad_bottom, pad_right=pad_right,
    )


def unletterbox_mask(mask: np.ndarray, info: LetterboxInfo) -> np.ndarray:
    """Crop padding then resize back to original image size. Uses NEAREST."""
    cropped = mask[
        info.pad_top : info.target_size - info.pad_bottom,
        info.pad_left : info.target_size - info.pad_right,
    ]
    return cv2.resize(cropped, (info.orig_w, info.orig_h),
                      interpolation=cv2.INTER_NEAREST)
