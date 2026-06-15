"""Renderer du schéma unifilaire du tableau électrique (cible dossier Consuel).

Symboles d'appareillage EN 60617 dessinés en primitives reportlab (AGCP, DDR,
disjoncteur, terre) + pictos d'usage maison (icon_assets) en bout de départ.
Mise en page A4 portrait, une colonne par ID, pagination par ID, cartouche.

Logique pure : aucun import Streamlit/React. Voir
docs/superpowers/specs/2026-06-15-schema-unifilaire-design.md
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.units import mm
from reportlab.graphics import renderPDF
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau
from src.planrec.icon_assets import load_icon_as_drawing, resolve_svg_id_for_circuit
from src.planrec.etiquettes_renderer import paginate_rcds, _draw_batia_logo_cartouche

# --- AGCP générique (tête d'installation, valeurs à confirmer par l'artisan) ---
AGCP_DESIGNATION = "Disjoncteur de branchement"
AGCP_CALIBRE = "15/45 A"
AGCP_SENSITIVITY_MA = 500          # sélectif (S)
DEFAULT_CURVE = "C"                 # courbe disjoncteurs divisionnaires (résidentiel)
AGCP_CONFIRM_NOTE = "Valeurs amont (AGCP, terre) à confirmer par l'artisan"

# --- Géométrie page (mm, A4 portrait) ---
A4_PORTRAIT_W_MM = 210.0
A4_PORTRAIT_H_MM = 297.0
PAGE_MARGIN_MM = 15.0
USABLE_W_MM = A4_PORTRAIT_W_MM - 2 * PAGE_MARGIN_MM   # 180
IDS_PER_PAGE = 3
HEAD_ZONE_H_MM = 38.0              # zone AGCP + terre + barre
ID_HEADER_H_MM = 22.0
DEPARTURE_H_MM = 22.0
CARTOUCHE_H_MM = 18.0


def circuit_repere(id_idx: int, depart_idx: int) -> str:
    """Repère lisible d'un départ : 'N°ID.N°départ' (ex. '1.3')."""
    return f"{id_idx}.{depart_idx}"


def _yp(y_top_mm: float) -> float:
    """Coord 'depuis le haut de page' (mm) → points reportlab (origine bas-gauche)."""
    return (A4_PORTRAIT_H_MM - y_top_mm) * mm


def _draw_picto(canvas, svg_id: str, x_mm: float, y_top_mm: float, size_mm: float) -> None:
    """Place un picto d'usage (viewBox 40×40) scalé dans size_mm, coin haut-gauche
    en (x_mm, y_top_mm depuis le haut)."""
    try:
        drawing = load_icon_as_drawing(svg_id)
    except FileNotFoundError:
        return
    ref = max(drawing.width, drawing.height) or 40.0
    scale = (size_mm * mm) / ref
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, canvas, x_mm * mm, _yp(y_top_mm + size_mm))


def _draw_head(canvas, busbar_y_top_mm: float) -> None:
    """AGCP (disjoncteur de branchement) + prise de terre + barre de répartition."""
    x_left = PAGE_MARGIN_MM
    box_w, box_h = 14.0, 16.0
    box_top = busbar_y_top_mm - box_h - 8.0

    # Boîtier AGCP + contact diagonal
    canvas.setLineWidth(1.2)
    canvas.rect(x_left * mm, _yp(box_top + box_h), box_w * mm, box_h * mm)
    canvas.line((x_left + 3) * mm, _yp(box_top + box_h - 3),
                (x_left + box_w - 3) * mm, _yp(box_top + 3))
    # Amont (vers le haut) + aval (vers la barre)
    canvas.line((x_left + box_w / 2) * mm, _yp(box_top),
                (x_left + box_w / 2) * mm, _yp(box_top - 6))
    canvas.line((x_left + box_w / 2) * mm, _yp(box_top + box_h),
                (x_left + box_w / 2) * mm, _yp(busbar_y_top_mm))
    # Annotations
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 5), AGCP_DESIGNATION)
    canvas.setFont("Helvetica", 7)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 9.5),
                      f"{AGCP_CALIBRE} · {AGCP_SENSITIVITY_MA} mA · sélectif")
    canvas.setFont("Helvetica-Oblique", 6)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 13.5), AGCP_CONFIRM_NOTE)

    # Prise de terre (droite) : descente + 3 traits décroissants
    tx = A4_PORTRAIT_W_MM - PAGE_MARGIN_MM - 10.0
    canvas.setLineWidth(1.0)
    canvas.line(tx * mm, _yp(box_top), tx * mm, _yp(box_top + 8))
    canvas.line((tx - 5) * mm, _yp(box_top + 8), (tx + 5) * mm, _yp(box_top + 8))
    canvas.line((tx - 3.3) * mm, _yp(box_top + 9.6), (tx + 3.3) * mm, _yp(box_top + 9.6))
    canvas.line((tx - 1.6) * mm, _yp(box_top + 11.2), (tx + 1.6) * mm, _yp(box_top + 11.2))
    canvas.setFont("Helvetica", 6)
    canvas.drawCentredString(tx * mm, _yp(box_top + 14.5), "Terre")

    # Barre de répartition
    canvas.setLineWidth(2.0)
    canvas.line(PAGE_MARGIN_MM * mm, _yp(busbar_y_top_mm),
                (A4_PORTRAIT_W_MM - PAGE_MARGIN_MM) * mm, _yp(busbar_y_top_mm))
    canvas.setLineWidth(1.0)


def _draw_departure(canvas, circuit, repere: str, spine_x_mm: float,
                    col_x_mm: float, y_top_mm: float) -> None:
    """Un départ : branche + disjoncteur + repère/calibre/section + picto + label."""
    branch_y = y_top_mm + 3
    dj_x = spine_x_mm + 3
    dj_w, dj_h = 6.0, 5.0
    # Branche depuis l'épine vers le disjoncteur
    canvas.setLineWidth(1.0)
    canvas.line(spine_x_mm * mm, _yp(branch_y), dj_x * mm, _yp(branch_y))
    # Symbole disjoncteur divisionnaire (boîtier + contact)
    canvas.rect(dj_x * mm, _yp(branch_y + dj_h / 2), dj_w * mm, dj_h * mm)
    canvas.line((dj_x + 1) * mm, _yp(branch_y + dj_h / 2 - 1),
                (dj_x + dj_w - 1) * mm, _yp(branch_y - dj_h / 2 + 1))
    # Texte : repère + calibre/courbe + section
    tx = dj_x + dj_w + 2
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(tx * mm, _yp(branch_y - 0.5), repere)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(tx * mm, _yp(branch_y + 3), f"{circuit.breaker_amps}A {DEFAULT_CURVE}")
    canvas.drawString(tx * mm, _yp(branch_y + 6), f"{circuit.cable_section_mm2} mm²")
    # Picto d'usage + label court
    svg_id = resolve_svg_id_for_circuit(circuit)
    _draw_picto(canvas, svg_id, col_x_mm + 3, y_top_mm + 11, 7.0)
    canvas.setFont("Helvetica", 6)
    label = (circuit.label or "")[:22]
    canvas.drawString((col_x_mm + 12) * mm, _yp(y_top_mm + 15), label)


def _draw_id_column(canvas, rcd, id_idx: int, col_x_mm: float, col_w_mm: float,
                    busbar_y_top_mm: float) -> None:
    """Une colonne = symbole ID en tête + peigne de disjoncteurs en dessous."""
    cx = col_x_mm + col_w_mm / 2
    # Descente barre → ID
    canvas.line(cx * mm, _yp(busbar_y_top_mm), cx * mm, _yp(busbar_y_top_mm + 6))
    id_top = busbar_y_top_mm + 6
    id_w, id_h = 26.0, ID_HEADER_H_MM - 6
    id_x = cx - id_w / 2
    # Symbole DDR (boîtier + contact diagonal + tore)
    canvas.setLineWidth(1.2)
    canvas.rect(id_x * mm, _yp(id_top + id_h), id_w * mm, id_h * mm)
    canvas.line((id_x + 4) * mm, _yp(id_top + id_h - 3),
                (id_x + id_w - 4) * mm, _yp(id_top + 3))
    canvas.circle(cx * mm, _yp(id_top + id_h / 2), 1.6 * mm, stroke=1, fill=0)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(cx * mm, _yp(id_top + 4.5), f"ID {id_idx}")
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(cx * mm, _yp(id_top + id_h + 4),
                             f"{rcd.amps}A · Type {rcd.rcd_type} · {rcd.sensitivity_ma} mA")
    # Peigne vertical (épine)
    dep_top = id_top + id_h + 8
    canvas.setLineWidth(1.0)
    if rcd.circuits:
        spine_bottom = dep_top + (len(rcd.circuits) - 1) * DEPARTURE_H_MM + 3
        canvas.line(cx * mm, _yp(id_top + id_h), cx * mm, _yp(spine_bottom))
    for j, circuit in enumerate(rcd.circuits):
        y0 = dep_top + j * DEPARTURE_H_MM
        _draw_departure(canvas, circuit, circuit_repere(id_idx, j + 1),
                        cx, col_x_mm, y0)


def _draw_cartouche(canvas, tableau: Tableau, page_idx: int, total_pages: int) -> None:
    """Bandeau bas : logo batIA + titre + date + page + mention de réserve."""
    margin = PAGE_MARGIN_MM
    band_h = CARTOUCHE_H_MM
    y0 = margin  # bas de bande, mesuré depuis le bas
    canvas.setLineWidth(0.8)
    canvas.rect(margin * mm, y0 * mm, USABLE_W_MM * mm, band_h * mm)
    _draw_batia_logo_cartouche(canvas, margin, y0, 28.0, band_h)
    canvas.line((margin + 28) * mm, y0 * mm, (margin + 28) * mm, (y0 + band_h) * mm)
    tx = margin + 31
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(tx * mm, (y0 + band_h - 5) * mm,
                      f"Schéma unifilaire — Logement {tableau.typology}")
    canvas.setFont("Helvetica", 7)
    canvas.drawString(tx * mm, (y0 + band_h - 9.5) * mm,
                      f"Date : {date.today().isoformat()}   ·   "
                      f"Page {page_idx + 1}/{total_pages}")
    canvas.setFont("Helvetica-Oblique", 6)
    canvas.drawString(tx * mm, (y0 + 2.5) * mm,
                      "Calculé selon NFC 15-100 §10 + règles cabinet. Sections câbles "
                      "indicatives. L'artisan valide la conformité finale.")


def render_schema_unifilaire_pdf(tableau: Tableau) -> bytes:
    """Rend le PDF complet du schéma unifilaire (A4 portrait, multi-pages).

    Une colonne par ID (RCD), IDS_PER_PAGE colonnes par page. AGCP générique +
    terre + barre de répartition rappelés en tête de chaque page ; cartouche en
    pied. Tableau vide → une page minimale valide.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=portrait(A4))
    pages = paginate_rcds(tableau.rcds, per_page=IDS_PER_PAGE) or [[]]
    total_pages = max(len(pages), 1)
    busbar_y = PAGE_MARGIN_MM + HEAD_ZONE_H_MM
    col_w = USABLE_W_MM / IDS_PER_PAGE

    for page_idx, rcds_in_page in enumerate(pages):
        _draw_head(c, busbar_y)
        base_id_idx = page_idx * IDS_PER_PAGE
        for local_idx, rcd in enumerate(rcds_in_page):
            id_idx = base_id_idx + local_idx + 1
            col_x = PAGE_MARGIN_MM + local_idx * col_w
            _draw_id_column(c, rcd, id_idx, col_x, col_w, busbar_y)
        _draw_cartouche(c, tableau, page_idx, total_pages)
        c.showPage()

    c.save()
    return buf.getvalue()
