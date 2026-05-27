"""Fusion OCR (FR text) ↔ Segmentation (C2 polygons).

Provides:
  - FR_TO_C2 mapping (room_type from postprocess_ocr_items → C2 class id)
  - attribute_ocr_to_rooms(): for each OCR hit, find the polygon it falls in
  - fuse_rooms_with_ocr(): enrich each RoomDetection with its OCR hits +
    flag conflicts when OCR text class disagrees with model class
"""
from __future__ import annotations
from typing import Iterable

import cv2
import numpy as np

from src.segmentation.classes import CLASS_ID
from src.segmentation.schema import RoomDetection


# OCR FR room_type (from src/planrec/ocr/postprocess.py:_ROOM_ALIASES)
# → C2 class id (from src/segmentation/classes.py).
# Note: "bureau" → BedRoom (CubiCasa-style: office = private room with similar
# electrical needs). "wc" → Bath (matches our 10-class taxonomy where Bath
# fusionne sdb + WC).
FR_TO_C2: dict[str, int] = {
    "cuisine": CLASS_ID["Kitchen"],
    "salon": CLASS_ID["LivingRoom"],
    "sejour": CLASS_ID["LivingRoom"],
    "chambre": CLASS_ID["BedRoom"],
    "nid": CLASS_ID["BedRoom"],
    "bureau": CLASS_ID["BedRoom"],
    "salle_de_bain": CLASS_ID["Bath"],
    "salle_de_douche": CLASS_ID["Bath"],
    "salle_d_eau": CLASS_ID["Bath"],
    "wc": CLASS_ID["Bath"],
    "entree": CLASS_ID["Entry"],
    "couloir": CLASS_ID["Entry"],
    "degagement": CLASS_ID["Entry"],
    "palier": CLASS_ID["Entry"],
    "cellier": CLASS_ID["Storage"],
    "buanderie": CLASS_ID["Storage"],
    "dressing": CLASS_ID["Storage"],
    "garage": CLASS_ID["Garage"],
    "balcon": CLASS_ID["Outdoor"],
    "terrasse": CLASS_ID["Outdoor"],
}


def _bbox_centroid(bbox: list[list[int]]) -> tuple[float, float]:
    """OCR bbox is 4 points [[x,y], ...] → centroid."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def attribute_ocr_to_rooms(
    ocr_hits: list[dict],
    rooms: Iterable[RoomDetection],
) -> dict[str, list[dict]]:
    """For each OCR hit, find the room polygon containing its centroid.

    Returns {room.id: [hit, ...]}. Hits with centroid outside all rooms
    are returned under key "_outside" (legend, margins, etc.).

    When a centroid falls in multiple polygons (overlapping rooms), the
    SMALLEST polygon wins (most specific room).
    """
    rooms_list = list(rooms)
    by_room: dict[str, list[dict]] = {r.id: [] for r in rooms_list}
    by_room["_outside"] = []

    # Precompute polygons as ndarrays + their area for tie-breaking
    polys = [
        (r, np.asarray(r.polygon, dtype=np.int32), r.area_pixels)
        for r in rooms_list
    ]

    for hit in ocr_hits:
        bbox = hit.get("bbox")
        if not bbox or len(bbox) < 3:
            by_room["_outside"].append(hit)
            continue
        cx, cy = _bbox_centroid(bbox)

        candidates: list[tuple[int, RoomDetection]] = []
        for room, poly, area in polys:
            if cv2.pointPolygonTest(poly, (cx, cy), measureDist=False) >= 0:
                candidates.append((area, room))

        if not candidates:
            by_room["_outside"].append(hit)
        else:
            candidates.sort(key=lambda t: t[0])  # smallest first
            target_room = candidates[0][1]
            by_room[target_room.id].append(hit)

    return by_room


def fuse_rooms_with_ocr(
    rooms: list[RoomDetection],
    ocr_hits: list[dict],
) -> list[dict]:
    """Combine each room with its in-polygon OCR hits + conflict flag.

    Returns one dict per room with:
        room: RoomDetection
        ocr_hits: list of dict with text/confidence/bbox/room_type
        ocr_class_id: int | None (best class id implied by OCR hits, by
            text confidence majority)
        conflict: bool (True if ocr_class_id is set and differs from
            room.type_id)
    """
    attributed = attribute_ocr_to_rooms(ocr_hits, rooms)
    out: list[dict] = []

    for room in rooms:
        hits = attributed.get(room.id, [])

        # Pick best OCR class for this room: take the hit with highest
        # confidence whose room_type is mappable. Ties broken by hit order.
        ocr_class_id: int | None = None
        best_conf = -1.0
        for h in hits:
            rt = h.get("room_type")
            if rt is None:
                continue
            cid = FR_TO_C2.get(rt)
            if cid is None:
                continue
            conf = float(h.get("confidence", 0.0))
            if conf > best_conf:
                best_conf = conf
                ocr_class_id = cid

        conflict = (
            ocr_class_id is not None and ocr_class_id != room.type_id
        )

        out.append({
            "room": room,
            "ocr_hits": hits,
            "ocr_class_id": ocr_class_id,
            "conflict": conflict,
        })

    return out
