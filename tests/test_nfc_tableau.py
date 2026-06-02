"""Tests pour le module nfc_tableau (algo greedy de répartition tableau électrique)."""
from __future__ import annotations
import pytest

from src.planrec.nfc_tableau import CircuitType, Circuit


def test_circuit_type_has_7_values():
    """7 types de circuits couvrent le périmètre V1."""
    expected = {"lighting", "socket", "kitchen_special", "laundry",
                "boiler", "heating", "towel_warmer"}
    actual = {ct.value for ct in CircuitType}
    assert actual == expected


def test_circuit_dataclass_fields():
    """Circuit a id, type, label, breaker_amps, cable_section_mm2, rooms_served,
    n_devices, requires_type_a."""
    c = Circuit(
        id="circ_abc12345",
        type=CircuitType.LIGHTING,
        label="Lum Séjour",
        breaker_amps=10,
        cable_section_mm2=1.5,
        rooms_served=["Sejour"],
        n_devices=3,
        requires_type_a=False,
    )
    assert c.id == "circ_abc12345"
    assert c.type == CircuitType.LIGHTING
    assert c.breaker_amps == 10
    assert c.cable_section_mm2 == 1.5
    assert not c.requires_type_a


def test_rcd_dataclass_fields():
    from src.planrec.nfc_tableau import RCD, Circuit, CircuitType
    c = Circuit(id="c1", type=CircuitType.LIGHTING, label="x",
                breaker_amps=10, cable_section_mm2=1.5)
    rcd = RCD(id="rcd_1", rcd_type="A", amps=40, sensitivity_ma=30,
              circuits=[c])
    assert rcd.rcd_type == "A"
    assert rcd.amps == 40
    assert rcd.sensitivity_ma == 30
    assert len(rcd.circuits) == 1


def test_tableau_dataclass_fields():
    from src.planrec.nfc_tableau import Tableau
    t = Tableau(
        typology="T3", typology_source="auto", surface_m2=80.0,
        heating_enabled=True, rcds=[], total_modules=0, n_rails=1,
        notes=["RJ45 → coffret VDI"], warnings=[],
    )
    assert t.typology == "T3"
    assert t.heating_enabled is True
    assert t.notes == ["RJ45 → coffret VDI"]


def test_detect_typology_T1_studio():
    """1 séjour seul → T1 (studio)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global(
        [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}],
    )
    assert detect_typology(devis) == "T1"


def test_detect_typology_T2_living_plus_1_bedroom():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T2"


def test_detect_typology_T3_living_plus_2_bedrooms():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T3"


def test_detect_typology_T5_capped_at_5():
    """4+ chambres + séjour → T5 (on cap au lieu de T6/T7)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "B4", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T5"


def test_lighting_one_room_one_circuit_if_few_lights():
    """Une pièce avec ≤5 lights → 1 circuit éclairage 10A/1.5mm²."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    rooms_with_lights = [("Sejour", 3), ("Chambre 1", 2)]
    circuits = _build_lighting_circuits(rooms_with_lights)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 10
    assert circuits[0].cable_section_mm2 == 1.5
    assert circuits[0].n_devices == 5
    assert set(circuits[0].rooms_served) == {"Sejour", "Chambre 1"}


def test_lighting_bin_packing_overflow_creates_2_circuits():
    """7 lights ne tiennent pas sur 1 circuit (cap 5) → 2 circuits."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    rooms_with_lights = [("Cuisine", 7)]
    circuits = _build_lighting_circuits(rooms_with_lights)
    assert len(circuits) == 2
    assert sum(c.n_devices for c in circuits) == 7


def test_sockets_one_room_one_circuit():
    """Pièce 5 prises → 1 circuit 20A/2.5mm²."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms_with_sockets = [("Sejour", 5)]
    circuits = _build_socket_circuits(rooms_with_sockets)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].n_devices == 5


def test_sockets_pack_small_rooms_together():
    """3 petites pièces (2+1+1 prises) → 1 circuit grouppé."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("WC", 1), ("Entrée", 2), ("Couloir", 1)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 1
    assert circuits[0].n_devices == 4


def test_sockets_large_room_dedicated_circuit():
    """Pièce 12 prises → 1 circuit dédié."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("Sejour", 12)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 1
    assert circuits[0].n_devices == 12


def test_heating_pack_2_convectors_per_circuit():
    """4 convecteurs → 2 circuits HEATING (2 max par circuit, 20A)."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    rooms_with_conv = [("Sejour", 1), ("Chambre 1", 1), ("Chambre 2", 1),
                       ("Chambre 3", 1)]
    circuits = _build_heating_circuits(rooms_with_conv, n_towel_warmers=0)
    heating = [c for c in circuits if c.type.value == "heating"]
    assert len(heating) == 2
    assert all(c.breaker_amps == 20 and c.cable_section_mm2 == 2.5
               for c in heating)
    assert sum(c.n_devices for c in heating) == 4


def test_heating_1_circuit_per_towel_warmer():
    """3 sèche-serviettes → 3 circuits dédiés TOWEL_WARMER (1 par circuit)."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits(rooms_with_convectors=[],
                                       n_towel_warmers=3)
    tw = [c for c in circuits if c.type.value == "towel_warmer"]
    assert len(tw) == 3


def test_heating_empty_lists():
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits([], n_towel_warmers=0)
    assert circuits == []


def test_specialized_each_appliance_one_circuit():
    """6 appareils spé → 6 circuits dédiés."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {
        EquipmentType.OVEN: 1,
        EquipmentType.COOKTOP: 1,
        EquipmentType.DISHWASHER: 1,
        EquipmentType.WASHING_MACHINE: 1,
        EquipmentType.DRYER: 1,
        EquipmentType.BOILER: 1,
    }
    circuits = _build_specialized_circuits(counts)
    assert len(circuits) == 6


def test_specialized_plaque_is_32A_6mm2_type_a():
    """Plaque cuisson → calibre 32A, câble 6mm², requires_type_a=True."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {EquipmentType.COOKTOP: 1}
    circuits = _build_specialized_circuits(counts)
    assert len(circuits) == 1
    plaque = circuits[0]
    assert plaque.breaker_amps == 32
    assert plaque.cable_section_mm2 == 6.0
    assert plaque.requires_type_a is True


def test_specialized_lavelinge_is_20A_2_5mm2_type_a():
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {EquipmentType.WASHING_MACHINE: 1}
    circuits = _build_specialized_circuits(counts)
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].requires_type_a is True


def test_min_rcds_T2_returns_2():
    """T2 → 2 RCD minimum (règle cabinet)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=None,
                             n_breakers=5) == 2


def test_min_rcds_surface_overrides_typology():
    """T1 mais 120 m² → 3 RCD (règle NFC stricte > règle typo)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T1", surface_m2=120.0,
                             n_breakers=5) == 3


def test_min_rcds_many_breakers_forces_more():
    """T2 (2 RCD min) mais 18 disjoncteurs → ceil(18/8) = 3 RCD."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=80.0,
                             n_breakers=18) == 3


def test_distribute_type_A_contains_cooktop_and_lavelinge():
    """RCD1 Type A contient OBLIGATOIREMENT Plaque + LL."""
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Plaque",
                     breaker_amps=32, cable_section_mm2=6.0,
                     requires_type_a=True)
    ll = Circuit(id="c2", type=CircuitType.LAUNDRY, label="LL",
                 breaker_amps=20, cable_section_mm2=2.5,
                 requires_type_a=True)
    other = Circuit(id="c3", type=CircuitType.LIGHTING, label="Lum",
                    breaker_amps=10, cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([plaque, ll, other], n_rcds=2)
    assert rcds[0].rcd_type == "A"
    type_a_ids = {c.id for c in rcds[0].circuits}
    assert "c1" in type_a_ids
    assert "c2" in type_a_ids


def test_distribute_other_rcds_are_type_AC():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="P",
                     breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True)
    others = [Circuit(id=f"c{i+2}", type=CircuitType.LIGHTING, label=f"L{i}",
                      breaker_amps=10, cable_section_mm2=1.5)
              for i in range(2)]
    rcds = _distribute_circuits_to_rcds([plaque] + others, n_rcds=2)
    assert rcds[0].rcd_type == "A"
    assert rcds[1].rcd_type == "AC"


def test_rcd_amps_formula_normalized():
    """RCD avec 4× 20A non-chauffage → (4*20)/2 = 40A normalisé."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id=f"c{i}", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5)
        for i in range(4)
    ]
    assert _compute_rcd_amps(circuits) == 40


def test_rcd_amps_heating_summed_not_halved():
    """1× 20A socket + 1× 20A heating → 20/2 + 20 = 30 → arrondi à 40A."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id="c1", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
        Circuit(id="c2", type=CircuitType.HEATING, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
    ]
    assert _compute_rcd_amps(circuits) == 40


def test_generate_tableau_T3_complete_flow():
    """T3 standard (séjour + 2 chambres + cuisine + SdB + entrée) →
    tableau cohérent : 3 RCD min, Type A contient Plaque + LL, notes RJ45."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "E1", "c2_class": "Entry"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)

    assert tableau.typology == "T3"
    assert tableau.heating_enabled is True
    assert len(tableau.rcds) >= 3
    # Premier RCD est Type A et contient Plaque + LL
    type_a_rcd = tableau.rcds[0]
    assert type_a_rcd.rcd_type == "A"
    labels = [c.label for c in type_a_rcd.circuits]
    assert any("Plaque" in lbl for lbl in labels)
    assert any("Lave-linge" in lbl for lbl in labels)
    # Note RJ45 hors tableau
    assert any("RJ45" in n for n in tableau.notes)


def test_generate_tableau_typology_override():
    """typology_override force la typologie quel que soit le devis."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ]
    devis = compute_devis_global(rooms)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True,
                                typology_override="T4")
    assert tableau.typology == "T4"
    assert tableau.typology_source == "user_override"


def test_generate_tableau_heating_disabled_no_heating_circuits():
    """heating_enabled=False → 0 circuits HEATING ni TOWEL_WARMER."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "S1", "c2_class": "Bath"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    all_circuits = [c for r in tableau.rcds for c in r.circuits]
    heating_circuits = [c for c in all_circuits
                        if c.type.value in ("heating", "towel_warmer")]
    assert heating_circuits == []
