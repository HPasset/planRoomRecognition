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
