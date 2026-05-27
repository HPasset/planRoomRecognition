"""CubiCasa SVG → panoptic semantic + instance masks.

Reuses geometry helpers from scripts/cubicasa5k_export_yolo.py for
viewBox handling, transforms, and image alignment.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from src.segmentation.classes import CUBICASA_TO_C2, CLASS_ID, ROOM_CLASS_IDS


@dataclass
class RoomPolygon:
    """A polygon belonging to one C2 class, on the SVG viewBox coord system."""
    class_id: int
    points: np.ndarray  # shape (N, 2), float


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def _parse_points(pts: str) -> np.ndarray:
    coords: list[float] = []
    for part in pts.replace(",", " ").split():
        try:
            v = float(part)
        except ValueError:
            continue  # skip malformed token rather than discard whole polygon
        if not np.isfinite(v):
            continue  # skip NaN/Inf coordinates (silent corruption guard)
        coords.append(v)
    coords = coords[: (len(coords) // 2) * 2]
    if not coords:
        return np.empty((0, 2))
    return np.asarray(coords, dtype=np.float64).reshape(-1, 2)


def _candidate_labels(elem, parent_map: dict) -> tuple[list[str], list[str]]:
    """Return (own_labels, ancestor_labels). Direct labels take priority over inherited."""
    own: list[str] = []
    for attr in ("class", "id"):
        v = elem.get(attr)
        if v:
            own.extend(v.split())
    ancestors: list[str] = []
    cur = parent_map.get(elem)
    while cur is not None:
        for attr in ("class", "id"):
            v = cur.get(attr)
            if v:
                ancestors.extend(v.split())
        cur = parent_map.get(cur)
    return own, ancestors


def _label_to_class_id(own: list[str], ancestors: list[str]) -> int | None:
    """Resolve class id, prioritizing the polygon's own labels over ancestors.

    Within own labels: Wall takes priority over rooms (Wall always wins if direct).
    Then any direct room class.
    Then fall back to ancestor labels (last resort).
    """
    # Pass 1: check own labels for Wall first
    if "Wall" in own:
        return CLASS_ID["Wall"]
    # Pass 2: check own labels for any room class
    for lbl in own:
        cid = CUBICASA_TO_C2(lbl)
        if cid != 0:
            return cid
    # Pass 3: fall back to ancestor labels (Wall first, then rooms)
    if "Wall" in ancestors:
        return CLASS_ID["Wall"]
    for lbl in ancestors:
        cid = CUBICASA_TO_C2(lbl)
        if cid != 0:
            return cid
    return None


def _get_viewbox(root) -> tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split() if p]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]
    w = root.get("width")
    h = root.get("height")
    if w and h:
        return 0.0, 0.0, float(w), float(h)
    raise ValueError("SVG size not found")


def extract_room_polygons(svg_path: str | Path) -> List[RoomPolygon]:
    """Parse SVG and return all polygons mapped to C2 classes (Wall + rooms)."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    parent_map = {c: p for p in root.iter() for c in p}

    out: list[RoomPolygon] = []
    for elem in root.iter():
        if _strip_ns(elem.tag) != "polygon":
            continue
        pts_attr = elem.get("points")
        if not pts_attr:
            continue
        pts = _parse_points(pts_attr)
        if pts.shape[0] < 3:
            continue
        own, ancestors = _candidate_labels(elem, parent_map)
        cid = _label_to_class_id(own, ancestors)
        if cid is None or cid == 0:
            continue
        out.append(RoomPolygon(class_id=cid, points=pts))
    return out


def rasterize_panoptic(
    polygons: List[RoomPolygon], image_size: Tuple[int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    """Rasterize polygons into (semantic_mask, instance_mask).

    Args:
        polygons: from extract_room_polygons (assumed to be in SVG viewBox coords
                  matching image_size — caller responsible for prior scaling).
        image_size: (width, height) in pixels.

    Returns:
        semantic: uint8 (H, W), 0 = Background, 1..9 = class ids
        instance: int32 (H, W), 0 = unassigned, 1..N = unique room instance ids.
                  Walls always have instance_id = 0 (treated as stuff, not things).
    """
    w, h = image_size
    sem = np.zeros((h, w), dtype=np.uint8)
    inst = np.zeros((h, w), dtype=np.int32)

    next_inst_id = 1
    # Pass 1: rooms (instance-able)
    for poly in polygons:
        if poly.class_id not in ROOM_CLASS_IDS:
            continue
        if not np.all(np.isfinite(poly.points)):
            continue  # silent corruption guard
        pts = np.round(poly.points).astype(np.int32)
        cv2.fillPoly(sem, [pts], int(poly.class_id))
        cv2.fillPoly(inst, [pts], int(next_inst_id))
        next_inst_id += 1

    # Pass 2: walls overwrite rooms (a wall pixel is not in any room)
    for poly in polygons:
        if poly.class_id != CLASS_ID["Wall"]:
            continue
        if not np.all(np.isfinite(poly.points)):
            continue
        pts = np.round(poly.points).astype(np.int32)
        cv2.fillPoly(sem, [pts], int(poly.class_id))
        cv2.fillPoly(inst, [pts], 0)  # walls = stuff

    return sem, inst
