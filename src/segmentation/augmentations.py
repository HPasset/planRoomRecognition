# src/segmentation/augmentations.py
"""Albumentations transforms for plan segmentation.

Train transform: aggressive but geometry-preserving (no elastic/mosaic/mixup).
Eval transform: letterbox to image_size, normalize, no augmentation.
"""
import albumentations as A
import cv2


_NORMALIZE = A.Normalize(
    mean=(0.485, 0.456, 0.406),  # ImageNet stats — Mask2Former pretrained convention
    std=(0.229, 0.224, 0.225),
)

_ADDITIONAL_TARGETS = {"instance_mask": "mask"}


def build_train_transform(image_size: int) -> A.Compose:
    return A.Compose(
        [
            # Geometric (preserve right-angle layout where possible)
            A.RandomRotate90(p=0.5),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.Affine(
                rotate=(-10, 10), shear=(-5, 5), scale=(0.8, 1.2),
                interpolation=cv2.INTER_LINEAR,
                mask_interpolation=cv2.INTER_NEAREST,
                fit_output=False, p=0.3,
            ),
            # Resize to fixed train size with padding (preserve aspect)
            A.LongestMaxSize(max_size=image_size, interpolation=cv2.INTER_LINEAR),
            A.PadIfNeeded(
                min_height=image_size, min_width=image_size,
                border_mode=cv2.BORDER_CONSTANT,
                value=255,          # white background for image (1.4.x API)
                mask_value=0,       # background class for masks (1.4.x API)
            ),
            # Photometric
            A.RandomBrightnessContrast(p=0.4),
            A.CLAHE(p=0.2),
            A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.0, p=0.3),
            # Degradations (scan realism)
            A.GaussNoise(p=0.2),
            A.GaussianBlur(blur_limit=(3, 5), p=0.15),
            A.ImageCompression(quality_range=(50, 95), p=0.2),
            A.CoarseDropout(num_holes_range=(1, 8),
                            hole_height_range=(8, 32),
                            hole_width_range=(8, 32),
                            fill_value=255, mask_fill_value=0, p=0.2),
            _NORMALIZE,
        ],
        additional_targets=_ADDITIONAL_TARGETS,
    )


def build_eval_transform(image_size: int) -> A.Compose:
    return A.Compose(
        [
            A.LongestMaxSize(max_size=image_size, interpolation=cv2.INTER_LINEAR),
            A.PadIfNeeded(
                min_height=image_size, min_width=image_size,
                border_mode=cv2.BORDER_CONSTANT,
                value=255, mask_value=0,  # 1.4.x API
            ),
            _NORMALIZE,
        ],
        additional_targets=_ADDITIONAL_TARGETS,
    )
