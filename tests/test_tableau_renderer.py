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


def test_render_svg_contains_all_circuits_as_rect():
    """Tous les circuits sont rendus comme rect colorés."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    svg = render_svg(tab)

    total_circuits = sum(len(r.circuits) for r in tab.rcds)
    n_rect = svg.count("<rect")
    assert n_rect >= total_circuits + len(tab.rcds)


def test_render_svg_well_formed_xml():
    """SVG output parseable comme XML."""
    import xml.etree.ElementTree as ET
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0}]
    devis = compute_devis_global(rooms)
    tab = generate_tableau(devis_global=devis, heating_enabled=False)
    svg = render_svg(tab)
    ET.fromstring(svg)


def test_render_svg_dimensions_scale_with_n_rcds():
    """Hauteur SVG croît avec le nombre de RCD."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    small_rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}]
    big_rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    svg_small = render_svg(generate_tableau(
        compute_devis_global(small_rooms, heating_enabled=False),
        heating_enabled=False,
    ))
    svg_big = render_svg(generate_tableau(
        compute_devis_global(big_rooms, heating_enabled=True),
        heating_enabled=True,
    ))
    h_small = int(svg_small.split('height="')[1].split('"')[0])
    h_big = int(svg_big.split('height="')[1].split('"')[0])
    assert h_big > h_small


def test_render_html_table_one_row_per_circuit():
    """Une ligne <tr> par circuit + 1 row header."""
    from src.planrec.tableau_renderer import render_html_table
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    html = render_html_table(tab)

    total_circuits = sum(len(r.circuits) for r in tab.rcds)
    n_tr = html.count("<tr")
    assert n_tr == total_circuits + 1


def test_render_html_table_contains_breaker_amps_and_section():
    """Le HTML mentionne calibre + section câble."""
    from src.planrec.tableau_renderer import render_html_table
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "K1", "c2_class": "Kitchen"}]
    devis = compute_devis_global(rooms)
    tab = generate_tableau(devis_global=devis)
    html = render_html_table(tab)
    assert "32 A" in html or "32A" in html
    assert "6 mm²" in html or "6.0 mm²" in html or "6.0mm" in html


def test_export_pdf_returns_valid_bytes():
    """export_pdf retourne des bytes parseables comme PDF."""
    from src.planrec.tableau_renderer import export_pdf
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global
    import io
    from pypdf import PdfReader

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    pdf_bytes = export_pdf(tab)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "Tableau" in text or "tableau" in text.lower()
