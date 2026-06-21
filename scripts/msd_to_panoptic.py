"""Convertit MSD (Modified Swiss Dwellings, CSV vectoriel) en jeu panoptique
10 classes pour src/segmentation/dataset.py:PanopticDataset.

Source : data/raw/msd/mds_V2_5.372k.csv (geom WKT métrique + roomtype + plan_id).
Sortie : <out>/images|semantic|instance/{split}/<plan_id>.png + splits.json.
"""
from __future__ import annotations
import numpy as np
import cv2
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon

from src.segmentation.classes import MSD_TO_C2, CLASS_ID, ROOM_CLASS_IDS

_WALL_ID = CLASS_ID["Wall"]
_ROOM_IDS = set(ROOM_CLASS_IDS)


def _polys(geom_wkt: str) -> list[np.ndarray]:
    """WKT → liste de rings (Nx2 float, coords métriques). Tolère MULTIPOLYGON."""
    g = shapely_wkt.loads(geom_wkt)
    out = []
    for poly in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
        if isinstance(poly, Polygon) and not poly.is_empty:
            out.append(np.asarray(poly.exterior.coords, dtype=np.float64))
    return out


def _bounds(entities: list[dict]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for e in entities:
        for ring in _polys(e["geom"]):
            xs.extend(ring[:, 0]); ys.extend(ring[:, 1])
    return min(xs), min(ys), max(xs), max(ys)


def _to_px(ring: np.ndarray, minx, maxy, scale, margin) -> np.ndarray:
    """Métrique → pixels. Y inversé (image y-down)."""
    px = margin + (ring[:, 0] - minx) * scale
    py = margin + (maxy - ring[:, 1]) * scale
    return np.stack([px, py], axis=1).round().astype(np.int32)


def rasterize_plan(entities: list[dict], size: int = 768, margin: int = 16):
    """Liste d'entités {roomtype, entity_type, geom} → (image, semantic, instance).

    Ordre de peinture : pièces (area) d'abord, puis murs (Structure) par-dessus.
    image : murs noirs sur fond blanc (rendu type plan, sans mobilier).
    """
    minx, miny, maxx, maxy = _bounds(entities)
    span = max(maxx - minx, maxy - miny) or 1.0
    scale = (size - 2 * margin) / span

    image = np.full((size, size, 3), 255, np.uint8)
    semantic = np.zeros((size, size), np.uint8)
    instance = np.zeros((size, size), np.uint16)

    areas = [e for e in entities if e["entity_type"] == "area"]
    walls = [e for e in entities if e["entity_type"] == "separator"]

    next_inst = 1
    for e in areas:
        cid = MSD_TO_C2(e["roomtype"])
        if cid == CLASS_ID["Background"]:
            continue
        for ring in _polys(e["geom"]):
            pts = _to_px(ring, minx, maxy, scale, margin)
            cv2.fillPoly(semantic, [pts], int(cid))
            if cid in _ROOM_IDS:
                cv2.fillPoly(instance, [pts], next_inst)
        if cid in _ROOM_IDS:
            next_inst += 1

    for e in walls:
        for ring in _polys(e["geom"]):
            pts = _to_px(ring, minx, maxy, scale, margin)
            cv2.fillPoly(semantic, [pts], _WALL_ID)
            cv2.fillPoly(instance, [pts], 0)
            cv2.fillPoly(image, [pts], (0, 0, 0))

    return image, semantic, instance
