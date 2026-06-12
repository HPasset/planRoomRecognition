"""Custom Streamlit component : drag-and-drop pastilles sur le plan.

Phase 1 (actuelle) :
- Affiche le plan (image) avec pastilles colorées pré-placées (positions OCR).
- Palette à droite avec les types de pièces disponibles.
- Pas encore de drag (Phase 2).

Phase 2 (à venir) :
- Drag des pastilles existantes pour les repositionner.
- Sortir une pastille du cadre image → suppression.

Phase 3 (à venir) :
- Drag depuis la palette → ajout d'une nouvelle pastille.

Usage::

    from app.components.pastille_canvas import pastille_canvas

    result = pastille_canvas(
        image_bytes=img_bgr_encoded,
        image_width=W,
        image_height=H,
        initial_pastilles=[
            {"id": "ocr_001", "type": "Cuisine", "label": "Cuisine",
             "x": 150, "y": 200, "color": "rgb(255,200,100)"},
            ...
        ],
        palette=[
            {"type": "Cuisine", "label": "Cuisine", "color": "rgb(255,200,100)"},
            ...
        ],
        key="my_canvas",
    )
    # result = {"pastilles": [...]} — état courant après interactions user
"""
from __future__ import annotations
import base64
from pathlib import Path

import streamlit.components.v1 as components


_FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

# Declare component pointing to built frontend assets.
_component_func = components.declare_component(
    "pastille_canvas",
    path=str(_FRONTEND_DIR),
)


def pastille_canvas(
    image_bytes: bytes,
    image_width: int,
    image_height: int,
    initial_pastilles: list[dict],
    palette: list[dict],
    seg_polygons: list[dict] | None = None,
    yolo_boxes: list[dict] | None = None,
    equipments: list[dict] | None = None,
    equip_palette: list[dict] | None = None,
    equip_visible_types: list[str] | None = None,
    pastille_to_devis_room: dict[str, str] | None = None,
    wall_lines: list | None = None,
    key: str | None = None,
) -> dict | None:
    """Render le canvas pastilles + palette.

    Args:
        image_bytes: bytes encodés (PNG ou JPEG) du plan
        image_width: largeur originale image en px (pour mapping coord)
        image_height: hauteur originale image en px
        initial_pastilles: liste de dicts {id, type, label, x, y, color}
            où x/y sont en coordonnées image originale
        palette: liste de dicts {type, label, color} pour les types dispo
        seg_polygons: optionnel, liste de dicts {type_name, points, fill,
            stroke} où points = [[x,y], ...] en coord image originale.
            Dessinés en overlay SVG sous les pastilles (non interactifs).
        yolo_boxes: optionnel, liste de dicts {class_name, x1, y1, x2, y2,
            confidence, color} en coord image originale. Dessinés en overlay
            SVG (rectangles + labels) au-dessus des polygones segmentation
            mais SOUS les pastilles. Non interactifs. Purement visuel.
        equipments: optionnel, liste de dicts {id, type, room, x, y, color,
            uncertain} où x/y sont en coordonnées image originale. `uncertain`
            (bool) → halo orange « à vérifier » autour de l'icône. Instances
            équipements individuelles affichées sur le plan (1 prise = 1 instance).
        equip_palette: optionnel, liste de dicts {type, label, color, svg_id}
            décrivant les types d'équipements disponibles dans la palette
            sous le canvas.
        wall_lines: optionnel, liste de [x1, y1, x2, y2] (ou tuples) en
            coordonnées image originale. Dessinés en overlay SVG comme segments
            magenta (stroke rgba(217,70,239,0.9)) non interactifs, sous les
            pastilles. Typiquement issu de extract_wall_lines(wall_mask).
        key: clé Streamlit unique pour le component

    Returns:
        dict avec clé 'pastilles' : list[dict] mise à jour après interactions,
        ou None si le component n'a pas encore notifié de changement.
    """
    # Encode image en data URL base64 pour transit JSON → iframe
    # Détection du type MIME (PNG vs JPEG) via les magic bytes
    if image_bytes[:8].startswith(b"\x89PNG"):
        mime = "image/png"
    elif image_bytes[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    else:
        # Fallback PNG (sans garantie)
        mime = "image/png"
    image_data_url = (
        f"data:{mime};base64,"
        + base64.b64encode(image_bytes).decode("ascii")
    )

    return _component_func(
        image_data=image_data_url,
        image_width=int(image_width),
        image_height=int(image_height),
        initial_pastilles=initial_pastilles,
        palette=palette,
        seg_polygons=seg_polygons or [],
        yolo_boxes=yolo_boxes or [],
        equipments=equipments or [],
        equip_palette=equip_palette or [],
        equip_visible_types=equip_visible_types,
        pastille_to_devis_room=pastille_to_devis_room or {},
        wall_lines=[list(seg) for seg in (wall_lines or [])],
        key=key,
        default=None,
    )
