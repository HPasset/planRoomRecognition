import numpy as np
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.classes import NUM_CLASSES


def test_perfect_prediction_iou_one():
    pred = np.array([[2, 2, 0], [2, 2, 0], [0, 0, 0]], dtype=np.uint8)
    gt = pred.copy()
    iou = compute_iou_per_class(pred, gt, NUM_CLASSES)
    # Class 2 IoU = 1, class 0 IoU = 1, others = nan
    assert iou[2] == 1.0
    assert iou[0] == 1.0
    assert np.isnan(iou[5])


def test_no_overlap_iou_zero():
    pred = np.full((3, 3), 2, dtype=np.uint8)
    gt = np.full((3, 3), 5, dtype=np.uint8)
    iou = compute_iou_per_class(pred, gt, NUM_CLASSES)
    assert iou[2] == 0.0
    assert iou[5] == 0.0


def test_miou_handles_nan():
    iou = np.full(NUM_CLASSES, np.nan)
    iou[2] = 0.8
    iou[5] = 0.6
    assert abs(compute_miou(iou) - 0.7) < 1e-6
