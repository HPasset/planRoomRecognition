"""Tests pour schema_unifilaire (rendu PDF schéma unifilaire tableau)."""
from __future__ import annotations


def test_circuit_repere_format():
    from src.planrec.schema_unifilaire import circuit_repere
    assert circuit_repere(1, 1) == "1.1"
    assert circuit_repere(2, 3) == "2.3"


def test_agcp_constants_present():
    from src.planrec import schema_unifilaire as su
    assert su.AGCP_SENSITIVITY_MA == 500
    assert su.DEFAULT_CURVE == "C"
    assert "artisan" in su.AGCP_CONFIRM_NOTE.lower()


def _make_tableau(n_ids: int, departs_per_id: int = 3, typology: str = "T3"):
    """Construit un Tableau de test : n_ids RCD, departs_per_id circuits chacun."""
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    rcds = []
    for i in range(n_ids):
        circuits = [
            Circuit(
                id=f"c{i}_{j}",
                type=CircuitType.SOCKET,
                label=f"Prises pièce {j}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=[f"Pièce {j}"],
                n_devices=4,
            )
            for j in range(departs_per_id)
        ]
        rcds.append(RCD(id=f"rcd{i}", rcd_type="A" if i == 0 else "AC",
                        amps=40, sensitivity_ma=30, circuits=circuits))
    return Tableau(typology=typology, typology_source="auto", surface_m2=80.0,
                   heating_enabled=True, rcds=rcds, total_modules=0, n_rails=0,
                   notes=[], warnings=[])


def test_pdf_header_and_nonempty():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2))
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_empty_tableau_produces_valid_single_page_pdf():
    from pypdf import PdfReader
    import io
    from src.planrec.nfc_tableau import Tableau
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0, n_rails=0,
                    notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(empty)
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_multipage_when_many_ids():
    """7 ID → ceil(7/3) = 3 pages."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(7, departs_per_id=2))
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 3


def test_saturated_id_8_departures_does_not_crash():
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(1, departs_per_id=8))
    assert pdf.startswith(b"%PDF-")


def test_repere_and_agcp_text_in_pdf():
    """Le repère '1.1' et la désignation AGCP figurent dans le texte du PDF."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(1, departs_per_id=2))
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "1.1" in text
    assert "branchement" in text.lower()


def test_all_circuit_types_render_without_crash():
    """Chaque CircuitType doit résoudre un picto et rendre sans exception."""
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    circuits = [
        Circuit(id=f"c{i}", type=ct, label=ct.value, breaker_amps=16,
                cable_section_mm2=1.5, rooms_served=["X"], n_devices=1)
        for i, ct in enumerate(CircuitType)
    ]
    rcd = RCD(id="r", rcd_type="AC", amps=40, sensitivity_ma=30, circuits=circuits)
    tab = Tableau(typology="T4", typology_source="auto", surface_m2=90.0,
                  heating_enabled=True, rcds=[rcd], total_modules=0, n_rails=0,
                  notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(tab)
    assert pdf.startswith(b"%PDF-")
