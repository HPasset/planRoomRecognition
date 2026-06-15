"""Tests pour icon_assets (helpers partagés de pictos tableau électrique)."""
from __future__ import annotations


def test_load_icon_as_drawing_returns_drawing():
    from reportlab.graphics.shapes import Drawing
    from src.planrec.icon_assets import load_icon_as_drawing
    d = load_icon_as_drawing("socket")
    assert isinstance(d, Drawing)
    assert d.width > 0 and d.height > 0


def test_load_icon_as_drawing_unknown_raises():
    import pytest
    from src.planrec.icon_assets import load_icon_as_drawing
    with pytest.raises(FileNotFoundError):
        load_icon_as_drawing("nonexistent_svg_id")


def test_resolve_svg_id_prefers_label_prefix():
    """Plaque/Four/LV partagent CircuitType KITCHEN_SPECIAL mais pictos distincts."""
    from src.planrec.icon_assets import resolve_svg_id_for_circuit
    from src.planrec.nfc_tableau import Circuit, CircuitType
    four = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Four",
                   breaker_amps=20, cable_section_mm2=2.5)
    plaque = Circuit(id="c2", type=CircuitType.KITCHEN_SPECIAL, label="Plaque cuisson",
                     breaker_amps=32, cable_section_mm2=6.0)
    assert resolve_svg_id_for_circuit(four) == "oven"
    assert resolve_svg_id_for_circuit(plaque) == "cooktop"


def test_resolve_svg_id_falls_back_to_circuit_type():
    from src.planrec.icon_assets import resolve_svg_id_for_circuit
    from src.planrec.nfc_tableau import Circuit, CircuitType
    light = Circuit(id="c3", type=CircuitType.LIGHTING, label="",
                    breaker_amps=10, cable_section_mm2=1.5)
    assert resolve_svg_id_for_circuit(light) == "light"


def test_etiquettes_renderer_reexports_load_icon():
    """Régression : l'ancien point d'import doit continuer de fonctionner."""
    from src.planrec.etiquettes_renderer import load_icon_as_drawing
    assert load_icon_as_drawing("light") is not None
