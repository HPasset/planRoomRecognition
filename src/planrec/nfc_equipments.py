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
