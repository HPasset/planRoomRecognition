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


def test_split_rcd_into_rows_no_overflow():
    """Un RCD à 5 disjoncteurs tient sur 1 seule rangée."""
    from src.planrec.etiquettes_renderer import split_rcd_into_rows
    from src.planrec.nfc_tableau import Circuit, RCD, CircuitType
    circuits = [
        Circuit(id=f"c{i}", type=CircuitType.SOCKET, label=f"Q{i}",
                breaker_amps=20, cable_section_mm2=2.5)
        for i in range(5)
    ]
    rcd = RCD(id="rcd1", rcd_type="A", amps=40, sensitivity_ma=30, circuits=circuits)
    rows = split_rcd_into_rows(rcd, max_per_row=7)
    assert len(rows) == 1
    assert len(rows[0]) == 5


def test_split_rcd_into_rows_overflow_on_8_disjoncteurs():
    """Un RCD à 8 disjoncteurs (max NFC) déborde sur 2 rangées : 7 + 1."""
    from src.planrec.etiquettes_renderer import split_rcd_into_rows
    from src.planrec.nfc_tableau import Circuit, RCD, CircuitType
    circuits = [
        Circuit(id=f"c{i}", type=CircuitType.SOCKET, label=f"Q{i}",
                breaker_amps=20, cable_section_mm2=2.5)
        for i in range(8)
    ]
    rcd = RCD(id="rcd1", rcd_type="A", amps=40, sensitivity_ma=30, circuits=circuits)
    rows = split_rcd_into_rows(rcd, max_per_row=7)
    assert len(rows) == 2
    assert len(rows[0]) == 7
    assert len(rows[1]) == 1


def test_paginate_rcds_5_per_page_default():
    """5 RCDs tiennent sur 1 page, 6 RCDs occupent 2 pages."""
    from src.planrec.etiquettes_renderer import paginate_rcds
    from src.planrec.nfc_tableau import RCD
    rcds_5 = [RCD(id=f"r{i}", rcd_type="AC", amps=40, sensitivity_ma=30, circuits=[])
              for i in range(5)]
    pages_5 = paginate_rcds(rcds_5, per_page=5)
    assert len(pages_5) == 1
    assert len(pages_5[0]) == 5

    rcds_6 = rcds_5 + [RCD(id="r5", rcd_type="AC", amps=40, sensitivity_ma=30, circuits=[])]
    pages_6 = paginate_rcds(rcds_6, per_page=5)
    assert len(pages_6) == 2
    assert len(pages_6[0]) == 5
    assert len(pages_6[1]) == 1


def test_render_rcd_row_draws_expected_text_and_rects():
    """Le rendu d'une rangée RCD doit dessiner :
    - Texte 'ID 1' dans la cellule ID (strip header)
    - Texte 'Q1' dans la première cellule Qn (strip header)
    - Texte du label de circuit dans le body (ex. 'Plaque cuisson')
    - 'Interrupteur différentiel' dans la cellule ID body
    Vérifié via parsing du PDF généré (texte extrait)."""
    import io
    from pypdf import PdfReader
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import landscape, A4
    from src.planrec.etiquettes_renderer import render_rcd_row
    from src.planrec.nfc_tableau import Circuit, RCD, CircuitType

    circuits = [
        Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Plaque cuisson",
                breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True),
    ]
    rcd = RCD(id="rcd1", rcd_type="A", amps=63, sensitivity_ma=30, circuits=circuits)

    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=landscape(A4))
    render_rcd_row(
        canvas=canvas,
        rcd=rcd,
        row_circuits=circuits,
        rcd_index=1,
        global_q_start=1,
        y_top_mm=180,
        page_usable_width_mm=277,
    )
    canvas.save()

    reader = PdfReader(io.BytesIO(buf.getvalue()))
    text = reader.pages[0].extract_text()
    assert "ID 1" in text
    assert "Q1" in text
    assert "Interrupteur" in text and "différentiel" in text
    assert "Plaque cuisson" in text
