"""Logique pure de résolution des conflits OCR / Segmentation.

Un conflit vient de `fuse_rooms_with_ocr` : une pièce *segmentation* dont la
classe modèle diffère de la classe impliquée par l'OCR. La résolution est
ancrée sur le seg_room_id (RoomDetection.id) — c'est le polygone seg qui sert
au point-in-polygon pour relier le conflit à sa pastille.

Pas d'import Streamlit ni de constante d'app ici : ce module est testable seul.
"""
from __future__ import annotations

import cv2
import numpy as np

from src.segmentation.classes import CLASS_NAMES


def unresolved_conflicts(
    fusion_records: list[dict],
    resolutions: dict[str, str],
) -> list[dict]:
    """fusion_records en conflit dont le seg_room_id n'est pas encore résolu."""
    return [
        rec for rec in fusion_records
        if rec.get("conflict") and rec["room"].id not in resolutions
    ]


def conflict_choices(record: dict) -> dict:
    """Extrait de quoi peupler la modale pour un fusion_record en conflit.

    Retourne les noms de classe C2 (domaine segmentation) — la conversion vers
    les libellés devis FR se fait côté app (c2_class_to_devis_label)."""
    room = record["room"]
    ocr_class_id = record["ocr_class_id"]
    ocr_text = ""
    for h in record.get("ocr_hits", []):
        txt = h.get("text") or h.get("raw_text") or ""
        if txt:
            ocr_text = txt
            break
    return {
        "seg_room_id": room.id,
        "ocr_text": ocr_text,
        "ocr_class_id": ocr_class_id,
        "ocr_class_name": CLASS_NAMES[ocr_class_id],
        "seg_class_id": room.type_id,
        "seg_class_name": room.type,
    }


def find_pastille_in_room(
    pastilles: list[dict],
    polygon: list[list[int]],
) -> str | None:
    """id de la pastille dont (x, y) est dans le polygone. Plusieurs → la plus
    proche du centroïde. Aucune → None."""
    if not pastilles or not polygon:
        return None
    contour = np.array(polygon, dtype=np.int32).reshape(-1, 1, 2)
    cx = float(np.mean([p[0] for p in polygon]))
    cy = float(np.mean([p[1] for p in polygon]))
    best_id: str | None = None
    best_dist = float("inf")
    for p in pastilles:
        x, y = float(p["x"]), float(p["y"])
        if cv2.pointPolygonTest(contour, (x, y), False) < 0:
            continue
        d = (x - cx) ** 2 + (y - cy) ** 2
        if d < best_dist:
            best_dist = d
            best_id = str(p["id"])
    return best_id
