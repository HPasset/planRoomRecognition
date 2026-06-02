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
