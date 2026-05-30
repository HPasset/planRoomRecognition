"""Logique métier des équipements électriques individuels (instances).

Ce module est PUR : aucun import Streamlit/React. Testable en pytest seul.

Une instance équipement = une unité physique sur le plan (1 prise = 1 instance,
même si la ligne devis a Qté=6 → 6 instances). Les positions (x, y) sont en
coordonnées image originale (px).
"""
from __future__ import annotations
import math
import random
import secrets
from typing import Callable, TypedDict

from src.planrec.nfc_rules import EquipmentType, DevisGlobal


class EquipmentInstance(TypedDict):
    """Une unité physique d'équipement placée sur le plan."""
    id: str        # "eq_<8 hex>"
    type: str      # clé EQUIP_TYPES
    room: str      # nom pièce devis (ex "Cuisine", "Chambre 2")
    x: int         # px image originale
    y: int
    color: str     # CSS color


# Mapping label devis (FR) + couleur (CSS) + svg_id (pour le composant React)
EQUIP_TYPES: dict[str, dict[str, str]] = {
    "Prise":       {"label": "Prise courant",  "color": "rgb(255, 112, 67)", "svg_id": "socket"},
    "RJ45":        {"label": "Prise RJ45",     "color": "rgb(38, 166, 154)", "svg_id": "rj45"},
    "LightPoint":  {"label": "Point lumineux", "color": "rgb(251, 192, 45)", "svg_id": "light"},
    "Switch":      {"label": "Interrupteur",   "color": "rgb(66, 165, 245)", "svg_id": "switch"},
    "SpecialFeed": {"label": "Alim spé",       "color": "rgb(171, 71, 188)", "svg_id": "specfeed"},
}


# Mapping de l'enum NFC vers la clé EQUIP_TYPES (string)
NFC_TO_EQUIP_TYPE: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise",
    EquipmentType.RJ45: "RJ45",
    EquipmentType.LIGHT_POINT: "LightPoint",
    EquipmentType.SWITCH: "Switch",
    EquipmentType.SPECIAL_FEED: "SpecialFeed",
}


def generate_equipment_id() -> str:
    """Génère un ID unique 'eq_<8 hex>' (~4 milliards de valeurs distinctes)."""
    return f"eq_{secrets.token_hex(4)}"


def generate_equipments_from_devis_global(
    devis_global: DevisGlobal,
) -> list[EquipmentInstance]:
    """Pour chaque ligne (pièce × type) du devis, génère Qté instances.

    Le room label utilise l'auto-indice (Chambre 1, Chambre 2…) SI plusieurs
    pièces de la même catégorie NFC sont présentes — même logique que
    `build_devis_lines_initial` côté streamlit_app.py.

    Positions initiales : x=0, y=0 (le caller utilise smart_placement pour
    les remplir avant rendu).
    """
    # Compte les pièces par catégorie pour l'auto-indice
    cat_total: dict[str, int] = {}
    for room_devis in devis_global.per_room:
        cat = room_devis.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    cat_seen: dict[str, int] = {}

    instances: list[EquipmentInstance] = []
    for room_devis in devis_global.per_room:
        cat = room_devis.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = (
            f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat
        )
        for nfc_type, qty in room_devis.items.items():
            equip_key = NFC_TO_EQUIP_TYPE[nfc_type]
            color = EQUIP_TYPES[equip_key]["color"]
            for _ in range(qty):
                instances.append({
                    "id": generate_equipment_id(),
                    "type": equip_key,
                    "room": room_label,
                    "x": 0,
                    "y": 0,
                    "color": color,
                })
    return instances


def smart_placement_fallback_cluster(
    room_center: tuple[int, int],
    n_equipments: int,
    image_size: tuple[int, int],
    spacing: int = 30,
    drift: int = 5,
    random_seed: int | None = None,
) -> list[tuple[int, int]]:
    """Placement fallback en grille compacte autour de room_center.

    Utilisé quand la segmentation Mask2Former n'est pas active (pas de
    polygone disponible pour la pièce). Grille carrée centrée sur
    room_center, espacement `spacing`, drift aléatoire ±`drift` par
    instance. Positions clampées dans la bbox image.
    """
    rng = random.Random(random_seed)
    image_w, image_h = image_size
    cx, cy = room_center
    grid_side = max(1, math.ceil(math.sqrt(n_equipments)))
    positions: list[tuple[int, int]] = []
    for i in range(n_equipments):
        col = i % grid_side
        row = i // grid_side
        ox = (col - (grid_side - 1) / 2) * spacing
        oy = (row - (grid_side - 1) / 2) * spacing
        dx = rng.randint(-drift, drift)
        dy = rng.randint(-drift, drift)
        x = max(0, min(image_w, int(cx + ox + dx)))
        y = max(0, min(image_h, int(cy + oy + dy)))
        positions.append((x, y))
    return positions
