"""Pont entre le moteur de placement (holistique, par pièce) et le callback
per-instance `smart_placer(equip_type, room, idx, n_of_type)` de Streamlit.

`build_room_layout_index` appelle le résolveur une fois par pièce et range les
résultats par (room_label, equip_key, index_dans_le_type) pour lookup O(1).
"""
from __future__ import annotations

from src.planrec.placement.contracts import RoomContext, PlacedEquipment
from src.planrec.placement.resolver import place_room
from src.planrec.placement.spec import SPEC_BY_ROOM_TYPE

LayoutIndex = dict[tuple[str, str, int], PlacedEquipment]


def build_room_layout_index(
    room_label: str, ctx: RoomContext, counts: dict[str, int],
) -> LayoutIndex:
    """Layout holistique d'une pièce → index (room, type, idx) → PlacedEquipment.

    Retourne {} si le type de pièce n'a pas de spec (→ caller garde l'ancien
    placement).
    """
    if ctx.room_type not in SPEC_BY_ROOM_TYPE:
        return {}
    placed = place_room(ctx, counts)
    index: LayoutIndex = {}
    per_type_count: dict[str, int] = {}
    for pe in placed:
        idx = per_type_count.get(pe.equip_key, 0)
        index[(room_label, pe.equip_key, idx)] = pe
        per_type_count[pe.equip_key] = idx + 1
    return index
