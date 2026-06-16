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


def _ll_rooms(devis_global):
    """(room_id, nfc_category) des pièces portant un lave-linge."""
    return [
        (d.room_id, d.nfc_category)
        for d in devis_global.per_room
        if d.items.get(EquipmentType.WASHING_MACHINE, 0) >= 1
    ]


def test_lave_linge_cellier_pas_de_doublon():
    dg = compute_devis_global([
        {"id": "C1", "c2_class": "Storage"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "K1", "c2_class": "Kitchen"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "C1"  # rattaché au cellier existant


def test_lave_linge_repli_sur_sdb_si_pas_de_cellier():
    dg = compute_devis_global([
        {"id": "S1", "c2_class": "Bath"},
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0] == ("S1", NFCCategory.BATH)


def test_lave_linge_priorite_sdb_avant_cuisine():
    dg = compute_devis_global([
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "S1"  # SDB prioritaire sur cuisine


def test_lave_linge_circuit_only_si_aucune_piece_candidate():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "__laundry_virtual__"
    assert ll[0][1] == NFCCategory.STORAGE


def test_lave_linge_label_20A_sur_repli():
    dg = compute_devis_global([
        {"id": "S1", "c2_class": "Bath"},
    ])
    sdb = next(d for d in dg.per_room if d.room_id == "S1")
    assert "Lave-linge (20A)" in sdb.special_feeds_detail


def test_cellier_lave_linge_label_20A():
    dg = compute_devis_global([
        {"id": "C1", "c2_class": "Storage"},
    ])
    cellier = next(d for d in dg.per_room if d.room_id == "C1")
    assert "Lave-linge (20A)" in cellier.special_feeds_detail
    assert "Lave-linge (16A)" not in cellier.special_feeds_detail


def test_tableau_force_rcd_type_a_sans_cellier():
    """Logement sans cellier mais avec SDB → le lave-linge garanti crée un
    circuit LAUNDRY qui force un DDR Type A dans le tableau."""
    from src.planrec.nfc_tableau import generate_tableau

    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "S1", "c2_class": "Bath"},
    ])
    tableau = generate_tableau(devis_global=dg, heating_enabled=True)
    assert any(rcd.rcd_type == "A" for rcd in tableau.rcds)
