"""Segmentation metrics: per-class IoU, mIoU, room recall/precision/type accuracy."""
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


def compute_room_recall_precision(
    pred_instance: np.ndarray,
    pred_classes: dict[int, int],
    gt_instance: np.ndarray,
    gt_classes: dict[int, int],
    iou_threshold: float = 0.5,
) -> tuple[float, float, float]:
    """Match predicted rooms to GT rooms by IoU > threshold.

    Returns:
        recall: fraction of GT rooms matched with correct class
        precision: fraction of predicted rooms matching a GT room with correct class
        type_accuracy: among matched rooms (any class), fraction with correct class
    """
    gt_ids = [i for i in np.unique(gt_instance) if i != 0]
    pred_ids = [i for i in np.unique(pred_instance) if i != 0]

    if not gt_ids and not pred_ids:
        return 1.0, 1.0, 1.0
    if not gt_ids:
        return 0.0, 0.0, 0.0
    if not pred_ids:
        return 0.0, 1.0, 0.0

    # IoU matrix
    iou = np.zeros((len(gt_ids), len(pred_ids)))
    for i, g in enumerate(gt_ids):
        gm = gt_instance == g
        for j, p in enumerate(pred_ids):
            pm = pred_instance == p
            u = np.logical_or(gm, pm).sum()
            if u == 0:
                continue
            iou[i, j] = np.logical_and(gm, pm).sum() / u

    # Greedy matching by descending IoU
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matches: list[tuple[int, int]] = []  # (gt_idx, pred_idx)
    flat = [(iou[i, j], i, j) for i in range(len(gt_ids)) for j in range(len(pred_ids))]
    flat.sort(reverse=True)
    for v, i, j in flat:
        if v < iou_threshold:
            break
        if i in matched_gt or j in matched_pred:
            continue
        matched_gt.add(i)
        matched_pred.add(j)
        matches.append((i, j))

    # Class-correct matches (cast numpy ints to Python int for dict lookup)
    correct = 0
    for i, j in matches:
        if pred_classes.get(int(pred_ids[j])) == gt_classes.get(int(gt_ids[i])):
            correct += 1

    recall = correct / len(gt_ids)
    precision = correct / len(pred_ids) if pred_ids else 0.0
    type_acc = (correct / len(matches)) if matches else 0.0
    return recall, precision, type_acc
