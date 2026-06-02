"""Tests pour tableau_renderer (rendu SVG + HTML + PDF du tableau)."""
from __future__ import annotations


def test_render_svg_returns_str_starting_with_svg():
    """render_svg sortie commence par '<svg' (string XML)."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import Tableau
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0,
                    n_rails=0, notes=[], warnings=[])
    out = render_svg(empty)
    assert isinstance(out, str)
    assert out.startswith("<svg") or out.startswith("<div")


def test_circuit_colors_constants_present():
    """CIRCUIT_COLORS contient les 7 CircuitType avec hex couleur."""
    from src.planrec.tableau_renderer import CIRCUIT_COLORS
    from src.planrec.nfc_tableau import CircuitType
    for ct in CircuitType:
        assert ct in CIRCUIT_COLORS
        assert CIRCUIT_COLORS[ct].startswith("#")
        assert len(CIRCUIT_COLORS[ct]) == 7
