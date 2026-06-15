"""Tests pour etiquettes_renderer (rendu PDF étiquettes tableau électrique)."""
from __future__ import annotations


def test_load_icon_as_drawing_returns_reportlab_drawing():
    """load_icon_as_drawing('socket') retourne un Drawing reportlab non-None."""
    from src.planrec.etiquettes_renderer import load_icon_as_drawing
    from reportlab.graphics.shapes import Drawing
    d = load_icon_as_drawing("socket")
    assert isinstance(d, Drawing)
    assert d.width > 0
    assert d.height > 0


def test_load_icon_as_drawing_substitutes_currentcolor_to_black():
    """Le SVG contient 'currentColor' qui doit être remplacé par '#000000'
    avant parsing (svglib ne gère pas currentColor natif)."""
    from src.planrec.etiquettes_renderer import load_icon_as_drawing
    # Le test passe si pas d'exception lors du chargement d'une icône
    # qui utilise currentColor (toutes nos icônes en utilisent par charte)
    d = load_icon_as_drawing("light")
    assert d is not None


def test_load_icon_as_drawing_unknown_raises():
    """Demander une icône inexistante doit lever FileNotFoundError pour
    éviter les bugs silencieux."""
    import pytest
    from src.planrec.etiquettes_renderer import load_icon_as_drawing
    with pytest.raises(FileNotFoundError):
        load_icon_as_drawing("nonexistent_svg_id")


def test_compute_strip_widths_returns_expected_dimensions():
    """Pour un RCD à 3 disjoncteurs, les largeurs en mm doivent être :
    index 6 + ID 35 + 3 x Qn (17.5) + batIA (reste) = 277 mm zone imprimable."""
    from src.planrec.etiquettes_renderer import compute_strip_widths

    widths = compute_strip_widths(n_disjoncteurs=3, page_usable_width_mm=277.0)
    assert widths["index"] == 6.0
    assert widths["id"] == 35.0
    assert widths["disjoncteurs"] == [17.5, 17.5, 17.5]
    # Reste pour le cartouche batIA
    expected_cartouche = 277.0 - 6.0 - 35.0 - (3 * 17.5)
    assert abs(widths["cartouche"] - expected_cartouche) < 0.01


def test_compute_strip_widths_cartouche_min_30mm():
    """Le cartouche batIA fait au moins 30 mm pour la lisibilité du logo +
    'Tableau électrique'. Avec 7 disjoncteurs (max raisonnable par rangée),
    le cartouche doit encore respecter ce minimum."""
    from src.planrec.etiquettes_renderer import compute_strip_widths

    # 7 disjoncteurs max raisonnables (cf. spec) — au-delà, overflow géré ailleurs
    widths = compute_strip_widths(n_disjoncteurs=7, page_usable_width_mm=277.0)
    assert widths["cartouche"] >= 30.0
