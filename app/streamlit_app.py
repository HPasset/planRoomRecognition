"""Streamlit demo: upload a floor plan and inspect predicted rooms + OCR.

Run with:
    streamlit run app/streamlit_app.py

Pure local — no data leaves the machine.
"""
from __future__ import annotations
import os
# MUST be set before torch import (Mask2Former MPS fallback)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import hashlib
import sys
import tempfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
import numpy as np
import pandas as pd
import streamlit as st

from app.components.pastille_canvas import pastille_canvas
from src.planrec.fusion import FR_TO_C2, fuse_rooms_with_ocr
from src.planrec.nfc_pricing import (
    DEFAULT_PRICES_HT,
    EQUIPMENT_LABELS_FR,
    EQUIPMENT_LABELS_LIST,
    LABEL_FR_TO_EQUIPMENT,
    TVA_DEFAULT,
    TVA_OPTIONS,
    compute_ttc,
)
from src.planrec.nfc_equipments import EQUIP_TYPES
from src.planrec.nfc_rules import compute_devis_global
from src.planrec.ocr.engine_paddle import PaddleOCREngine
from src.planrec.ocr.postprocess import postprocess_ocr_items
from src.planrec.polygon_postprocess import (
    extract_lines_from_image,
    extract_wall_lines,
    postprocess_polygon,
)
from src.segmentation.classes import CLASS_NAMES, ROOM_CLASS_IDS
from src.segmentation.inference import SegmentationInference
from src.segmentation.schema import RoomDetection, SegmentationOutput


# Palette identique à scripts/visualize_predictions.py — cohérence visuelle.
# Wall passé du gris foncé au magenta vif : invisible sur plans dont les murs
# sont déjà dessinés en noir.
PALETTE = np.array([
    [0, 0, 0],         # 0 Background
    [255, 0, 255],     # 1 Wall — magenta vif (contraste max sur fond noir/blanc)
    [255, 200, 100],   # 2 Kitchen
    [120, 220, 100],   # 3 LivingRoom
    [100, 150, 255],   # 4 BedRoom
    [200, 100, 200],   # 5 Bath
    [255, 220, 0],     # 6 Entry
    [180, 120, 80],    # 7 Storage
    [100, 100, 100],   # 8 Garage
    [120, 220, 220],   # 9 Outdoor
], dtype=np.uint8)

# Mapping libellé FR (devis UI) ↔ (c2_class, ocr_hint pour désambig WC).
# Utilisé par l'éditeur de pièces du devis : selectbox utilisateur en FR,
# conversion interne vers le format attendu par compute_devis_for_room().
DEVIS_LABEL_TO_PARAMS: dict[str, tuple[str, str | None]] = {
    "Cuisine": ("Kitchen", None),
    "Séjour / Salon": ("LivingRoom", None),
    "Chambre": ("BedRoom", None),
    "Salle de bain": ("Bath", None),
    "WC": ("Bath", "WC"),
    "Cellier / Buanderie": ("Storage", None),
    "Dégagement / Couloir": ("Entry", None),
    "Garage": ("Garage", None),
    "Extérieur (Terrasse...)": ("Outdoor", None),
}
DEVIS_LABELS = list(DEVIS_LABEL_TO_PARAMS.keys())


def c2_class_to_devis_label(c2_class: str, ocr_hint: str = "") -> str:
    """Convertit c2_class (+ ocr_hint éventuel) vers le libellé FR de l'éditeur."""
    hint_lower = (ocr_hint or "").lower()
    if c2_class == "Bath" and any(w in hint_lower for w in ("wc", "toilette")):
        return "WC"
    return {
        "Kitchen": "Cuisine",
        "LivingRoom": "Séjour / Salon",
        "BedRoom": "Chambre",
        "Bath": "Salle de bain",
        "Storage": "Cellier / Buanderie",
        "Entry": "Dégagement / Couloir",
        "Garage": "Garage",
        "Outdoor": "Extérieur (Terrasse...)",
    }.get(c2_class, "Chambre")  # fallback default


# Couleurs des pastilles du canvas drag-drop : mêmes RGB que PALETTE (overlay
# segmentation) pour cohérence visuelle. Convertit RGB → string CSS.
def _rgb_to_css(rgb: tuple[int, int, int]) -> str:
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


# Mapping label devis (FR) → couleur CSS pastille
DEVIS_LABEL_TO_COLOR: dict[str, str] = {
    "Cuisine": _rgb_to_css((255, 200, 100)),         # orange (Kitchen)
    "Séjour / Salon": _rgb_to_css((120, 220, 100)),   # vert (LivingRoom)
    "Chambre": _rgb_to_css((100, 150, 255)),          # bleu (BedRoom)
    "Salle de bain": _rgb_to_css((200, 100, 200)),    # violet (Bath)
    "WC": _rgb_to_css((255, 240, 150)),               # jaune clair (WC, distinct SDB)
    "Cellier / Buanderie": _rgb_to_css((180, 120, 80)),  # marron (Storage)
    "Dégagement / Couloir": _rgb_to_css((255, 220, 0)),  # jaune (Entry)
    "Garage": _rgb_to_css((180, 180, 180)),           # gris clair
    "Extérieur (Terrasse...)": _rgb_to_css((120, 220, 220)),  # cyan (Outdoor)
}


def _bbox_center(bbox: list[list[int]]) -> tuple[int, int]:
    """Centre d'une bbox polygone (4 points) en (x, y)."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))


DEFAULT_CHECKPOINT = "runs/segmentation/stage_b_finetune_v1/checkpoints/best.pt"

# === YOLO Brique A (détection meubles, 9 classes NFC) — purement visuel ===
YOLO_BRIQUE_A_CHECKPOINT = "runs/detect/runs/detect/brique_a_v1/weights/best.pt"
BATIA_YOLO_CLASSES = [
    "Bathtub", "Shower", "WashBasin", "Toilet", "KitchenSink",
    "Cooktop", "Refrigerator", "WashingMachine", "Bed",
]
# Palette distincte de DEVIS_LABEL_TO_COLOR (qui colore les pièces) — ici on
# colore les MEUBLES. Couleurs vives pour bien voir les bbox sur le plan.
YOLO_BRIQUE_A_COLORS: dict[str, str] = {
    "Bathtub":        _rgb_to_css((70, 130, 180)),    # bleu acier
    "Shower":         _rgb_to_css((0, 191, 255)),     # bleu ciel
    "WashBasin":      _rgb_to_css((64, 224, 208)),    # turquoise
    "Toilet":         _rgb_to_css((138, 43, 226)),    # violet
    "KitchenSink":    _rgb_to_css((50, 205, 50)),     # vert lime
    "Cooktop":        _rgb_to_css((220, 20, 60)),     # rouge crimson
    "Refrigerator":   _rgb_to_css((105, 105, 105)),   # gris foncé
    "WashingMachine": _rgb_to_css((255, 140, 0)),     # orange
    "Bed":            _rgb_to_css((160, 82, 45)),     # marron
}
ALPHA = 0.40
CONFLICT_COLOR_BGR = (0, 0, 255)        # red for conflict outlines
OCR_BOX_COLOR_BGR = (0, 200, 0)         # green for OCR bboxes
WALL_LINE_COLOR_BGR = (255, 0, 255)     # magenta for detected wall lines (BGR=RGB here)


@st.cache_resource(show_spinner=False)
def load_seg_model(checkpoint_path: str, image_size: int) -> SegmentationInference:
    return SegmentationInference(
        checkpoint_path=checkpoint_path,
        image_size=image_size,
        device="auto",
    )


@st.cache_resource(show_spinner=False)
def load_paddleocr_engine() -> PaddleOCREngine:
    return PaddleOCREngine(langs=["fr"])


@st.cache_resource(show_spinner=False)
def load_yolo_brique_a_model(checkpoint_path: str):
    """Lazy-load YOLO Brique A (Ultralytics). Cached resource = chargé une fois."""
    from ultralytics import YOLO
    return YOLO(checkpoint_path)


@st.cache_data(show_spinner=False)
def run_yolo_brique_a(image_bytes: bytes, conf_threshold: float) -> list[dict]:
    """Inférence YOLO Brique A sur l'image. Retourne liste de bbox + classes.

    Cached sur (image bytes, conf) → re-run uniquement si l'image ou le seuil
    change (les filtres par classe sont appliqués côté UI APRÈS l'inférence).
    """
    model = load_yolo_brique_a_model(YOLO_BRIQUE_A_CHECKPOINT)
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    results = model.predict(source=img, conf=conf_threshold, verbose=False)
    out: list[dict] = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls.item())
            cls_name = model.names[cls_id]
            conf_score = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].cpu().numpy()]
            out.append({
                "class_name": cls_name,
                "confidence": conf_score,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            })
    return out


def build_devis_lines_initial(
    devis_global, prices_ht: dict, next_id_start: int = 0,
) -> tuple[list[dict], int]:
    """Transforme un DevisGlobal en lignes initiales (1 ligne par
    (pièce × équipement)). Numérote les pièces de même catégorie ('Chambre 1',
    'Chambre 2'...) si plusieurs.

    Returns:
        (lines, next_id_after) où lines est la liste de dicts, next_id_after
        le prochain _id disponible (pour les ajouts manuels ultérieurs).
    """
    lines: list[dict] = []
    next_id = next_id_start

    # Count pièces par catégorie pour numérotation
    cat_counts: dict[str, int] = {}
    for d in devis_global.per_room:
        c = d.nfc_category.value
        cat_counts[c] = cat_counts.get(c, 0) + 1
    cat_seen: dict[str, int] = {}

    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        if cat_counts[cat] > 1:
            room_label = f"{cat} {cat_seen[cat]}"
        else:
            room_label = cat

        for eq, qty in d.items.items():
            if qty <= 0:
                continue
            lines.append({
                "_id": next_id,
                "Pièce": room_label,
                "Équipement": EQUIPMENT_LABELS_FR[eq],
                "Qté": int(qty),
                "Prix HT (€)": float(prices_ht.get(eq, 0.0)),
                "_manual": False,  # généré par le moteur NFC (vs ajout manuel)
                "_equip_ids": [],  # IDs équipements drag-droppés (Phase 4+)
            })
            next_id += 1
    return lines, next_id


def build_rooms_from_ocr(ocr_hits: list[dict]) -> list[dict]:
    """Construit une liste de pièces depuis les hits OCR matchés à un alias.

    OCR-first MVP : chaque hit OCR matché à un room_type FR (cuisine, chambre,
    wc, etc.) devient une 'pièce' avec un mapping vers la classe C2 (Kitchen,
    BedRoom, etc.) via FR_TO_C2.

    Returns:
        list of dicts: {id, room_type_fr, c2_class, c2_class_id, bbox,
                        confidence, raw_text}
    """
    rooms: list[dict] = []
    counter = 1
    for hit in ocr_hits:
        room_type = hit.get("room_type")
        if not room_type:
            continue
        c2_id = FR_TO_C2.get(room_type)
        if c2_id is None:
            continue
        rooms.append({
            "id": f"ocr_{counter:03d}",
            "room_type_fr": room_type,
            "c2_class": CLASS_NAMES[c2_id],
            "c2_class_id": c2_id,
            "bbox": hit.get("bbox", []),
            "confidence": float(hit.get("confidence", 1.0)),
            "raw_text": hit.get("raw_text", ""),
        })
        counter += 1
    return rooms


@st.cache_data(show_spinner=False)
def run_ocr_raw(image_bytes: bytes, preprocess: bool) -> list[dict]:
    """Returns ALL raw OCR hits (no metric filtering, no confidence cutoff).

    Cached on (image bytes, preprocess flag). Postprocessing/filtering is
    applied in the UI layer so changing the confidence slider doesn't re-run
    the slow inference.

    Uses PaddleOCR (3-pass: normal + 90°CW + 90°CCW for vertical texts).
    """
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    engine = load_paddleocr_engine()
    return engine.read(img, preprocess=preprocess)


def _polygon_centroid(pts: np.ndarray) -> tuple[int, int]:
    M = cv2.moments(pts.reshape(-1, 1, 2))
    if M["m00"] == 0:
        return int(pts[:, 0].mean()), int(pts[:, 1].mean())
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])


def _draw_label_box(canvas, text, x, y, bg_color, border_color=None):
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad_x, pad_y = 6, 4
    x0 = max(0, x - tw // 2 - pad_x)
    y0 = max(0, y - th // 2 - pad_y)
    x1 = x0 + tw + 2 * pad_x
    y1 = y0 + th + 2 * pad_y + baseline
    cv2.rectangle(canvas, (x0, y0), (x1, y1), bg_color, thickness=-1)
    cv2.rectangle(canvas, (x0, y0), (x1, y1),
                  border_color or (255, 255, 255), thickness=2 if border_color else 1)
    cv2.putText(canvas, text, (x0 + pad_x, y1 - pad_y - baseline),
                font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def render_overlay_ocr_only(
    image_bgr: np.ndarray,
    ocr_rooms: list[dict],
    ocr_hits_all: list[dict] | None = None,
    show_ocr_labels: bool = True,
    show_ocr_boxes: bool = False,
) -> np.ndarray:
    """Overlay minimaliste : image originale + bboxes/labels OCR.

    Utilisé quand la segmentation est OFF (MVP OCR-first).

    Args:
        show_ocr_labels: dessine bbox colorée + label pour chaque pièce OCR
                         identifiée (ex: 'Kitchen (Cuisine)')
        show_ocr_boxes: dessine toutes les bboxes OCR brutes en vert fin,
                        y compris celles non matchées (utile pour debug)
    """
    blended = image_bgr.copy()

    # Pass 1 : labels par pièce OCR (bbox colorée + texte)
    if show_ocr_labels:
        for r in ocr_rooms:
            bbox = r.get("bbox", [])
            if not bbox or len(bbox) < 3:
                continue
            cid = r["c2_class_id"]
            color = tuple(int(c) for c in PALETTE[cid])
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(blended, [pts], True, color, thickness=2,
                          lineType=cv2.LINE_AA)
            x_min = int(min(p[0] for p in bbox))
            y_min = int(min(p[1] for p in bbox))
            label = f"{r['c2_class']} ({r['raw_text']})"
            _draw_label_box(blended, label, x_min + 50,
                            max(15, y_min - 5), color)

    # Pass 2 : toutes les bboxes OCR brutes (vert fin, debug)
    if show_ocr_boxes and ocr_hits_all:
        for h in ocr_hits_all:
            bbox = h.get("bbox")
            if not bbox or len(bbox) < 3:
                continue
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(blended, [pts], True, OCR_BOX_COLOR_BGR,
                          thickness=1, lineType=cv2.LINE_AA)
            x, y = int(bbox[0][0]), int(bbox[0][1])
            text = h.get("text", "")[:30]
            cv2.putText(blended, text, (x, max(0, y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, OCR_BOX_COLOR_BGR, 1,
                        cv2.LINE_AA)

    return blended


def render_overlay(
    image_bgr: np.ndarray,
    rooms: list[RoomDetection],
    threshold: float,
    allowed_class_ids: set[int],
    fusion_records: list[dict] | None = None,
    show_ocr_boxes: bool = False,
    ocr_hits_all: list[dict] | None = None,
    simplify_epsilon_pct: float = 0.0,
    axis_align_tolerance_deg: float | None = None,
    wall_lines: list[tuple[int, int, int, int]] | None = None,
    wall_snap_angle_deg: float = 10.0,
    wall_snap_dist_px: float = 25.0,
    show_wall_lines: bool = False,
) -> np.ndarray:
    """Render filtered rooms on top of the original image.

    If fusion_records is provided, conflicts (OCR class ≠ model class) are
    drawn with a red outline + ⚠ prefix in the label.

    simplify_epsilon_pct / axis_align_tolerance_deg control the polygon
    post-processing for cleaner visuals (Douglas-Peucker + axis snap).
    """
    overlay = image_bgr.copy()

    # Build conflict lookup
    conflict_room_ids: set[str] = set()
    ocr_class_by_room: dict[str, int | None] = {}
    if fusion_records:
        for rec in fusion_records:
            ocr_class_by_room[rec["room"].id] = rec.get("ocr_class_id")
            if rec.get("conflict"):
                conflict_room_ids.add(rec["room"].id)

    visible = [
        r for r in rooms
        if r.confidence >= threshold and r.type_id in allowed_class_ids
    ]
    visible.sort(key=lambda r: -r.area_pixels)

    # Pre-simplify polygons once (used in both fill + outline passes)
    polygons_simplified: dict[str, np.ndarray] = {}
    any_postprocess = (
        simplify_epsilon_pct > 0 or axis_align_tolerance_deg or wall_lines
    )
    for r in visible:
        if any_postprocess:
            poly = postprocess_polygon(
                r.polygon,
                simplify_epsilon_pct=simplify_epsilon_pct,
                axis_align_tolerance_deg=axis_align_tolerance_deg,
                wall_lines=wall_lines,
                wall_snap_angle_deg=wall_snap_angle_deg,
                wall_snap_dist_px=wall_snap_dist_px,
            )
        else:
            poly = r.polygon
        polygons_simplified[r.id] = np.array(poly, dtype=np.int32)

    # Pass 1: filled polygons (model class color)
    for r in visible:
        color = tuple(int(c) for c in PALETTE[r.type_id])
        pts = polygons_simplified[r.id]
        cv2.fillPoly(overlay, [pts], color)

    blended = cv2.addWeighted(overlay, ALPHA, image_bgr, 1 - ALPHA, 0)

    # Pass 2: outlines + labels
    for r in visible:
        color = tuple(int(c) for c in PALETTE[r.type_id])
        pts = polygons_simplified[r.id]

        is_conflict = r.id in conflict_room_ids
        outline_color = CONFLICT_COLOR_BGR if is_conflict else color
        outline_th = 4 if is_conflict else 2
        cv2.polylines(blended, [pts], True, outline_color,
                      thickness=outline_th, lineType=cv2.LINE_AA)

        cx, cy = _polygon_centroid(pts)
        if is_conflict:
            ocr_cid = ocr_class_by_room.get(r.id)
            ocr_name = CLASS_NAMES[ocr_cid] if ocr_cid is not None else "?"
            label = f"⚠ {r.type} {r.confidence:.2f} | OCR:{ocr_name}"
            _draw_label_box(blended, label, cx, cy, CONFLICT_COLOR_BGR,
                            border_color=(255, 255, 255))
        else:
            label = f"{r.type} {r.confidence:.2f}"
            _draw_label_box(blended, label, cx, cy, color)

    # Optional: draw all OCR bboxes (green, thin)
    if show_ocr_boxes and ocr_hits_all:
        for h in ocr_hits_all:
            bbox = h.get("bbox")
            if not bbox or len(bbox) < 3:
                continue
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(blended, [pts], True, OCR_BOX_COLOR_BGR,
                          thickness=1, lineType=cv2.LINE_AA)
            x, y = int(bbox[0][0]), int(bbox[0][1])
            cv2.putText(blended, h.get("room_type", "?"), (x, max(0, y - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, OCR_BOX_COLOR_BGR, 1,
                        cv2.LINE_AA)

    # Optional: draw detected wall lines (magenta, thick) — drawn last so they
    # remain visible over the room overlays.
    if show_wall_lines and wall_lines:
        for x1, y1, x2, y2 in wall_lines:
            cv2.line(blended, (x1, y1), (x2, y2),
                     WALL_LINE_COLOR_BGR, thickness=3, lineType=cv2.LINE_AA)

    return blended


def _find_devis_line_idx(
    df_devis: pd.DataFrame,
    room: str,
    equip_type: str,
) -> int | None:
    """Cherche l'index de la ligne (Pièce=room, Équipement=label) dans df_devis."""
    equip_label = EQUIP_TYPES[equip_type]["label"]
    matches = df_devis[
        (df_devis["Pièce"] == room) & (df_devis["Équipement"] == equip_label)
    ]
    if len(matches) == 0:
        return None
    return matches.index[0]


def main():
    st.set_page_config(
        page_title="batIA — Détection de pièces",
        page_icon="🏠",
        layout="wide",
    )
    st.title("🏠 batIA — Détection de pièces (Stage B + OCR)")
    st.caption(
        "Charge un plan, ajuste les filtres, active l'OCR pour confirmer "
        "les détections du modèle avec les labels textuels présents sur le plan."
    )

    # --- Sidebar ---
    with st.sidebar:
        st.header("Plan d'entrée")
        uploaded = st.file_uploader(
            "Plan (PNG / JPEG)",
            type=["png", "jpg", "jpeg"],
            help="Le fichier reste 100% en local."
        )

        # OCR : toujours actif (MVP OCR-first)
        st.markdown("---")
        st.header("🔤 OCR (toujours actif)")
        st.caption(
            "Identification des pièces depuis les labels textuels du plan. "
            "Source primaire des 'Pièces détectées' (la segmentation reste "
            "optionnelle, en complément visuel)."
        )
        enable_ocr = True  # hardcoded : toujours actif
        ocr_confidence_min = st.slider(
            "Confidence min OCR", 0.10, 0.80, 0.30, 0.05,
            help="Filtre les hits OCR sous ce seuil. Baisse-le si certains "
                 "labels visibles ne sont pas reconnus (au prix de bruit accru)."
        )
        show_ocr_labels = st.checkbox(
            "Afficher les labels OCR identifiés (bbox + texte par pièce)",
            value=True,
            help="Encadre chaque pièce identifiée par l'OCR avec une bbox "
                 "colorée + label (ex: 'Kitchen (Cuisine)'). Décoche pour voir "
                 "l'image brute."
        )
        show_ocr_boxes = st.checkbox(
            "Afficher TOUTES les bboxes OCR brutes (vert, debug)",
            value=False,
            help="Affiche toutes les détections OCR (même celles non matchées "
                 "à un alias). Utile pour debug, peut surcharger visuellement."
        )

        # Segmentation : optionnelle, en complément visuel
        st.markdown("---")
        st.header("🧠 Segmentation Mask2Former (optionnel)")
        enable_segmentation = st.checkbox(
            "Activer la segmentation visuelle", value=False,
            help="Lance Mask2Former pour visualiser les contours des pièces en "
                 "overlay coloré. Optionnel : l'OCR seul suffit pour identifier "
                 "les pièces et générer le devis. Active uniquement si tu veux "
                 "voir les polygones (et utiliser snap-to-walls, fusion, etc.)."
        )

        # Filtres pièces (segmentation only) — appliqués à l'overlay polygones
        threshold = 0.30
        class_checks: dict[int, bool] = {cid: True for cid in ROOM_CLASS_IDS}
        if enable_segmentation:
            st.markdown("**Filtres pièces segmentées**")
            threshold = st.slider(
                "Seuil de confiance minimum", 0.0, 1.0, 0.30, 0.05,
                help="Masque les pièces segmentées dont la confiance prédite est < ce seuil."
            )
            st.markdown("**Types de pièces à afficher (overlay)**")
            cols = st.columns(2)
            for i, cid in enumerate(sorted(ROOM_CLASS_IDS)):
                with cols[i % 2]:
                    class_checks[cid] = st.checkbox(
                        CLASS_NAMES[cid], value=True, key=f"cls_{cid}"
                    )
        allowed_class_ids = {cid for cid, on in class_checks.items() if on}

        st.markdown("---")
        st.header("Rendu polygones")
        simplify_epsilon_pct = st.slider(
            "Lissage Douglas-Peucker (% du périmètre)",
            min_value=0.0, max_value=3.0, value=1.0, step=0.1,
            help="0 = polygones bruts (200+ sommets, bords zigzag). "
                 "1-1.5% = compromis lisible. 2-3% = très simplifié, "
                 "perd les coins anguleux."
        )
        axis_align_on = st.checkbox(
            "Forcer les arêtes presque-droites à l'axe horizontal/vertical",
            value=False,
            help="Snap les arêtes dont l'angle est < tolérance à 0°/90°. "
                 "Donne un rendu 'architecte'. À utiliser après simplification."
        )
        axis_align_tolerance_deg = None
        if axis_align_on:
            axis_align_tolerance_deg = st.slider(
                "Tolérance axis-align (°)",
                min_value=2.0, max_value=20.0, value=12.0, step=1.0,
                help="Une arête à ±X° de l'horizontale/verticale sera snappée. "
                     "Trop large = distortions visibles. 10-15° = sweet spot."
            )

        snap_walls_on = st.checkbox(
            "Snap-to-walls (alignement sur murs détectés)", value=False,
            help="Utilise le masque Wall prédit par le modèle (ou Canny+Hough "
                 "sur l'image en fallback) comme contrainte structurelle. Les "
                 "arêtes des pièces sont projetées sur les vraies lignes de "
                 "murs. Donne le rendu le plus réaliste, sensible aux paramètres."
        )
        show_wall_lines = st.checkbox(
            "Afficher les murs détectés (magenta)", value=False,
            disabled=not snap_walls_on,
            help="Dessine les lignes de murs extraites en magenta vif sur "
                 "l'overlay. Utile pour comprendre ce que le snap utilise."
        )
        wall_algorithm = st.selectbox(
            "Algorithme d'extraction de lignes",
            options=["hough", "lsd"],
            index=1,  # LSD par défaut : meilleur sur plans architecturaux
            disabled=not snap_walls_on,
            help="hough = Canny + HoughLinesP, classique, rapide. "
                 "lsd = Line Segment Detector, conçu pour images "
                 "architecturales, plus robuste sur murs gris épais et "
                 "orientations non-orthogonales (plans haussmanniens, mansardés)."
        )
        wall_min_line_length = st.slider(
            "Longueur min des murs détectés (px)",
            min_value=20, max_value=300, value=50, step=10,
            disabled=not snap_walls_on,
            help="Plus haut = filtre les meubles/chaises/cotations courtes. "
                 "Trop haut = on rate les vrais murs courts (ex: petite cloison)."
        )
        wall_max_line_gap = st.slider(
            "Tolérance gap entre segments collinéaires (px)",
            min_value=5, max_value=60, value=20, step=5,
            disabled=not snap_walls_on,
            help="Hough fusionne 2 segments collinéaires si distance entre eux "
                 "< cette valeur. Plus haut = comble les trous (croisements, "
                 "hachures, petites variations d'intensité). Trop haut = "
                 "lignes parasites peuvent être fusionnées."
        )
        wall_filters_on = st.checkbox(
            "Filtres anti-bruit (sombre + axis-aligned)", value=True,
            disabled=not snap_walls_on,
            help="Active : ne garde que les lignes sombres et "
                 "(presque) horizontales/verticales. Filtre escaliers, arcs "
                 "de portes, lignes diagonales. Désactiver pour comparer."
        )
        wall_threshold_strategy = st.selectbox(
            "Stratégie de seuillage",
            options=["manual", "adaptive", "otsu"],
            index=1,  # adaptive par défaut (meilleur que manual sur plans variés)
            disabled=not (snap_walls_on and wall_filters_on),
            help="manual = seuil fixe (slider ci-dessous). "
                 "adaptive = seuil local par patch, gère les plans à intensité "
                 "variable (recommandé). "
                 "otsu = seuil global auto-déterminé par histogramme."
        )
        wall_dark_threshold = st.slider(
            "Seuil sombre (intensité max pour être 'mur')",
            min_value=50, max_value=240, value=150, step=10,
            disabled=not (snap_walls_on and wall_filters_on
                          and wall_threshold_strategy == "manual"),
            help="Actif uniquement en mode manuel. "
                 "Plans à murs noirs : 100-150. "
                 "Plans à murs gris épais : 180-220."
        )
        wall_snap_angle_deg = 10.0
        wall_snap_dist_px = 25.0
        if snap_walls_on:
            wall_snap_angle_deg = st.slider(
                "Tolérance angle (°)",
                min_value=2.0, max_value=20.0, value=10.0, step=1.0,
                help="Une arête de pièce et une ligne de mur sont compatibles "
                     "si leurs angles diffèrent de moins de cette valeur."
            )
            wall_snap_dist_px = st.slider(
                "Tolérance distance (px)",
                min_value=5.0, max_value=80.0, value=25.0, step=5.0,
                help="Distance perpendiculaire max entre le milieu de l'arête "
                     "et la ligne de mur candidate."
            )

        # === Détection meubles YOLO (Brique A) — purement visuel ===
        st.markdown("---")
        st.header("🛠 Détection meubles YOLO (optionnel)")
        enable_yolo = st.checkbox(
            "Activer la détection des meubles",
            value=False,
            help="Lance YOLO11m Brique A pour détecter les meubles "
                 "(Bathtub, Toilet, Bed, etc.) en overlay sur le plan. "
                 "Purement visuel, n'affecte pas le devis ni les pastilles."
        )
        yolo_conf_threshold = 0.25
        yolo_class_checks: dict[str, bool] = {
            name: True for name in BATIA_YOLO_CLASSES
        }
        if enable_yolo:
            yolo_conf_threshold = st.slider(
                "Seuil confiance YOLO", 0.05, 1.0, 0.25, 0.05,
                help="Masque les détections YOLO sous ce seuil."
            )
            st.markdown("**Classes à afficher**")
            cols = st.columns(2)
            for i, cls_name in enumerate(BATIA_YOLO_CLASSES):
                with cols[i % 2]:
                    yolo_class_checks[cls_name] = st.checkbox(
                        cls_name, value=True, key=f"yolo_cls_{cls_name}"
                    )
        yolo_allowed_classes = {n for n, on in yolo_class_checks.items() if on}

        st.markdown("---")
        st.header("💡 Devis NFC")
        st.caption(
            "Génération du devis NFC via le bouton **💡 Générer devis** "
            "au-dessus de l'éditeur de pièces."
        )
        devis_handicap = st.checkbox(
            "Norme handicap", value=False,
            help="Active les règles supplémentaires (prises additionnelles à "
                 "proximité des commandes d'éclairage). Pris en compte au "
                 "prochain click 'Générer devis'."
        )
        devis_tva_label = st.selectbox(
            "Taux TVA",
            options=list(TVA_OPTIONS.keys()),
            index=list(TVA_OPTIONS.keys()).index(TVA_DEFAULT),
            help="Neuf 20% (construction) / Réno 10% (logement > 2 ans) / "
                 "Réno 5.5% (travaux d'amélioration énergétique)."
        )
        devis_tva_rate = TVA_OPTIONS[devis_tva_label]

        st.markdown("---")
        st.header("Modèle")
        checkpoint = st.text_input(
            "Checkpoint", value=DEFAULT_CHECKPOINT,
            help="Chemin vers le .pt (best.pt Stage B par défaut)."
        )
        image_size = st.select_slider(
            "Résolution inférence",
            options=[512, 768, 1024, 1280],
            value=768,
            help="Le modèle a été entraîné à 768. Plus grand = bords + nets "
                 "mais inférence plus lente (×1.8 à 1024, ×2.8 à 1280). "
                 "Changement = recharge modèle (~10 s)."
        )

    # --- Main pane ---
    if uploaded is None:
        st.info("👈 Charge un plan dans la sidebar pour démarrer.")
        st.markdown(
            "**MVP OCR-first** : reconnaissance des pièces basée sur les labels "
            "textuels du plan (PaddleOCR FR multi-rotation) → génération du "
            "devis NFC quantitatif.\n\n"
            f"**Vocabulaire** : {len(FR_TO_C2)} aliases FR → 10 classes C2 "
            "(Cuisine, Chambre, SDB, WC, Séjour, etc.).\n\n"
            "**Segmentation Mask2Former** disponible en complément visuel "
            "(toggle dans la sidebar)."
        )
        return

    # Persistent bytes for caching
    img_bytes = uploaded.getvalue()
    img_hash = hashlib.md5(img_bytes).hexdigest()[:12]

    # Save upload to a temp file (SegmentationInference reads from path)
    suffix = Path(uploaded.name).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name

    # === Pipeline d'analyse : OCR + Segmentation (optionnelle) ===
    # Stratégie cache pour éviter le "saut visuel" à chaque rerun (causé par
    # les interactions widget) :
    # - OCR : @st.cache_data décore run_ocr_raw → instant après 1er run
    # - Segmentation : inference.predict() N'EST PAS cached → on stocke le
    #   résultat en session_state pour éviter de re-inférer à chaque rerun
    # - st.status() : affiché UNIQUEMENT si cache miss (sinon l'apparition+
    #   collapse à chaque rerun fait sauter la page)
    result: SegmentationOutput | None = None
    fusion_records: list[dict] | None = None
    ocr_hits_raw: list[dict] = []
    ocr_hits: list[dict] = []

    ocr_done_key = f"ocr_first_done_{img_hash}"
    seg_cache_key = (
        f"seg_result_{img_hash}_{Path(checkpoint).name}_{image_size}"
        if enable_segmentation else None
    )
    needs_ocr_compute = ocr_done_key not in st.session_state
    needs_seg_compute = (
        enable_segmentation and seg_cache_key not in st.session_state
    )
    show_progress = needs_ocr_compute or needs_seg_compute

    # st.status TOUJOURS rendu (collapsed après le 1er run) pour conserver
    # une hauteur stable de la page → pas de saut visuel quand on passe du
    # "1er upload avec progress" à "rerun cached silencieux".
    _initial_label = (
        "🔍 Analyse du plan en cours..." if show_progress
        else "✓ Analyse terminée (depuis le cache)"
    )
    _initial_state = "running" if show_progress else "complete"
    with st.status(
        _initial_label, expanded=show_progress, state=_initial_state,
    ) as status:
        try:
            if show_progress:
                st.write("⏳ Chargement du modèle OCR PaddleOCR FR...")
            engine = load_paddleocr_engine()
            if show_progress:
                st.write("✓ Modèle OCR prêt")
                st.write(
                    "⏳ Lecture du plan (OCR 3 passes : "
                    "normal + ±90° pour textes verticaux)..."
                )

            ocr_hits_raw = run_ocr_raw(img_bytes, preprocess=False)
            if show_progress:
                st.write(f"✓ {len(ocr_hits_raw)} textes bruts détectés")
                st.session_state[ocr_done_key] = True
                st.write("⏳ Filtrage + matching alias français...")

            ocr_hits = postprocess_ocr_items(
                ocr_hits_raw, confidence_min=ocr_confidence_min,
                fuzzy=True, fuzzy_cutoff=0.72,
            )
            if show_progress:
                n_rooms_ocr = sum(1 for h in ocr_hits if h.get("room_type"))
                st.write(
                    f"✓ {n_rooms_ocr} pièces identifiées "
                    f"({len(ocr_hits)} labels retenus)"
                )

            if enable_segmentation:
                if not Path(checkpoint).exists():
                    status.update(
                        label="❌ Checkpoint segmentation introuvable",
                        state="error", expanded=True,
                    )
                    st.error(f"Checkpoint introuvable : `{checkpoint}`")
                    return
                if seg_cache_key in st.session_state:
                    result = st.session_state[seg_cache_key]
                else:
                    if show_progress:
                        st.write("⏳ Chargement du modèle Mask2Former...")
                    inference = load_seg_model(checkpoint, image_size)
                    if show_progress:
                        st.write("✓ Modèle segmentation prêt")
                        st.write("⏳ Inférence segmentation (Mask2Former Swin-S)...")
                    result = inference.predict(tmp_path)
                    st.session_state[seg_cache_key] = result
                    if show_progress:
                        st.write(
                            f"✓ Segmentation terminée en {result.inference_time_ms} ms "
                            f"({len(result.rooms)} polygones)"
                        )
                fusion_records = fuse_rooms_with_ocr(result.rooms, ocr_hits)

            if show_progress:
                status.update(
                    label="✓ Analyse terminée", state="complete", expanded=False,
                )
        except Exception as e:
            status.update(
                label=f"❌ Erreur pendant l'analyse : {type(e).__name__}",
                state="error", expanded=True,
            )
            st.exception(e)
            return

    # Load original image for overlay
    image_bgr = cv2.imread(tmp_path)
    if image_bgr is None:
        st.error("Impossible de lire l'image.")
        return

    # === Construction des pièces depuis OCR (source primaire) ===
    ocr_rooms = build_rooms_from_ocr(ocr_hits)

    # === Snap-to-walls (uniquement si segmentation activée) ===
    wall_lines: list[tuple[int, int, int, int]] | None = None
    wall_source: str = ""
    if enable_segmentation and snap_walls_on and result is not None:
        wall_mask_path = Path(result.walls.mask_path)
        if wall_mask_path.exists():
            wall_mask = cv2.imread(str(wall_mask_path), cv2.IMREAD_GRAYSCALE)
            if wall_mask is not None and wall_mask.max() > 0:
                wall_lines = extract_wall_lines(wall_mask)
                wall_source = f"masque Wall du modèle ({(wall_mask > 0).sum():,} px)"
        if not wall_lines:
            wall_lines = extract_lines_from_image(
                image_bgr,
                algorithm=wall_algorithm,
                min_line_length=wall_min_line_length,
                max_line_gap=wall_max_line_gap,
                threshold_strategy=wall_threshold_strategy if wall_filters_on else "manual",
                dark_threshold=wall_dark_threshold if wall_filters_on else None,
                morph_open_kernel=3 if wall_filters_on else 1,
                axis_aligned_only=wall_filters_on,
            )
            wall_source = (
                f"image originale ({wall_algorithm.upper()}, seuillage: {wall_threshold_strategy})"
                if wall_filters_on
                else f"image originale ({wall_algorithm.upper()}, brut sans filtre)"
            )
        if not wall_lines:
            st.warning(
                "Snap-to-walls activé mais Hough n'a trouvé aucune ligne."
            )

    # === Métriques OCR/segmentation (l'overlay visuel est remplacé par le
    # canvas drag-drop ci-dessous — fonctions render_overlay*/imports gardées
    # au cas où on voudrait re-ajouter un toggle "voir overlay debug") ===
    metric_cols = st.columns(4)
    metric_cols[0].metric("Labels OCR détectés", len(ocr_hits))
    metric_cols[1].metric("Pièces identifiées (OCR)", len(ocr_rooms))
    if enable_segmentation and result is not None:
        metric_cols[2].metric(
            "Segmentation", f"{result.inference_time_ms} ms",
            help=f"{image_size}×{image_size}",
        )
        n_seg_visible = sum(
            1 for r in result.rooms
            if r.confidence >= threshold and r.type_id in allowed_class_ids
        )
        metric_cols[3].metric(
            "Polygones", f"{n_seg_visible} / {len(result.rooms)}",
        )
        if fusion_records:
            n_conflict = sum(1 for r in fusion_records if r["conflict"])
            if n_conflict > 0:
                st.warning(f"⚠ {n_conflict} conflit(s) OCR/modèle à vérifier")

    # Key éditeur Pièces : remontée AVANT le canvas car les 2 sections en ont
    # besoin (canvas pour sync DataFrame, éditeur pour init).
    editor_key = f"devis_editor_{img_hash}"
    next_id_key = f"{editor_key}_nextid"

    # --- Canvas pastilles drag-drop (Phase 2 : drag + out-of-bbox suppr) ---
    st.markdown("---")
    st.markdown("### 🎯 Plan interactif (drag-and-drop)")
    st.caption(
        "Pastilles colorées posées sur le plan aux positions détectées par "
        "l'OCR. **Drag** pour repositionner. **Sortir du plan** pour "
        "supprimer la pièce du devis. Palette à droite (drag-in en Phase 3)."
    )

    # Clé session_state : positions/visibilité des pastilles persistées
    # entre les reruns Streamlit (sinon les drags seraient perdus à chaque
    # interaction widget).
    pastilles_state_key = f"pastilles_state_{img_hash}"

    # Init from OCR au premier render pour cette image
    if pastilles_state_key not in st.session_state:
        init_pastilles: list[dict] = []
        for r in ocr_rooms:
            bbox = r.get("bbox", [])
            if not bbox:
                continue
            cx, cy = _bbox_center(bbox)
            label_fr = c2_class_to_devis_label(r["c2_class"], r.get("raw_text", ""))
            init_pastilles.append({
                "id": r["id"],
                "type": label_fr,
                "label": label_fr,
                "x": cx,
                "y": cy,
                "color": DEVIS_LABEL_TO_COLOR.get(label_fr, "rgb(200,200,200)"),
            })
        st.session_state[pastilles_state_key] = init_pastilles

    # Réconciliation : si une row a été supprimée via 🗑️ table → pastille
    # correspondante doit aussi disparaître du canvas
    df_editor_current = st.session_state.get(editor_key)
    if df_editor_current is not None and "_pastille_id" in df_editor_current.columns:
        valid_pids = set(
            df_editor_current["_pastille_id"].dropna().astype(str).tolist()
        )
        st.session_state[pastilles_state_key] = [
            p for p in st.session_state[pastilles_state_key]
            if str(p["id"]) in valid_pids
        ]

    # Palette : tous les types de pièces dispos pour drag-in (Phase 3)
    palette: list[dict] = [
        {"type": lbl, "label": lbl, "color": color}
        for lbl, color in DEVIS_LABEL_TO_COLOR.items()
    ]

    # Palette équipements (Phase 2 : statique, drag-in en Phase 4)
    equip_palette_for_canvas: list[dict] = [
        {"type": key, "label": info["label"], "color": info["color"],
         "svg_id": info["svg_id"]}
        for key, info in EQUIP_TYPES.items()
    ]

    # Encode l'image originale en PNG pour transit au component
    _, encoded = cv2.imencode(".png", image_bgr)
    image_h, image_w = image_bgr.shape[:2]

    # Polygones segmentation à dessiner en overlay SVG sous les pastilles.
    # Filtrés par threshold + classes autorisées. Si snap-to-walls activé,
    # on passe les polygones par postprocess_polygon (simplify + axis-align +
    # snap aux wall_lines détectées) pour qu'ils suivent les murs réels.
    seg_polygons: list[dict] = []
    if enable_segmentation and result is not None:
        # Active la postprocess si l'user a activé snap-walls/simplification/axis-align
        snap_active_walls = wall_lines if snap_walls_on else None
        any_postprocess = (
            simplify_epsilon_pct > 0 or axis_align_tolerance_deg or snap_active_walls
        )
        for room in result.rooms:
            if room.confidence < threshold:
                continue
            if room.type_id not in allowed_class_ids:
                continue
            if any_postprocess:
                poly = postprocess_polygon(
                    room.polygon,
                    simplify_epsilon_pct=simplify_epsilon_pct,
                    axis_align_tolerance_deg=axis_align_tolerance_deg,
                    wall_lines=snap_active_walls,
                    wall_snap_angle_deg=wall_snap_angle_deg,
                    wall_snap_dist_px=wall_snap_dist_px,
                )
            else:
                poly = room.polygon
            rgb = PALETTE[room.type_id]
            r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
            seg_polygons.append({
                "type_name": room.type,
                "points": [[int(p[0]), int(p[1])] for p in poly],
                "fill": f"rgba({r},{g},{b},0.35)",
                "stroke": f"rgb({r},{g},{b})",
            })

    # YOLO Brique A — bbox meubles (purement visuel, n'affecte pas devis).
    # Si activé : run inference (cached), filtre par classes cochées + couleur.
    # Si checkpoint absent : warning discret + skip (pas de crash).
    yolo_boxes: list[dict] = []
    if enable_yolo:
        yolo_ckpt = Path(YOLO_BRIQUE_A_CHECKPOINT)
        if not yolo_ckpt.exists():
            st.warning(
                f"⚠ Checkpoint YOLO Brique A introuvable : `{yolo_ckpt}`. "
                "Train le modèle (`python scripts/train_yolo.py "
                "--config configs/yolo/brique_a.yaml`) ou décoche l'option."
            )
        else:
            raw_boxes = run_yolo_brique_a(img_bytes, yolo_conf_threshold)
            yolo_boxes = [
                {
                    "class_name": b["class_name"],
                    "x1": int(b["x1"]), "y1": int(b["y1"]),
                    "x2": int(b["x2"]), "y2": int(b["y2"]),
                    "confidence": round(float(b["confidence"]), 2),
                    "color": YOLO_BRIQUE_A_COLORS.get(
                        b["class_name"], "rgb(255,0,255)",
                    ),
                }
                for b in raw_boxes
                if b["class_name"] in yolo_allowed_classes
            ]

    equipments_state_key = f"equipments_state_{img_hash}"
    if equipments_state_key not in st.session_state:
        st.session_state[equipments_state_key] = []

    canvas_state = pastille_canvas(
        image_bytes=encoded.tobytes(),
        image_width=image_w,
        image_height=image_h,
        initial_pastilles=st.session_state[pastilles_state_key],
        palette=palette,
        seg_polygons=seg_polygons,
        yolo_boxes=yolo_boxes,
        equipments=st.session_state[equipments_state_key],
        equip_palette=equip_palette_for_canvas,
        key=f"pastille_canvas_{img_hash}",
    )

    # === Sync canvas → Python ===
    # Le component notifie son nouvel état dans canvas_state. On compare avec
    # session_state pour détecter ce qui a changé.
    if canvas_state is not None:
        new_pastilles = canvas_state.get("pastilles", [])
        current_state = st.session_state[pastilles_state_key]
        current_pids = {str(p["id"]) for p in current_state}
        new_pids = {str(p["id"]) for p in new_pastilles}
        removed_pids = current_pids - new_pids
        added_pastilles = [p for p in new_pastilles if str(p["id"]) not in current_pids]

        # Update session_state avec les nouvelles positions / suppressions / ajouts
        st.session_state[pastilles_state_key] = new_pastilles

        # Sync équipements (Phase 3+4) : positions, suppressions hors-image,
        # ajouts via palette. Persiste AVANT tout st.rerun().
        new_equipments = canvas_state.get("equipments", [])
        current_equipments = st.session_state[equipments_state_key]
        current_eq_ids = {e["id"] for e in current_equipments}
        new_eq_ids = {e["id"] for e in new_equipments}

        added_palette_eqs = [
            e for e in new_equipments
            if e["id"] not in current_eq_ids and e["id"].startswith("new_")
        ]
        removed_eq_ids = current_eq_ids - new_eq_ids

        st.session_state[equipments_state_key] = new_equipments

        # Phase 4 : sync devis pour ajouts (palette) et suppressions
        devis_lines_key = f"devis_lines_{img_hash}"

        if added_palette_eqs and devis_lines_key in st.session_state:
            df_devis = st.session_state[devis_lines_key].copy()
            for eq in added_palette_eqs:
                line_idx = _find_devis_line_idx(df_devis, eq["room"], eq["type"])
                if line_idx is not None:
                    df_devis.at[line_idx, "Qté"] = int(
                        df_devis.at[line_idx, "Qté"]
                    ) + 1
                    if "_equip_ids" in df_devis.columns:
                        ids_list = list(df_devis.at[line_idx, "_equip_ids"] or [])
                        ids_list.append(eq["id"])
                        df_devis.at[line_idx, "_equip_ids"] = ids_list
                else:
                    st.warning(
                        f"Équipement ajouté pour pièce '{eq['room']}' qui n'a "
                        "pas de ligne devis correspondante. Ajoute-la d'abord "
                        "via le tableau devis."
                    )
            st.session_state[devis_lines_key] = df_devis
            st.rerun()

        if removed_eq_ids and devis_lines_key in st.session_state:
            df_devis = st.session_state[devis_lines_key].copy()
            for line_idx in df_devis.index:
                if "_equip_ids" not in df_devis.columns:
                    break
                ids_list = list(df_devis.at[line_idx, "_equip_ids"] or [])
                kept_ids = [i for i in ids_list if i not in removed_eq_ids]
                n_removed = len(ids_list) - len(kept_ids)
                if n_removed > 0:
                    df_devis.at[line_idx, "_equip_ids"] = kept_ids
                    df_devis.at[line_idx, "Qté"] = int(
                        df_devis.at[line_idx, "Qté"]
                    ) - n_removed
            st.session_state[devis_lines_key] = df_devis
            st.rerun()

        # Phase 2 : sync DataFrame éditeur : drop rows dont pastille supprimée
        if removed_pids and df_editor_current is not None \
                and "_pastille_id" in df_editor_current.columns:
            to_remove_mask = (
                df_editor_current["_pastille_id"].notna()
                & df_editor_current["_pastille_id"].astype(str).isin(removed_pids)
            )
            if to_remove_mask.any():
                removed_row_ids = df_editor_current[to_remove_mask]["_id"].tolist()
                df_editor_clean = df_editor_current[~to_remove_mask].reset_index(drop=True)
                st.session_state[editor_key] = df_editor_clean
                # Cleanup widget states pour les rows supprimées
                for rid in removed_row_ids:
                    for prefix in ("inc", "type", "surf", "notes", "del"):
                        k = f"{editor_key}_{prefix}_{rid}"
                        if k in st.session_state:
                            del st.session_state[k]
                st.rerun()

        # Phase 3 : sync DataFrame éditeur : ajoute row pour chaque pastille
        # nouvellement drag-droppée depuis la palette (id préfixé "new_")
        if added_pastilles and df_editor_current is not None:
            new_rows = []
            for p in added_pastilles:
                pid = str(p["id"])
                if not pid.startswith("new_"):
                    continue  # safety : skip pastilles non-manuelles
                new_id = st.session_state.get(next_id_key, 0)
                st.session_state[next_id_key] = new_id + 1
                p_type = str(p.get("type", "Chambre"))
                new_rows.append({
                    "_id": new_id,
                    "_pastille_id": pid,
                    "Inclure": True,
                    "Type": p_type,
                    "Surface (m²)": 0.0,
                    "Notes / texte OCR": "(drag depuis palette)",
                })
            if new_rows:
                df_editor_extended = pd.concat(
                    [df_editor_current, pd.DataFrame(new_rows)],
                    ignore_index=True,
                )
                st.session_state[editor_key] = df_editor_extended
                # Pré-init widget states pour les nouvelles rows
                for row in new_rows:
                    rid = row["_id"]
                    st.session_state[f"{editor_key}_inc_{rid}"] = True
                    st.session_state[f"{editor_key}_type_{rid}"] = row["Type"]
                    st.session_state[f"{editor_key}_surf_{rid}"] = 0.0
                    st.session_state[f"{editor_key}_notes_{rid}"] = row["Notes / texte OCR"]
                st.rerun()

    # Debug expander (utile pendant le dev, à retirer en prod)
    with st.expander("🔍 Debug pastilles canvas (Phase 2)"):
        st.write(f"**Pastilles en session_state** : {len(st.session_state.get(pastilles_state_key, []))}")
        if canvas_state is not None:
            st.write(f"**Dernier canvas_state** : {len(canvas_state.get('pastilles', []))} pastilles")
        st.json(st.session_state.get(pastilles_state_key, []))

    # --- Éditeur de pièces interactif (OCR-first + édition manuelle) ---
    st.markdown("---")
    st.markdown("### 🛠 Pièces à inclure dans le devis")
    st.caption(
        "Pièces pré-détectées par OCR (toutes cochées par défaut). "
        "**Décoche** pour exclure une pièce du devis, **modifie** le type si "
        "l'OCR s'est trompé, **ajoute** une pièce manuellement si l'OCR l'a "
        "manquée."
    )

    # (editor_key déjà défini plus haut, avant le canvas pastilles)

    # Init du DataFrame en session_state au premier rendu pour cette image.
    # Chaque ligne reçoit un _id stable (compteur monotone) pour servir de
    # CLEF DE WIDGET — sinon les keys basées sur l'index pandas sont décalées
    # après chaque suppression et un click 🗑️ sur ligne N supprime la mauvaise.
    # (next_id_key déjà défini plus haut, avant le canvas pastilles)
    if editor_key not in st.session_state:
        st.session_state[next_id_key] = 0
        initial_rows: list[dict] = []
        for r in ocr_rooms:
            label = c2_class_to_devis_label(r["c2_class"], r.get("raw_text", ""))
            initial_rows.append({
                "_id": st.session_state[next_id_key],
                "_pastille_id": r["id"],  # lien vers la pastille canvas
                "Inclure": True,
                "Type": label,
                "Surface (m²)": 0.0,
                "Notes / texte OCR": r["raw_text"][:50],
            })
            st.session_state[next_id_key] += 1
        if not initial_rows:
            initial_rows = [{
                "_id": 0, "_pastille_id": None,
                "Inclure": True, "Type": "Chambre",
                "Surface (m²)": 0.0, "Notes / texte OCR": "",
            }]
            st.session_state[next_id_key] = 1
        st.session_state[editor_key] = pd.DataFrame(initial_rows)

    # === PRÉ-INIT widget states pour TOUTES les lignes ===
    # Le DataFrame en st.session_state[editor_key] est la SOURCE DE VÉRITÉ.
    # Les widgets utilisent on_change pour sync IMMÉDIATEMENT le DataFrame
    # dès que l'user change une valeur. Au début de chaque rerun, on
    # FORCE-SYNC le widget state depuis le DataFrame → garantit que le
    # widget affiche TOUJOURS la valeur courante du DataFrame, même si
    # Streamlit reset le widget state pour une raison quelconque.
    _df_init = st.session_state[editor_key]
    for _idx in _df_init.index:
        _rid = int(_df_init.loc[_idx, "_id"])
        # Force-sync : écrase le widget state avec la valeur du DataFrame
        # (qui a été mise à jour par on_change au précédent rerun)
        st.session_state[f"{editor_key}_type_{_rid}"] = str(_df_init.loc[_idx, "Type"])
        st.session_state[f"{editor_key}_inc_{_rid}"] = bool(_df_init.loc[_idx, "Inclure"])
        st.session_state[f"{editor_key}_surf_{_rid}"] = float(_df_init.loc[_idx, "Surface (m²)"])
        st.session_state[f"{editor_key}_notes_{_rid}"] = str(_df_init.loc[_idx, "Notes / texte OCR"])

    # === Callbacks on_change : sync widget value → DataFrame ===
    # CRITIQUE : sans ces callbacks, le DataFrame ne reflète JAMAIS les
    # éditions utilisateur. Conséquence : type_total lit l'init "Chambre",
    # le devis génère des équipements de Chambre au lieu de WC, etc.
    def _on_edit_field(rid: int, widget_suffix: str, df_field: str, caster):
        wkey = f"{editor_key}_{widget_suffix}_{rid}"
        if wkey not in st.session_state:
            return
        df_cur = st.session_state[editor_key]
        mask = df_cur["_id"] == rid
        df_cur.loc[mask, df_field] = caster(st.session_state[wkey])
        st.session_state[editor_key] = df_cur

    # Boutons d'action en haut : Ajouter pièce + Générer devis + Réinitialiser
    devis_state_key = f"devis_generated_{img_hash}"
    col_add, col_devis, _, col_reset = st.columns([1, 1, 2, 1])
    with col_add:
        if st.button("➕ Ajouter une pièce", key=f"{editor_key}_add"):
            new_id = st.session_state[next_id_key]
            st.session_state[next_id_key] += 1
            new_row = pd.DataFrame([{
                "_id": new_id,
                "_pastille_id": None,  # manuel → pas de pastille (Phase 3 via palette)
                "Inclure": True, "Type": "Chambre",
                "Surface (m²)": 0.0, "Notes / texte OCR": "(ajout manuel)",
            }])
            st.session_state[editor_key] = pd.concat(
                [st.session_state[editor_key], new_row], ignore_index=True,
            )
            # Pré-init widget states pour la nouvelle ligne → disponibles dès
            # le prochain render (évite fallback "Chambre" du type_total loop)
            st.session_state[f"{editor_key}_inc_{new_id}"] = True
            st.session_state[f"{editor_key}_type_{new_id}"] = "Chambre"
            st.session_state[f"{editor_key}_surf_{new_id}"] = 0.0
            st.session_state[f"{editor_key}_notes_{new_id}"] = "(ajout manuel)"
            st.rerun()
    with col_devis:
        if st.button("💡 Générer devis", key=f"{editor_key}_gen",
                     type="primary"):
            st.session_state[devis_state_key] = True
            # Avant reset : sauvegarder les lignes ajoutées manuellement EN
            # LISANT LES WIDGET STATES (pas le DataFrame, qui n'a pas les
            # valeurs éditées par l'utilisateur).
            dl_key = f"devis_lines_{img_hash}"
            manual_backup_key = f"{dl_key}_manual_backup"
            if dl_key in st.session_state:
                existing_devis = st.session_state[dl_key]
                if "_manual" in existing_devis.columns:
                    manual_rows: list[dict] = []
                    for idx in existing_devis.index:
                        if not bool(existing_devis.loc[idx, "_manual"]):
                            continue
                        rid = int(existing_devis.loc[idx, "_id"])
                        backup_ids = []
                        if "_equip_ids" in existing_devis.columns:
                            backup_ids = list(
                                existing_devis.loc[idx, "_equip_ids"] or []
                            )
                        manual_rows.append({
                            "Pièce": st.session_state.get(
                                f"{dl_key}_piece_{rid}",
                                str(existing_devis.loc[idx, "Pièce"]),
                            ),
                            "Équipement": st.session_state.get(
                                f"{dl_key}_eq_{rid}",
                                str(existing_devis.loc[idx, "Équipement"]),
                            ),
                            "Qté": int(st.session_state.get(
                                f"{dl_key}_qty_{rid}",
                                int(existing_devis.loc[idx, "Qté"]),
                            )),
                            "Prix HT (€)": float(st.session_state.get(
                                f"{dl_key}_ht_{rid}",
                                float(existing_devis.loc[idx, "Prix HT (€)"]),
                            )),
                            "_equip_ids": backup_ids,
                        })
                    if manual_rows:
                        st.session_state[manual_backup_key] = manual_rows
            # Reset complet du tableau devis pour reconstruction
            keys_to_del = [
                k for k in list(st.session_state.keys())
                if k.startswith(dl_key) and k != manual_backup_key
            ]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()
    with col_reset:
        if st.button(
            "🔄 Réinitialiser", key=f"{editor_key}_reset",
            help="Efface toutes les éditions et reconstruit le tableau depuis "
                 "les pièces détectées par OCR.",
        ):
            # Supprime toutes les clés session_state liées à ce plan
            keys_to_del = [
                k for k in list(st.session_state.keys())
                if k.startswith(editor_key) or k.startswith(devis_state_key)
            ]
            for k in keys_to_del:
                del st.session_state[k]
            st.rerun()

    if not ocr_rooms and len(st.session_state[editor_key]) == 1:
        st.warning(
            "Aucune pièce identifiée par l'OCR. Ajoute des pièces manuellement "
            "via le bouton ➕ et configure leur type."
        )

    # === Rendu custom row-by-row : VRAIS boutons 🗑️ par ligne ===
    # Layout : 6 colonnes [#, Inclure, Type, Surface, Notes, Bouton Suppr.]
    COL_PROPS = [0.4, 1, 4, 2, 5, 1]

    # Headers
    header_cols = st.columns(COL_PROPS)
    header_cols[0].markdown("**#**", help="Numéro d'occurrence pour ce type "
                                          "(ex: WC 2 = 2ème WC)")
    header_cols[1].markdown("**Inclure**")
    header_cols[2].markdown("**Type de pièce**")
    header_cols[3].markdown("**Surface (m²)**")
    header_cols[4].markdown("**Notes / texte OCR**")
    header_cols[5].markdown("**Suppr.**")
    st.divider()

    df = st.session_state[editor_key]
    ids_to_delete: list[int] = []

    # Compteurs lus DEPUIS LE DATAFRAME (source de vérité, sync via on_change)
    type_total: dict[str, int] = {}
    for idx in df.index:
        current_type = str(df.loc[idx, "Type"])
        type_total[current_type] = type_total.get(current_type, 0) + 1
    type_seen_count: dict[str, int] = {}

    for idx in df.index:
        row = df.loc[idx]
        row_id = int(row["_id"])
        current_type = str(row["Type"])
        type_seen_count[current_type] = type_seen_count.get(current_type, 0) + 1
        idx_label = (
            str(type_seen_count[current_type])
            if type_total.get(current_type, 0) >= 2 else ""
        )

        cols = st.columns(COL_PROPS)
        with cols[0]:
            if idx_label:
                st.markdown(
                    f"<div style='padding-top: 0.5rem; text-align: center; "
                    f"color: #666; font-weight: 600;'>{idx_label}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown("")
        # Widgets avec on_change → sync DataFrame instantanément
        with cols[1]:
            st.checkbox(
                "Inclure cette pièce",
                key=f"{editor_key}_inc_{row_id}",
                on_change=_on_edit_field,
                args=(row_id, "inc", "Inclure", bool),
                label_visibility="collapsed",
            )
        with cols[2]:
            st.selectbox(
                "Type de pièce", DEVIS_LABELS,
                key=f"{editor_key}_type_{row_id}",
                on_change=_on_edit_field,
                args=(row_id, "type", "Type", str),
                label_visibility="collapsed",
            )
        with cols[3]:
            st.number_input(
                "Surface",
                min_value=0.0, max_value=300.0, step=1.0,
                key=f"{editor_key}_surf_{row_id}",
                on_change=_on_edit_field,
                args=(row_id, "surf", "Surface (m²)", float),
                label_visibility="collapsed",
            )
        with cols[4]:
            st.text_input(
                "Notes",
                key=f"{editor_key}_notes_{row_id}",
                on_change=_on_edit_field,
                args=(row_id, "notes", "Notes / texte OCR", str),
                label_visibility="collapsed",
            )
        with cols[5]:
            if st.button(
                "🗑️", key=f"{editor_key}_del_{row_id}",
                help="Supprimer définitivement cette pièce du tableau",
            ):
                ids_to_delete.append(row_id)

    # Process deletions : drop par _id (pas par index pandas)
    if ids_to_delete:
        new_df = df[~df["_id"].isin(ids_to_delete)].reset_index(drop=True)
        st.session_state[editor_key] = new_df
        for row_id in ids_to_delete:
            for prefix in ("inc", "type", "surf", "notes", "del"):
                k = f"{editor_key}_{prefix}_{row_id}"
                if k in st.session_state:
                    del st.session_state[k]
        st.rerun()

    # edited_df = DataFrame directement (déjà sync via on_change)
    edited_df = df.copy()

    # Compteur live
    n_total = len(edited_df)
    n_inclus = int(edited_df["Inclure"].sum()) if n_total > 0 else 0
    st.caption(
        f"📊 **{n_inclus}** pièces cochées sur **{n_total}** au total"
    )

    # --- Devis (basé sur NF C 15-100) — affiché après click 'Générer devis' ---
    if st.session_state.get(devis_state_key, False):
        st.markdown("---")
        st.markdown("### 💡 Devis quantitatif (basé sur norme NF C 15-100)")
        if devis_handicap:
            st.caption("🦽 Norme handicap activée")

        # Construit rooms_input depuis le DataFrame édité (uniquement les lignes
        # cochées avec un Type valide)
        rooms_input: list[dict] = []
        for idx, row in edited_df.iterrows():
            if not row.get("Inclure", False):
                continue
            label = row.get("Type")
            if not label or label not in DEVIS_LABEL_TO_PARAMS:
                continue
            c2_class, forced_hint = DEVIS_LABEL_TO_PARAMS[label]
            surface = float(row.get("Surface (m²)") or 0.0)
            rooms_input.append({
                "id": f"room_{idx + 1:03d}",
                "c2_class": c2_class,
                "surface_m2": surface if surface > 0 else None,
                # Si label='WC', on force ocr_hint='WC' pour que le moteur NFC
                # applique les règles WC (allégées) au lieu de SDB
                "ocr_hint": forced_hint or row.get("Notes / texte OCR", ""),
            })

        if not rooms_input:
            st.warning(
                "Aucune pièce cochée dans l'éditeur. "
                "Coche au moins une pièce pour générer le devis."
            )
        else:
            # === Tableau détail devis (éditable, ligne par ligne) ===
            devis_lines_key = f"devis_lines_{img_hash}"
            devis_lines_nid_key = f"{devis_lines_key}_nextid"

            # Init depuis le DevisGlobal (1er render OU après reset via bouton
            # "Générer devis" qui efface cette session_state). Les lignes
            # manuelles sauvegardées dans manual_backup sont réinjectées à la
            # bonne position (juste après la dernière ligne de leur pièce).
            if devis_lines_key not in st.session_state:
                devis = compute_devis_global(
                    rooms_input, handicap=devis_handicap,
                )
                lines, next_id_after = build_devis_lines_initial(
                    devis, DEFAULT_PRICES_HT, next_id_start=0,
                )
                manual_backup_key = f"{devis_lines_key}_manual_backup"
                if manual_backup_key in st.session_state:
                    for m_row in st.session_state[manual_backup_key]:
                        m_row["_id"] = next_id_after
                        m_row["_manual"] = True
                        next_id_after += 1
                        target_piece = m_row.get("Pièce")
                        last_idx = None
                        for i, l in enumerate(lines):
                            if l.get("Pièce") == target_piece:
                                last_idx = i
                        if last_idx is not None:
                            lines.insert(last_idx + 1, m_row)
                        else:
                            lines.append(m_row)
                    del st.session_state[manual_backup_key]
                st.session_state[devis_lines_key] = pd.DataFrame(lines)
                st.session_state[devis_lines_nid_key] = next_id_after

            # Liste des pièces existantes dans le devis (pour selectbox Pièce)
            df_devis_current = st.session_state[devis_lines_key]
            existing_pieces = sorted(
                set(df_devis_current["Pièce"].astype(str).unique())
            )
            if "Autre" not in existing_pieces:
                existing_pieces.append("Autre")

            # === FORCE-SYNC widget states depuis le DataFrame ===
            # DataFrame = source de vérité (mis à jour via on_change). À chaque
            # rerun, on force-set le widget state pour qu'il matche le DF.
            for _idx in df_devis_current.index:
                _rid = int(df_devis_current.loc[_idx, "_id"])
                _piece_val = str(df_devis_current.loc[_idx, "Pièce"])
                st.session_state[f"{devis_lines_key}_piece_{_rid}"] = (
                    _piece_val if _piece_val in existing_pieces else "Autre"
                )
                _eq_val = str(df_devis_current.loc[_idx, "Équipement"])
                st.session_state[f"{devis_lines_key}_eq_{_rid}"] = (
                    _eq_val if _eq_val in EQUIPMENT_LABELS_LIST
                    else EQUIPMENT_LABELS_LIST[0]
                )
                st.session_state[f"{devis_lines_key}_qty_{_rid}"] = int(
                    df_devis_current.loc[_idx, "Qté"]
                )
                st.session_state[f"{devis_lines_key}_ht_{_rid}"] = float(
                    df_devis_current.loc[_idx, "Prix HT (€)"]
                )

            # Callback générique : sync widget value → DataFrame
            def _on_devis_edit(rid: int, widget_suffix: str, df_field: str, caster):
                wkey = f"{devis_lines_key}_{widget_suffix}_{rid}"
                if wkey not in st.session_state:
                    return
                df_cur = st.session_state[devis_lines_key]
                mask = df_cur["_id"] == rid
                df_cur.loc[mask, df_field] = caster(st.session_state[wkey])
                st.session_state[devis_lines_key] = df_cur

            # Layout "Ajouter une ligne" : selectbox pièce + bouton
            col_add_piece, col_add_btn, _ = st.columns([2, 1, 2])
            with col_add_piece:
                add_target_piece = st.selectbox(
                    "Pour quelle pièce ?",
                    existing_pieces,
                    key=f"{devis_lines_key}_addpiece",
                    label_visibility="collapsed",
                )
            with col_add_btn:
                if st.button(
                    "➕ Ajouter une ligne", key=f"{devis_lines_key}_add",
                    help="Ajoute un équipement à la pièce sélectionnée. "
                         "La nouvelle ligne s'insère après le dernier équipement "
                         "de cette pièce.",
                ):
                    new_id = st.session_state[devis_lines_nid_key]
                    st.session_state[devis_lines_nid_key] += 1
                    first_eq = EQUIPMENT_LABELS_LIST[0]
                    first_eq_enum = LABEL_FR_TO_EQUIPMENT[first_eq]
                    new_row = pd.DataFrame([{
                        "_id": new_id, "Pièce": add_target_piece,
                        "Équipement": first_eq,
                        "Qté": 1,
                        "Prix HT (€)": float(DEFAULT_PRICES_HT[first_eq_enum]),
                        "_manual": True,
                        "_equip_ids": [],
                    }])
                    # Insertion intelligente : après la DERNIÈRE ligne de
                    # cette pièce dans le tableau
                    df_now = st.session_state[devis_lines_key]
                    matching = df_now[df_now["Pièce"] == add_target_piece]
                    if matching.empty:
                        new_df = pd.concat(
                            [df_now, new_row], ignore_index=True,
                        )
                    else:
                        last_pos = df_now.index.get_loc(matching.index[-1])
                        before = df_now.iloc[:last_pos + 1]
                        after = df_now.iloc[last_pos + 1:]
                        new_df = pd.concat(
                            [before, new_row, after], ignore_index=True,
                        )
                    st.session_state[devis_lines_key] = new_df
                    # Pré-init widget states pour la nouvelle ligne
                    st.session_state[f"{devis_lines_key}_piece_{new_id}"] = add_target_piece
                    st.session_state[f"{devis_lines_key}_eq_{new_id}"] = first_eq
                    st.session_state[f"{devis_lines_key}_qty_{new_id}"] = 1
                    st.session_state[f"{devis_lines_key}_ht_{new_id}"] = float(
                        DEFAULT_PRICES_HT[first_eq_enum]
                    )
                    st.rerun()

            df_devis = st.session_state[devis_lines_key]

            # === Groupement par pièce (préserve l'ordre d'apparition dans df) ===
            pieces_in_order: list[str] = []
            _seen: set[str] = set()
            for idx in df_devis.index:
                p = str(df_devis.loc[idx, "Pièce"])
                if p not in _seen:
                    pieces_in_order.append(p)
                    _seen.add(p)

            # State expanded/collapsed par pièce (default = tout déroulé)
            expanded_key = f"{devis_lines_key}_expanded"
            if expanded_key not in st.session_state:
                st.session_state[expanded_key] = {}
            # Ajoute les nouvelles pièces / supprime les obsolètes
            st.session_state[expanded_key] = {
                p: st.session_state[expanded_key].get(p, True)
                for p in pieces_in_order
            }

            # === Toggle global au-dessus du tableau ===
            # Pattern on_change : le callback ne fire QUE quand l'user clique
            # explicitement sur la checkbox. Les autres interactions (chevron
            # individuel, ajout/suppression de ligne, etc.) ne déclenchent PAS
            # le callback → pas d'override silencieux des états individuels.
            #
            # Le state de la checkbox est force-sync à l'état réel AVANT le
            # render : si toutes les pièces sont déroulées → cochée, sinon
            # décochée. Cohérence visuelle automatique.
            toggle_key = f"{devis_lines_key}_all_expand"
            all_expanded_now = (
                bool(pieces_in_order)
                and all(st.session_state[expanded_key].values())
            )
            st.session_state[toggle_key] = all_expanded_now

            # Callback fired uniquement sur click utilisateur sur la checkbox
            _pieces_for_cb = list(pieces_in_order)
            _exp_key_for_cb = expanded_key

            def _on_global_toggle():
                new_val = bool(st.session_state[toggle_key])
                for p in _pieces_for_cb:
                    st.session_state[_exp_key_for_cb][p] = new_val

            st.checkbox(
                "📂 Tout dérouler  /  📁 Tout enrouler",
                key=toggle_key,
                on_change=_on_global_toggle,
                help="Coche pour afficher tous les équipements de toutes les "
                     "pièces. Décoche pour ne voir que les noms de pièces "
                     "(plus lisible si beaucoup de pièces). Tu peux aussi "
                     "replier/déplier chaque pièce individuellement via le "
                     "chevron ▶/▼ devant son nom.",
            )

            # === Calcul totaux GLOBAUX (depuis DataFrame, inclut pièces collapsed) ===
            total_ht = 0.0
            total_ttc = 0.0
            for idx in df_devis.index:
                qty_i = int(df_devis.loc[idx, "Qté"])
                ht_i = float(df_devis.loc[idx, "Prix HT (€)"])
                ttc_i = compute_ttc(ht_i, devis_tva_rate)
                total_ht += qty_i * ht_i
                total_ttc += qty_i * ttc_i

            # === Headers (8 cols : Pièce, ✏️, Équipement, Qté, HT, TTC, Total, Suppr.) ===
            COL_PROPS_DEVIS = [2, 0.3, 3, 1, 1, 1, 1, 1]
            h = st.columns(COL_PROPS_DEVIS)
            h[0].markdown("**Pièce**")
            h[1].markdown("")  # colonne icône origine, sans header
            h[2].markdown("**Équipement**")
            h[3].markdown("**Qté**")
            h[4].markdown("**Prix HT €**")
            h[5].markdown("**Prix TTC €**")
            h[6].markdown("**Total TTC €**")
            h[7].markdown("**Suppr.**")
            st.divider()

            ids_to_delete: list[int] = []

            # === Rendering : un header par pièce + (conditionnellement) ses rows ===
            for piece_name in pieces_in_order:
                is_expanded = st.session_state[expanded_key].get(piece_name, True)
                piece_rows = df_devis[df_devis["Pièce"] == piece_name]
                n_equipts = len(piece_rows)

                # Sous-total TTC de la pièce
                piece_total_ttc = 0.0
                for idx in piece_rows.index:
                    qty_i = int(piece_rows.loc[idx, "Qté"])
                    ht_i = float(piece_rows.loc[idx, "Prix HT (€)"])
                    piece_total_ttc += qty_i * compute_ttc(ht_i, devis_tva_rate)

                # --- Row "header pièce" (chevron bouton tertiary + nom texte) ---
                hcols = st.columns(COL_PROPS_DEVIS)
                chevron = "▼" if is_expanded else "▶"
                with hcols[0]:
                    # Sous-colonnes : chevron (bouton sans bordure) + nom (texte)
                    btn_col, name_col = st.columns([1, 4])
                    with btn_col:
                        if st.button(
                            chevron,
                            key=f"toggle_{devis_lines_key}_{piece_name}",
                            type="tertiary",  # pas de bordure ni fond
                            help=("Replier" if is_expanded else "Déplier")
                                 + f" les {n_equipts} équipement(s)",
                        ):
                            st.session_state[expanded_key][piece_name] = not is_expanded
                            st.rerun()
                    with name_col:
                        st.markdown(
                            f"<div style='padding-top: 0.5rem;'>"
                            f"<b>{piece_name}</b></div>",
                            unsafe_allow_html=True,
                        )
                with hcols[2]:
                    plural = "s" if n_equipts > 1 else ""
                    st.markdown(
                        f"<div style='padding-top: 0.5rem; color: #666;'>"
                        f"<em>{n_equipts} équipement{plural}</em></div>",
                        unsafe_allow_html=True,
                    )

                # --- Rows équipement (uniquement si pièce déroulée) ---
                if not is_expanded:
                    continue

                for idx in piece_rows.index:
                    row = piece_rows.loc[idx]
                    rid = int(row["_id"])
                    is_manual = bool(row.get("_manual", False))
                    cols = st.columns(COL_PROPS_DEVIS)
                    # Widgets avec on_change → DataFrame est sync instantanément
                    with cols[0]:
                        st.selectbox(
                            "Pièce", existing_pieces,
                            key=f"{devis_lines_key}_piece_{rid}",
                            on_change=_on_devis_edit,
                            args=(rid, "piece", "Pièce", str),
                            label_visibility="collapsed",
                        )
                    with cols[1]:
                        if is_manual:
                            st.markdown(
                                "<div style='padding-top: 0.5rem; "
                                "text-align: center; color: #888;' "
                                "title='Ajouté manuellement'>✏️</div>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown("")
                    with cols[2]:
                        st.selectbox(
                            "Équipement", EQUIPMENT_LABELS_LIST,
                            key=f"{devis_lines_key}_eq_{rid}",
                            on_change=_on_devis_edit,
                            args=(rid, "eq", "Équipement", str),
                            label_visibility="collapsed",
                        )
                    with cols[3]:
                        st.number_input(
                            "Qté", min_value=0, max_value=99, step=1,
                            key=f"{devis_lines_key}_qty_{rid}",
                            on_change=_on_devis_edit,
                            args=(rid, "qty", "Qté", int),
                            label_visibility="collapsed",
                        )
                    with cols[4]:
                        st.number_input(
                            "HT", min_value=0.0, max_value=10000.0, step=1.0,
                            format="%.2f",
                            key=f"{devis_lines_key}_ht_{rid}",
                            on_change=_on_devis_edit,
                            args=(rid, "ht", "Prix HT (€)", float),
                            label_visibility="collapsed",
                        )
                    # Lecture depuis le DataFrame (sync via on_change) — évite
                    # de dépendre de la valeur de retour des widgets, qui peut
                    # être désynchronisée transitoirement après un toggle.
                    qty_disp = int(df_devis.loc[idx, "Qté"])
                    ht_disp = float(df_devis.loc[idx, "Prix HT (€)"])
                    prix_ttc = compute_ttc(ht_disp, devis_tva_rate)
                    total_line_ttc = qty_disp * prix_ttc
                    with cols[5]:
                        st.markdown(
                            f"<div style='padding-top: 0.5rem;'>{prix_ttc:.2f}</div>",
                            unsafe_allow_html=True,
                        )
                    with cols[6]:
                        st.markdown(
                            f"<div style='padding-top: 0.5rem;'>"
                            f"<b>{total_line_ttc:.2f}</b></div>",
                            unsafe_allow_html=True,
                        )
                    with cols[7]:
                        if st.button(
                            "🗑️", key=f"{devis_lines_key}_del_{rid}",
                            help="Supprimer cette ligne du devis",
                        ):
                            ids_to_delete.append(rid)

                # --- Sous-total pièce, aligné dans la col Total TTC ---
                # Affiché APRÈS les équipements (donc visible uniquement quand
                # la pièce est déroulée). Alignement = même colonne que les
                # Total TTC des lignes (col 6) → s'aligne verticalement avec
                # les valeurs 180.00, 60.00, etc.
                stcols = st.columns(COL_PROPS_DEVIS)
                with stcols[6]:
                    st.markdown(
                        f"<div style='padding-top: 0.3rem; padding-bottom: 0.3rem; "
                        f"color: #1f3a5f;'>"
                        f"<b>{piece_total_ttc:.2f} €</b></div>",
                        unsafe_allow_html=True,
                    )

            # Process deletions
            if ids_to_delete:
                new_df = df_devis[~df_devis["_id"].isin(ids_to_delete)].reset_index(drop=True)
                st.session_state[devis_lines_key] = new_df
                for rid in ids_to_delete:
                    for prefix in ("piece", "eq", "qty", "ht", "del"):
                        k = f"{devis_lines_key}_{prefix}_{rid}"
                        if k in st.session_state:
                            del st.session_state[k]
                st.rerun()

            # Caption explicative pour l'icône ✏️
            n_manual = int(df_devis["_manual"].sum()) if "_manual" in df_devis.columns else 0
            if n_manual > 0:
                st.caption(
                    f"✏️ = ligne ajoutée manuellement ({n_manual} ligne(s)). "
                    "Ces lignes sont **préservées** lors de la regénération du devis."
                )

            # Totaux globaux
            st.divider()
            col_t1, col_t2, col_t3 = st.columns([2, 1, 1])
            with col_t1:
                st.markdown("### 💰 Totaux devis")
                st.caption(f"TVA appliquée : **{devis_tva_label}**")
            with col_t2:
                st.metric("Total HT", f"{total_ht:.2f} €")
            with col_t3:
                st.metric("Total TTC", f"{total_ttc:.2f} €",
                          delta=f"{total_ttc - total_ht:.2f} € TVA")

            # Export CSV — reconstruit depuis les widget states (à jour)
            import io, csv
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf, delimiter=";")
            writer.writerow([
                "Pièce", "Équipement", "Qté",
                "Prix HT (€)", "Prix TTC (€)", "Total TTC (€)",
            ])
            csv_total_ht = 0.0
            csv_total_ttc = 0.0
            for idx in df_devis.index:
                rid = int(df_devis.loc[idx, "_id"])
                piece = st.session_state.get(
                    f"{devis_lines_key}_piece_{rid}",
                    str(df_devis.loc[idx, "Pièce"]),
                )
                eq = st.session_state.get(
                    f"{devis_lines_key}_eq_{rid}",
                    str(df_devis.loc[idx, "Équipement"]),
                )
                q = int(st.session_state.get(
                    f"{devis_lines_key}_qty_{rid}",
                    int(df_devis.loc[idx, "Qté"]),
                ))
                ht = float(st.session_state.get(
                    f"{devis_lines_key}_ht_{rid}",
                    float(df_devis.loc[idx, "Prix HT (€)"]),
                ))
                ttc = compute_ttc(ht, devis_tva_rate)
                line_ttc = q * ttc
                writer.writerow([
                    piece, eq, q,
                    f"{ht:.2f}", f"{ttc:.2f}", f"{line_ttc:.2f}",
                ])
                csv_total_ht += q * ht
                csv_total_ttc += line_ttc
            writer.writerow([])
            writer.writerow([
                "TOTAL", "", "", f"{csv_total_ht:.2f}",
                "", f"{csv_total_ttc:.2f}",
            ])

            csv_plan_id = result.plan_id if result else uploaded.name
            st.download_button(
                label="📥 Télécharger devis CSV",
                data=csv_buf.getvalue(),
                file_name=f"devis_{csv_plan_id}.csv",
                mime="text/csv",
            )

    # --- Debug: ALL raw OCR hits (before any filtering) ---
    if ocr_hits_raw:
        n_total = len(ocr_hits_raw)
        n_kept = len(ocr_hits)
        n_filtered = n_total - n_kept
        with st.expander(
            f"🔍 Debug OCR brut — {n_total} détections totales "
            f"({n_kept} retenues / {n_filtered} filtrées)"
        ):
            st.caption(
                "Toutes les détections de PaddleOCR (3-pass : normal + 90°CW "
                "+ 90°CCW) avant filtrage métier. Si un label visible sur le "
                "plan n'apparaît PAS ici, c'est que l'OCR n'a pas réussi à le "
                "lire (essaie de désactiver le preprocessing). Sinon, ajuste "
                "le seuil de confidence."
            )
            # Sort by confidence DESC for easier scan
            sorted_raw = sorted(ocr_hits_raw, key=lambda h: -h.get("confidence", 0))
            st.dataframe(
                [{"Texte brut": h.get("text", ""),
                  "Confiance": f"{h.get('confidence', 0):.2f}",
                  "Sous seuil ?": "❌" if h.get("confidence", 0) < ocr_confidence_min else "✅"}
                 for h in sorted_raw],
                use_container_width=True, hide_index=True,
                height=min(400, 35 * (len(sorted_raw) + 1)),
            )

    # Cleanup tmp
    try:
        os.unlink(tmp_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
