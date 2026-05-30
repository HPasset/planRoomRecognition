"""Tests pour le module nfc_equipments (logique métier équipements électriques)."""
from __future__ import annotations
import re
import pytest

from src.planrec.nfc_equipments import (
    EQUIP_TYPES,
    NFC_TO_EQUIP_TYPE,
    generate_equipment_id,
    generate_equipments_from_devis_global,
)
from src.planrec.nfc_rules import EquipmentType, compute_devis_global


def test_equip_types_has_5_entries():
    """Les 5 types NF C 15-100 doivent être présents avec label/color/svg_id."""
    expected_keys = {"Prise", "RJ45", "LightPoint", "Switch", "SpecialFeed"}
    assert set(EQUIP_TYPES.keys()) == expected_keys
    for key, info in EQUIP_TYPES.items():
        assert "label" in info
        assert "color" in info and info["color"].startswith("rgb(")
        assert "svg_id" in info


def test_nfc_to_equip_type_covers_all_enums():
    """Le mapping doit couvrir les 5 valeurs de EquipmentType."""
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SOCKET] == "Prise"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.RJ45] == "RJ45"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.LIGHT_POINT] == "LightPoint"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SWITCH] == "Switch"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SPECIAL_FEED] == "SpecialFeed"
    # Tous les enums sont mappés
    assert len(NFC_TO_EQUIP_TYPE) == 5


def test_generate_equipment_id_format():
    """ID = 'eq_' + 8 hex chars."""
    eid = generate_equipment_id()
    assert re.fullmatch(r"eq_[0-9a-f]{8}", eid)


def test_generate_equipment_id_unique():
    """100 appels successifs → 100 IDs distincts (proba collision négligeable)."""
    ids = {generate_equipment_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_equipments_from_devis_simple():
    """1 WC seul → 2 instances (1 LightPoint + 1 Switch selon NFC sans handicap)."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Bath", "surface_m2": None,
         "ocr_hint": "WC"},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    # WC NFC : 1 point lumineux + 1 interrupteur (pas de prise sans handicap)
    types = sorted(i["type"] for i in instances)
    assert types == ["LightPoint", "Switch"]
    # Chaque instance a un id unique, room "WC", x=y=0 par défaut
    assert len({i["id"] for i in instances}) == 2
    assert all(i["room"] == "WC" for i in instances)
    assert all(i["x"] == 0 and i["y"] == 0 for i in instances)
    assert all(i["color"] == EQUIP_TYPES[i["type"]]["color"] for i in instances)


def test_generate_equipments_kitchen_qty_explodes():
    """Cuisine NFC : qté élevée (6 prises + 3 alim spé + ...) → autant d'instances."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Kitchen", "surface_m2": None,
         "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    type_counts: dict[str, int] = {}
    for inst in instances:
        type_counts[inst["type"]] = type_counts.get(inst["type"], 0) + 1
    # Au moins 6 prises (NFC cuisine) + 3 alim spé + 1 point lum + 1 inter
    assert type_counts.get("Prise", 0) >= 6
    assert type_counts.get("SpecialFeed", 0) >= 3
    assert type_counts.get("LightPoint", 0) >= 1
    assert type_counts.get("Switch", 0) >= 1


def test_generate_equipments_room_label_with_index():
    """Plusieurs chambres → label = 'Chambre 1', 'Chambre 2'…"""
    rooms_input = [
        {"id": "r1", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
        {"id": "r2", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    rooms_in_instances = {i["room"] for i in instances}
    assert rooms_in_instances == {"Chambre 1", "Chambre 2"}
