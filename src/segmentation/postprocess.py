"""Postprocessing: Mask2Former panoptic output → polygons + JSON."""
from pathlib import Path
import cv2
import numpy as np
from pycocotools import mask as mask_utils

from src.segmentation.classes import CLASS_NAMES, ROOM_CLASS_IDS, CLASS_ID
from src.segmentation.preprocess import LetterboxInfo, unletterbox_polygon, unletterbox_mask
from src.segmentation.schema import RoomDetection, WallsOutput


SCORE_MIN = 0.5
AREA_RATIO_MIN = 0.001  # 0.1% of image


def simplify_polygon(contour: np.ndarray, epsilon_ratio: float = 0.005) -> np.ndarray:
    """Douglas-Peucker simplification. contour shape (N,1,2) or (N,2)."""
    if contour.ndim == 2:
        contour = contour[:, None, :]
    eps = epsilon_ratio * cv2.arcLength(contour, closed=True)
    simplified = cv2.approxPolyDP(contour, eps, closed=True)
    return simplified.reshape(-1, 2)


def _largest_contour(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE,
    )
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def panoptic_to_rooms(
    panoptic_seg: np.ndarray,
    segments_info: list[dict],
    letterbox_info: LetterboxInfo,
    plan_size: tuple[int, int],  # (W, H) of original image
) -> list[dict]:
    """Convert Mask2Former panoptic output → list of room dicts (RoomDetection-compat).

    Args:
        panoptic_seg: (H, W) int — segment id per pixel (in letterboxed space)
        segments_info: list of {id, label_id, score, ...}
        letterbox_info: from preprocess.letterbox
        plan_size: (W, H) of original image
    """
    out: list[dict] = []
    plan_w, plan_h = plan_size
    plan_area = plan_w * plan_h
    counter = 0

    for seg in segments_info:
        score = seg.get("score", 1.0)
        label_id = seg.get("label_id")
        if label_id is None or label_id not in ROOM_CLASS_IDS:
            continue
        if score < SCORE_MIN:
            continue

        binary_lb = (panoptic_seg == seg["id"]).astype(np.uint8)
        if binary_lb.sum() == 0:
            continue
        # Map to original image space
        binary_orig = unletterbox_mask(binary_lb, letterbox_info)
        if binary_orig.sum() / plan_area < AREA_RATIO_MIN:
            continue

        contour = _largest_contour(binary_orig)
        if contour is None:
            continue
        poly = simplify_polygon(contour, epsilon_ratio=0.005)
        if len(poly) < 3:
            continue

        xs, ys = poly[:, 0], poly[:, 1]
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        counter += 1
        out.append(dict(
            id=f"room_{counter:03d}",
            type=CLASS_NAMES[label_id],
            type_id=int(label_id),
            polygon=poly.tolist(),
            bbox=bbox,
            area_pixels=int(binary_orig.sum()),
            confidence=float(score),
        ))
    return out


def walls_mask_to_output(
    walls_mask_lb: np.ndarray,
    letterbox_info: LetterboxInfo,
    plan_id: str,
    out_dir: str | Path,
) -> WallsOutput:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    walls_orig = unletterbox_mask(walls_mask_lb, letterbox_info)
    out_path = out_dir / f"{Path(plan_id).stem}_walls.png"
    cv2.imwrite(str(out_path), (walls_orig * 255).astype(np.uint8))

    rle = mask_utils.encode(np.asfortranarray(walls_orig.astype(np.uint8)))
    rle_str = rle["counts"].decode("ascii")

    # Skeleton path count: number of connected components of skeletonized walls
    from skimage.morphology import skeletonize
    skel = skeletonize(walls_orig.astype(bool))
    n_components, _ = cv2.connectedComponents(skel.astype(np.uint8))

    return WallsOutput(
        mask_rle=rle_str,
        mask_path=str(out_path),
        skeleton_paths_count=max(0, n_components - 1),
    )
