from __future__ import annotations

from src.planrec.nfc_rules import (
    EquipmentType,
    NFCCategory,
    compute_devis_global,
)


def _conv(devis_global, room_id):
    """Nb de convecteurs d'une pièce donnée du DevisGlobal."""
    for d in devis_global.per_room:
        if d.room_id == room_id:
            return d.items.get(EquipmentType.CONVECTOR, 0)
    raise AssertionError(f"room {room_id} absente")


def test_convecteur_sejour_surface_45_donne_3():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 45.0},
    ])
    assert _conv(dg, "L1") == 3


def test_convecteur_chambre_11m2_donne_1():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom", "surface_m2": 11.0},
    ])
    assert _conv(dg, "B1") == 1


def test_convecteur_sejour_sans_surface_forfait_2():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom"},
    ])
    assert _conv(dg, "L1") == 2


def test_convecteur_chambre_sans_surface_forfait_1():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    assert _conv(dg, "B1") == 1


def test_convecteur_chauffage_desactive_zero():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 45.0},
    ], heating_enabled=False)
    assert _conv(dg, "L1") == 0
