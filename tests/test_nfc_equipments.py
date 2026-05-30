"""Tests pour le module nfc_equipments (logique métier équipements électriques)."""
from __future__ import annotations
import re
import pytest

from src.planrec.nfc_equipments import (
    EQUIP_TYPES,
    NFC_TO_EQUIP_TYPE,
    generate_equipment_id,
)
from src.planrec.nfc_rules import EquipmentType


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
