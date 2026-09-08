"""Segmentation metrics: per-class IoU, mIoU."""
import numpy as np


def compute_iou_per_class(pred: np.ndarray, gt: np.ndarray, num_classes: int,
                          ignore_index: int | None = None) -> np.ndarray:
    """Per-class IoU. Returns nan for classes absent from both pred and gt."""
    iou = np.full(num_classes, np.nan, dtype=np.float64)
    for c in range(num_classes):
        if ignore_index is not None and c == ignore_index:
            continue
        p = pred == c
        g = gt == c
        union = np.logical_or(p, g).sum()
        if union == 0:
            continue  # nan
        inter = np.logical_and(p, g).sum()
        iou[c] = inter / union
    return iou


def compute_miou(iou_per_class: np.ndarray) -> float:
    valid = iou_per_class[~np.isnan(iou_per_class)]
    return float(valid.mean()) if len(valid) > 0 else 0.0
