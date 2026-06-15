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
    # Le label est wrap sur 2 lignes ("Plaque" + "cuisson") par _wrap_cell_label
    # (max_chars=8). On vérifie les 2 fragments séparément dans le texte extrait.
    assert "Plaque" in text
    assert "cuisson" in text


def test_render_etiquettes_pdf_returns_valid_pdf_bytes():
    """Le PDF généré commence par '%PDF-' et est parsable par pypdf."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "B1", "c2_class": "BedRoom"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)
    pdf_bytes = render_etiquettes_pdf(tableau)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1


def test_render_etiquettes_pdf_contains_print_scale_instruction():
    """L'instruction 'Imprimer à 100 %' (ou variantes) doit apparaître dans
    le pied de page pour éviter qu'un user ne réduise l'échelle d'impression."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "K1", "c2_class": "Kitchen"}]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    pdf_bytes = render_etiquettes_pdf(tableau)
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
    # On accepte plusieurs variantes textuelles
    assert ("100 %" in text or "100%" in text or
            "Taille réelle" in text or "1:1" in text)


def test_render_etiquettes_pdf_page_count_matches_rcds():
    """Pour 5 RCDs : 1 page. Pour 6 RCDs : 2 pages."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType

    def _make_rcd(i: int) -> RCD:
        circuits = [Circuit(id=f"c{i}_{j}", type=CircuitType.SOCKET,
                            label="Prises", breaker_amps=20,
                            cable_section_mm2=2.5) for j in range(3)]
        return RCD(id=f"rcd{i}", rcd_type="AC", amps=40, sensitivity_ma=30,
                   circuits=circuits)

    # 5 RCDs -> 1 page
    tab_5 = Tableau(typology="T3", typology_source="auto", surface_m2=None,
                    heating_enabled=False,
                    rcds=[_make_rcd(i) for i in range(5)],
                    total_modules=15, n_rails=1, notes=[], warnings=[])
    assert len(PdfReader(io.BytesIO(render_etiquettes_pdf(tab_5))).pages) == 1

    # 6 RCDs -> 2 pages
    tab_6 = Tableau(typology="T5", typology_source="auto", surface_m2=None,
                    heating_enabled=False,
                    rcds=[_make_rcd(i) for i in range(6)],
                    total_modules=18, n_rails=1, notes=[], warnings=[])
    assert len(PdfReader(io.BytesIO(render_etiquettes_pdf(tab_6))).pages) == 2


def test_render_etiquettes_pdf_q_numbering_continuous_across_rcds():
    """Le Q-numbering est global continu : Q1..Q3 sur RCD 1, Q4 commence sur RCD 2."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType

    rcd_1 = RCD(id="rcd1", rcd_type="A", amps=40, sensitivity_ma=30,
                circuits=[Circuit(id=f"c1_{j}", type=CircuitType.SOCKET,
                                  label="Prises", breaker_amps=20,
                                  cable_section_mm2=2.5) for j in range(3)])
    rcd_2 = RCD(id="rcd2", rcd_type="AC", amps=40, sensitivity_ma=30,
                circuits=[Circuit(id=f"c2_{j}", type=CircuitType.LIGHTING,
                                  label="Éclairage", breaker_amps=10,
                                  cable_section_mm2=1.5) for j in range(2)])
    tab = Tableau(typology="T3", typology_source="auto", surface_m2=None,
                  heating_enabled=False, rcds=[rcd_1, rcd_2],
                  total_modules=5, n_rails=1, notes=[], warnings=[])
    pdf_bytes = render_etiquettes_pdf(tab)
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
    # Sur RCD 1 : Q1, Q2, Q3
    for q in ("Q1", "Q2", "Q3"):
        assert q in text
    # Sur RCD 2 (global continu) : Q4, Q5
    for q in ("Q4", "Q5"):
        assert q in text


def test_render_etiquettes_pdf_overflow_creates_bis_row():
    """Un RCD à 8 disjoncteurs (limite NFC) produit 2 rangées : 1 puis 1 bis.
    Vérifié par la présence du texte '1 bis' dans le PDF."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType

    circuits = [
        Circuit(id=f"c{j}", type=CircuitType.SOCKET, label="Prises",
                breaker_amps=20, cable_section_mm2=2.5)
        for j in range(8)
    ]
    rcd = RCD(id="rcd1", rcd_type="AC", amps=40, sensitivity_ma=30,
              circuits=circuits)
    tab = Tableau(typology="T2", typology_source="auto", surface_m2=None,
                  heating_enabled=False, rcds=[rcd], total_modules=8,
                  n_rails=1, notes=[], warnings=[])
    pdf_bytes = render_etiquettes_pdf(tab)
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
    # Convention : index "1 bis" pour la rangée de débordement
    assert "1 bis" in text
    # Les Qn vont de Q1 à Q8 continûment
    for q in (f"Q{i}" for i in range(1, 9)):
        assert q in text


def test_render_etiquettes_pdf_empty_tableau_returns_warning_page():
    """Un Tableau sans aucun RCD ne doit pas crasher mais émettre une page
    avec un message d'avertissement."""
    import io
    from pypdf import PdfReader
    from src.planrec.etiquettes_renderer import render_etiquettes_pdf
    from src.planrec.nfc_tableau import Tableau

    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0,
                    n_rails=0, notes=[], warnings=[])
    pdf_bytes = render_etiquettes_pdf(empty)
    assert pdf_bytes.startswith(b"%PDF-")
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text()
    assert "Aucun RCD" in text or "vide" in text
