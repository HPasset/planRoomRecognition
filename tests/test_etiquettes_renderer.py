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
