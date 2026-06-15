"""Tests pour schema_unifilaire (format Hager paysage)."""
from __future__ import annotations


def _cartouche(**over):
    from src.planrec.schema_unifilaire import CartoucheInfo
    base = dict(projet="Maison Dupont", client_nom="Dupont SARL",
                client_ville="Lyon", puissance_kva=9, regime_neutre="TT",
                date_iso="2026-06-15")
    base.update(over)
    return CartoucheInfo(**base)


def _make_tableau(n_ids: int, departs_per_id: int = 3, typology: str = "T3"):
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    rcds = []
    for i in range(n_ids):
        circuits = [
            Circuit(id=f"c{i}_{j}", type=CircuitType.SOCKET,
                    label=f"Prises pièce {j}", breaker_amps=20,
                    cable_section_mm2=2.5, rooms_served=[f"P{j}"], n_devices=4)
            for j in range(departs_per_id)
        ]
        rcds.append(RCD(id=f"rcd{i}", rcd_type="A" if i == 0 else "AC",
                        amps=40, sensitivity_ma=30, circuits=circuits))
    return Tableau(typology=typology, typology_source="auto", surface_m2=80.0,
                   heating_enabled=True, rcds=rcds, total_modules=0, n_rails=0,
                   notes=[], warnings=[])


def test_derive_puissance_kva():
    from src.planrec.schema_unifilaire import derive_puissance_kva
    assert derive_puissance_kva("T1") == 6
    assert derive_puissance_kva("T3") == 9
    assert derive_puissance_kva("T5") == 12
    assert derive_puissance_kva("???") == 9


def test_derive_db_calibre():
    from src.planrec.schema_unifilaire import derive_db_calibre
    assert derive_db_calibre(6) == 30
    assert derive_db_calibre(9) == 45
    assert derive_db_calibre(12) == 60
    assert derive_db_calibre(7) == 30   # plus proche tier <= 7 => 6 => 30 A


def test_cartouche_info_fields():
    c = _cartouche()
    assert c.projet == "Maison Dupont"
    assert c.client_nom == "Dupont SARL"
    assert c.puissance_kva == 9
    assert c.regime_neutre == "TT"


def test_pdf_header_and_single_folio():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2), _cartouche())
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_empty_tableau_valid_single_folio():
    from pypdf import PdfReader
    import io
    from src.planrec.nfc_tableau import Tableau
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0, n_rails=0,
                    notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(empty, _cartouche(puissance_kva=6))
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_cartouche_text_and_grid_present():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2), _cartouche())
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Maison Dupont" in text
    assert "Dupont SARL" in text
    assert "kVA" in text
    assert "TT" in text
    assert "Folio" in text
    assert "14" in text
    for letter in ("A", "G"):
        assert letter in text


def test_multifolio_pagination():
    """4 RCD × (1 ID + 3 départs) = 16 slots > 12/folio => 2 folios."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(4, departs_per_id=3), _cartouche())
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2
