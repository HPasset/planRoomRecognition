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


def test_schematic_tokens_present():
    """Repères DB1/ID1/Q1, L1,N, PE1 présents dans le texte du folio 1."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2, departs_per_id=2), _cartouche())
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "DB1" in text
    assert "ID1" in text
    assert "Q1" in text
    assert "L1,N" in text
    assert "PE1" in text


def test_global_q_numbering_across_folios():
    """Numérotation Q globale et continue : Q1 sur folio 1, Q12 sur le dernier."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(4, departs_per_id=3), _cartouche())
    reader = PdfReader(io.BytesIO(pdf))
    assert "Q1" in reader.pages[0].extract_text()
    assert "Q12" in reader.pages[1].extract_text()


def test_all_circuit_types_render_without_crash():
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
    pdf = render_schema_unifilaire_pdf(tab, _cartouche(puissance_kva=12))
    assert pdf.startswith(b"%PDF-")


def test_db_and_id_derived_annotations_in_pdf():
    """Spec §8 : le DB porte 500 mA + calibre dérivé de la puissance, et les ID
    portent leur sensibilité 30 mA + type. Pour 12 kVA, DB = 60 A."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(1, departs_per_id=2),
                                       _cartouche(puissance_kva=12))
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "60 A" in text          # DB calibre dérivé de 12 kVA
    assert "500 mA" in text        # sensibilité AGCP (sélectif)
    assert "30mA" in text          # sensibilité ID 30 mA
    assert "Type A" in text        # type du 1er ID (rcd_type "A")


def test_localisation_lists_every_room_horizontally():
    """La bande Localisation écrit l'en-tête du circuit puis le nom complet de
    chaque pièce, une par ligne (plus de texte vertical tronqué)."""
    import io
    from pypdf import PdfReader
    from src.planrec.nfc_tableau import Circuit, RCD, CircuitType, Tableau
    from src.planrec.schema_unifilaire import CartoucheInfo, render_schema_unifilaire_pdf

    circ = Circuit(id="c1", type=CircuitType.LIGHTING, label="Écl. CH2 CH3 DGT BAIN CEL",
                   breaker_amps=10, cable_section_mm2=1.5,
                   rooms_served=["Chambre 2", "Chambre 3", "Dégagement", "Salle de bain", "Cellier"])
    gtl = Circuit(id="c2", type=CircuitType.SOCKET, label="Prises GTL ×2",
                  breaker_amps=16, cable_section_mm2=1.5, n_devices=2)
    rcd = RCD(id="r1", rcd_type="A", amps=40, sensitivity_ma=30, circuits=[circ, gtl])
    tableau = Tableau(typology="T3", typology_source="auto", surface_m2=None,
                      heating_enabled=False, rcds=[rcd], total_modules=5,
                      n_rails=1, notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(tableau, CartoucheInfo(
        projet="p", client_nom="c", client_ville="v", puissance_kva=9,
        regime_neutre="TT", date_iso="2026-09-07"))
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for expected in ("Éclairage", "Chambre 2", "Chambre 3", "Dégagement", "Salle de bain", "Cellier", "Prises GTL ×2"):
        assert expected in text, (expected, text)
