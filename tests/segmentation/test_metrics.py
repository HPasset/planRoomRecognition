import numpy as np
from src.segmentation.metrics import (
    compute_iou_per_class, compute_miou, compute_room_recall_precision,
)
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


def test_room_recall_precision_basic():
    # GT instance mask: 2 rooms (class 2, class 5)
    gt_inst = np.zeros((10, 10), dtype=np.int32)
    gt_inst[0:5, 0:5] = 1  # room 1
    gt_inst[5:10, 5:10] = 2  # room 2
    gt_classes = {1: 2, 2: 5}

    # Pred: 1 room overlapping room 1 (correct class), 1 room overlapping room 2 (wrong class)
    pred_inst = np.zeros((10, 10), dtype=np.int32)
    pred_inst[0:5, 0:5] = 10
    pred_inst[5:10, 5:10] = 20
    pred_classes = {10: 2, 20: 4}  # second is BedRoom instead of Bath

    rec, prec, type_acc = compute_room_recall_precision(
        pred_inst, pred_classes, gt_inst, gt_classes,
    )
    assert rec == 0.5  # only room 1 retrouvé avec bonne classe
    assert prec == 0.5
    assert type_acc == 0.5  # 1 sur 2 retrouvés = bonne classe
