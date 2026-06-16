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

from src.planrec.nfc_rules import (
    EquipmentType,
    DevisGlobal,
    SPECIAL_FEED_EQUIPMENT_TYPES,
)


class EquipmentInstance(TypedDict):
    """Une unité physique d'équipement placée sur le plan."""
    id: str        # "eq_<8 hex>"
    type: str      # clé EQUIP_TYPES
    room: str      # nom pièce devis (ex "Cuisine", "Chambre 2")
    x: int         # px image originale
    y: int
    color: str     # CSS color
    uncertain: bool  # placement auto à re-vérifier (halo orange)


# Mapping label devis (FR) + couleur (CSS) + svg_id (pour le composant React)
EQUIP_TYPES: dict[str, dict[str, str]] = {
    # Anciens types (préservés)
    "Prise":          {"label": "Prise courant",  "color": "rgb(255, 112, 67)", "svg_id": "socket"},
    "RJ45":           {"label": "Prise RJ45",     "color": "rgb(38, 166, 154)", "svg_id": "rj45"},
    "LightPoint":     {"label": "Point lumineux", "color": "rgb(251, 192, 45)", "svg_id": "light"},
    "Switch":         {"label": "Interrupteur",   "color": "rgb(66, 165, 245)", "svg_id": "switch"},
    "SpecialFeed":    {"label": "Alim spé",       "color": "rgb(171, 71, 188)", "svg_id": "specfeed"},
    # NEW V1.2 — circuits spécialisés typés (violet cuisine, orange buanderie, rouge cumulus)
    "Oven":           {"label": "Four",           "color": "rgb(171, 71, 188)", "svg_id": "oven"},
    "Cooktop":        {"label": "Plaque cuisson", "color": "rgb(123, 31, 162)", "svg_id": "cooktop"},
    "Dishwasher":     {"label": "Lave-vaisselle", "color": "rgb(194, 24, 91)",  "svg_id": "dishwasher"},
    "WashingMachine": {"label": "Lave-linge",     "color": "rgb(255, 112, 67)", "svg_id": "washingmachine"},
    "Dryer":          {"label": "Sèche-linge",    "color": "rgb(255, 167, 38)", "svg_id": "dryer"},
    "Boiler":         {"label": "Chaudière",      "color": "rgb(198, 40, 40)",  "svg_id": "boiler"},
    # NEW V1.2 — chauffage (rouge clair)
    "Convector":      {"label": "Convecteur",     "color": "rgb(239, 83, 80)",  "svg_id": "convector"},
    "TowelWarmer":    {"label": "Sèche-serv.",    "color": "rgb(239, 154, 154)", "svg_id": "towelwarmer"},
}


# Mapping de l'enum NFC vers la clé EQUIP_TYPES (string)
NFC_TO_EQUIP_TYPE: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise",
    EquipmentType.RJ45: "RJ45",
    EquipmentType.LIGHT_POINT: "LightPoint",
    EquipmentType.SWITCH: "Switch",
    EquipmentType.SPECIAL_FEED: "SpecialFeed",
    # NEW V1.2
    EquipmentType.OVEN: "Oven",
    EquipmentType.COOKTOP: "Cooktop",
    EquipmentType.DISHWASHER: "Dishwasher",
    EquipmentType.WASHING_MACHINE: "WashingMachine",
    EquipmentType.DRYER: "Dryer",
    EquipmentType.BOILER: "Boiler",
    EquipmentType.CONVECTOR: "Convector",
    EquipmentType.TOWEL_WARMER: "TowelWarmer",
}


# Clés masquées de la PALETTE manuelle (drag-drop) : les 6 appareils, qui sont
# représentés par la pastille générique « Alim spé » (SpecialFeed), pas par des
# boutons typés. Convecteur/Sèche-serviettes en sont sortis → disponibles en
# palette et générés avec leur pastille propre. Cf. retour métier 2026-06-16.
CANVAS_HIDDEN_EQUIP_KEYS: frozenset[str] = frozenset({
    "Oven", "Cooktop", "Dishwasher", "WashingMachine", "Dryer", "Boiler",
})


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
    # Pièce synthétique « lave-linge virtuel » : circuit-only sans polygone
    # → jamais de pastille sur le plan (le circuit LAUNDRY reste dans le
    # tableau électrique). Cf. _ensure_washing_machine dans nfc_rules.py.
    placeable_rooms = [
        r for r in devis_global.per_room if r.room_id != "__laundry_virtual__"
    ]

    # Compte les pièces par catégorie pour l'auto-indice
    cat_total: dict[str, int] = {}
    for room_devis in placeable_rooms:
        cat = room_devis.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    cat_seen: dict[str, int] = {}

    instances: list[EquipmentInstance] = []
    for room_devis in placeable_rooms:
        cat = room_devis.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = (
            f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat
        )
        for nfc_type, qty in room_devis.items.items():
            if qty <= 0:
                continue
            # Les 6 appareils à alim dédiée → pastille générique « Alim spé ».
            # Le reste (dont Convecteur/Sèche-serviettes) → sa pastille propre.
            if nfc_type in SPECIAL_FEED_EQUIPMENT_TYPES:
                equip_key = "SpecialFeed"
            else:
                equip_key = NFC_TO_EQUIP_TYPE[nfc_type]
                if equip_key in CANVAS_HIDDEN_EQUIP_KEYS:
                    continue
            color = EQUIP_TYPES[equip_key]["color"]
            for _ in range(qty):
                instances.append({
                    "id": generate_equipment_id(),
                    "type": equip_key,
                    "room": room_label,
                    "x": 0,
                    "y": 0,
                    "color": color,
                    "uncertain": False,
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


def _polygon_centroid(polygon: list[tuple[int, int]]) -> tuple[int, int]:
    """Barycentre simple (moyenne des sommets) — suffisant pour nos polygones convexes."""
    n = len(polygon)
    cx = sum(p[0] for p in polygon) // n
    cy = sum(p[1] for p in polygon) // n
    return (cx, cy)


def _point_on_perimeter_offset_inward(
    polygon: list[tuple[int, int]],
    t: float,
    offset_px: int = 15,
) -> tuple[int, int]:
    """Point à la position t (0..1) sur le périmètre, décalé `offset_px` vers
    l'intérieur (vers le barycentre).

    t = 0   → premier sommet
    t = 0.5 → milieu du polygone
    t = 1   → revient au premier sommet (boucle)
    """
    segs = []
    total_len = 0.0
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((a, b, seg_len))
        total_len += seg_len
    target = (t % 1.0) * total_len
    px = py = 0.0
    cumul = 0.0
    for a, b, seg_len in segs:
        if cumul + seg_len >= target:
            ratio = (target - cumul) / seg_len if seg_len > 0 else 0.0
            px = a[0] + (b[0] - a[0]) * ratio
            py = a[1] + (b[1] - a[1]) * ratio
            break
        cumul += seg_len
    cx, cy = _polygon_centroid(polygon)
    vx = cx - px
    vy = cy - py
    v_len = math.hypot(vx, vy)
    if v_len > 0:
        px += (vx / v_len) * offset_px
        py += (vy / v_len) * offset_px
    return (int(px), int(py))


def smart_placement_with_polygon(
    equip_type: str,
    polygon: list[tuple[int, int]],
    room_pastille_pos: tuple[int, int],
    instance_index: int,
    n_of_type: int,
) -> tuple[int, int]:
    """Placement intelligent basé sur le polygone de la pièce (segmentation).

    - LightPoint : barycentre du polygone
    - Switch : sur périmètre, position la plus proche de room_pastille_pos
    - Prise : distribuée uniformément sur le périmètre
    - RJ45 : sur le périmètre, à côté de la 1ère prise (t=0.05)
    - SpecialFeed : sur le périmètre, à l'opposé de l'interrupteur (t=0.55)
    """
    if equip_type == "LightPoint":
        return _polygon_centroid(polygon)

    if equip_type == "Switch":
        best = None
        best_dist = float("inf")
        for i in range(60):
            t = i / 60.0
            p = _point_on_perimeter_offset_inward(polygon, t)
            d = math.hypot(
                p[0] - room_pastille_pos[0],
                p[1] - room_pastille_pos[1],
            )
            if d < best_dist:
                best_dist = d
                best = p
        return best if best else _polygon_centroid(polygon)

    if equip_type == "Prise":
        t = (instance_index + 0.5) / max(1, n_of_type)
        return _point_on_perimeter_offset_inward(polygon, t)

    if equip_type == "RJ45":
        return _point_on_perimeter_offset_inward(polygon, 0.05)

    if equip_type == "SpecialFeed":
        return _point_on_perimeter_offset_inward(polygon, 0.55)

    return _polygon_centroid(polygon)


def reconcile_equipments_for_line(
    current_state: list[EquipmentInstance],
    line_room: str,
    line_type: str,
    new_qty: int,
    smart_placer: Callable[[str, str, int, int], tuple[int, int]],
) -> tuple[list[EquipmentInstance], list[str]]:
    """Synchronise les instances pour UNE ligne devis (pièce × type) après
    changement de Qté.

    smart_placer(equip_type, room, instance_index, n_of_type) → (x, y)

    Returns:
        (new_state, line_ids) où line_ids = liste des UUIDs pour cette ligne
        après reconciliation (à écrire dans la colonne _equip_ids du DataFrame).
    """
    line_existing = [
        i for i in current_state
        if i["room"] == line_room and i["type"] == line_type
    ]
    others = [
        i for i in current_state
        if not (i["room"] == line_room and i["type"] == line_type)
    ]

    if new_qty >= len(line_existing):
        keep = list(line_existing)
        n_to_add = new_qty - len(line_existing)
        color = EQUIP_TYPES[line_type]["color"]
        for i in range(n_to_add):
            # idx_in_type = rang de l'instance dans son type = nb d'instances
            # DÉJÀ existantes avant cette boucle + i. NB : ne pas utiliser
            # len(keep), qui grossit à chaque append → on sauterait un index sur
            # deux (0,2,4…) et une position du moteur ne serait jamais demandée.
            idx_in_type = len(line_existing) + i
            x, y = smart_placer(line_type, line_room, idx_in_type, new_qty)
            keep.append({
                "id": generate_equipment_id(),
                "type": line_type,
                "room": line_room,
                "x": x,
                "y": y,
                "color": color,
                "uncertain": False,
            })
    else:
        keep = line_existing[:new_qty]

    new_state = others + keep
    line_ids = [i["id"] for i in keep]
    return (new_state, line_ids)
