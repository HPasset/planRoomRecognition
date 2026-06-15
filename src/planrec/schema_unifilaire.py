"""Renderer du schéma unifilaire — format Hager (A4 paysage, bus horizontal).

Cadre normalisé (repères A-G / 1-14), arrivée AGCP → jeu de barres → ID 30 mA →
disjoncteurs divisionnaires → barre de terre, bande pictogrammes (bibliothèque
batIA) et cartouche (projet / client / puissance / régime / folio).

Module pur : reportlab uniquement, aucun import Streamlit/React/DB. Voir
docs/superpowers/specs/2026-06-15-schema-unifilaire-hager-design.md
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics import renderPDF
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau, RCD
from src.planrec.icon_assets import load_icon_as_drawing, resolve_svg_id_for_circuit
from src.planrec.etiquettes_renderer import _draw_batia_logo_cartouche

# --- AGCP / courbe ---
AGCP_SENSITIVITY_MA = 500
DEFAULT_CURVE = "C"

# --- Dérivations ---
_PUISSANCE_BY_TYPO = {"T1": 6, "T2": 6, "T3": 9, "T4": 12, "T5": 12}
_DB_CALIBRE_BY_KVA = {3: 15, 6: 30, 9: 45, 12: 60, 15: 60, 18: 90}


def derive_puissance_kva(typology: str) -> int:
    """Puissance prévisionnelle par défaut selon la typologie (kVA, monophasé)."""
    return _PUISSANCE_BY_TYPO.get(typology, 9)


def derive_db_calibre(puissance_kva: int) -> int:
    """Calibre du disjoncteur de branchement (A) dérivé de la puissance (kVA)."""
    if puissance_kva in _DB_CALIBRE_BY_KVA:
        return _DB_CALIBRE_BY_KVA[puissance_kva]
    best = min(_DB_CALIBRE_BY_KVA)
    for k in sorted(_DB_CALIBRE_BY_KVA):
        if k <= puissance_kva:
            best = k
    return _DB_CALIBRE_BY_KVA[best]


@dataclass
class CartoucheInfo:
    projet: str
    client_nom: str
    client_ville: str
    puissance_kva: int
    regime_neutre: str
    date_iso: str


def circuit_repere(q_idx: int) -> str:
    """Repère global d'un disjoncteur divisionnaire : 'Q{n}'."""
    return f"Q{q_idx}"


# --- Géométrie page (mm, A4 paysage) ---
PAGE_W_MM = 297.0
PAGE_H_MM = 210.0
FRAME_MARGIN_MM = 8.0
FRAME_LEFT = FRAME_MARGIN_MM
FRAME_RIGHT = PAGE_W_MM - FRAME_MARGIN_MM
FRAME_BOT = FRAME_MARGIN_MM
FRAME_TOP = PAGE_H_MM - FRAME_MARGIN_MM
N_GRID_COLS = 14
GRID_ROWS = "ABCDEFG"
SLOTS_PER_FOLIO = 12

# Zones verticales (y depuis le bas, mm)
MAIN_BUS_Y = 188.0
ID_SYM_Y = 176.0
SEC_BUS_Y = 166.0
Q_SYM_Y = 150.0
PE_Y = 86.0
PICTO_TOP_Y = 78.0
PICTO_SIZE_MM = 9.0
CARTOUCHE_TOP_Y = 44.0

# Zones horizontales (x, mm)
LEGEND_RIGHT = 36.0
SLOTS_LEFT = 38.0


def _paginate_rcds_by_slots(rcds: list[RCD], cap: int = SLOTS_PER_FOLIO) -> list[list[RCD]]:
    """Empaquète des RCD entiers (ID + ses départs) par folio sans dépasser `cap`
    slots, pour qu'un RCD ne soit jamais coupé entre deux folios."""
    folios: list[list[RCD]] = []
    cur: list[RCD] = []
    used = 0
    for rcd in rcds:
        need = 1 + len(rcd.circuits)
        if cur and used + need > cap:
            folios.append(cur)
            cur = []
            used = 0
        cur.append(rcd)
        used += need
    if cur:
        folios.append(cur)
    return folios or [[]]


def _draw_grid_frame(c: Canvas) -> None:
    """Cadre extérieur + repères de grille (colonnes 1-14, lignes A-G)."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.rect(FRAME_LEFT * mm, FRAME_BOT * mm,
           (FRAME_RIGHT - FRAME_LEFT) * mm, (FRAME_TOP - FRAME_BOT) * mm)
    col_w = (FRAME_RIGHT - FRAME_LEFT) / N_GRID_COLS
    c.setFont("Helvetica", 6)
    for i in range(N_GRID_COLS):
        x = FRAME_LEFT + (i + 0.5) * col_w
        c.drawCentredString(x * mm, (FRAME_TOP - 4) * mm, str(i + 1))
        c.drawCentredString(x * mm, (FRAME_BOT + 1.5) * mm, str(i + 1))
        if i > 0:
            gx = (FRAME_LEFT + i * col_w) * mm
            c.setLineWidth(0.2)
            c.line(gx, FRAME_TOP * mm, gx, (FRAME_TOP - 2.5) * mm)
            c.line(gx, FRAME_BOT * mm, gx, (FRAME_BOT + 2.5) * mm)
            c.setLineWidth(1.0)
    row_h = (FRAME_TOP - FRAME_BOT) / len(GRID_ROWS)
    for j, letter in enumerate(GRID_ROWS):
        y = FRAME_TOP - (j + 0.5) * row_h
        c.drawCentredString((FRAME_LEFT + 2) * mm, y * mm, letter)
        c.drawCentredString((FRAME_RIGHT - 2) * mm, y * mm, letter)


def _draw_cartouche(c: Canvas, tableau: Tableau, cartouche: CartoucheInfo,
                    folio_idx: int, total: int) -> None:
    """Bandeau cartouche bas (style Hager) : logo + cases d'info."""
    x0, y0 = FRAME_LEFT, FRAME_BOT
    w = FRAME_RIGHT - FRAME_LEFT
    h = CARTOUCHE_TOP_Y - FRAME_BOT
    c.setLineWidth(0.8)
    c.rect(x0 * mm, y0 * mm, w * mm, h * mm)
    _draw_batia_logo_cartouche(c, x0 + 1, y0 + 1, 34.0, h - 2)
    lx = x0 + LEGEND_RIGHT
    c.line(lx * mm, y0 * mm, lx * mm, (y0 + h) * mm)
    fields = [
        ("Projet", cartouche.projet or "—"),
        ("Client", (cartouche.client_nom or "—") +
                   (f" · {cartouche.client_ville}" if cartouche.client_ville else "")),
        ("Tableau", f"Tableau électrique — {tableau.typology}"),
        ("Date", cartouche.date_iso),
        ("Puissance prévisionnelle", f"{cartouche.puissance_kva} kVA"),
        ("Régime de neutre", cartouche.regime_neutre),
        ("Folio", f"{folio_idx + 1} / {total}"),
    ]
    col_x = [lx + 2, lx + 95, lx + 180]
    for k, (label, value) in enumerate(fields):
        cx = col_x[k % 3]
        row = k // 3
        cy = y0 + h - 7 - row * (h / 3)
        c.setFont("Helvetica", 5.5)
        c.drawString(cx * mm, (cy + 2.5) * mm, label)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx * mm, (cy - 1.5) * mm, str(value)[:38])
    c.setFont("Helvetica-Oblique", 5)
    c.drawString((lx + 2) * mm, (y0 + 1.5) * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. Sections "
                 "indicatives. L'artisan valide la conformité finale.")


def _slot_x(local_slot_idx: int) -> float:
    """Centre x (mm) d'un slot dans la grille de départs."""
    slot_w = (FRAME_RIGHT - SLOTS_LEFT) / SLOTS_PER_FOLIO
    return SLOTS_LEFT + (local_slot_idx + 0.5) * slot_w


def _draw_source(c: Canvas, db_calibre: int) -> None:
    """Alim. BT + disjoncteur de branchement (folio 1), relié à la barre."""
    x = FRAME_LEFT + 16
    top = MAIN_BUS_Y + 12
    c.setLineWidth(1.0)
    c.line(x * mm, top * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.line((x - 1.5) * mm, (MAIN_BUS_Y + 8) * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.line((x + 1.5) * mm, (MAIN_BUS_Y + 8) * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x * mm, (top + 1) * mm, "Alim. BT")
    bw, bh = 11.0, 8.0
    c.setLineWidth(1.1)
    c.rect((x - bw / 2) * mm, (MAIN_BUS_Y - bh / 2) * mm, bw * mm, bh * mm)
    c.line((x - bw / 2 + 2) * mm, (MAIN_BUS_Y + bh / 2 - 2) * mm,
           (x + bw / 2 - 2) * mm, (MAIN_BUS_Y - bh / 2 + 2) * mm)
    c.setFont("Helvetica-Bold", 6)
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y + 2) * mm, "DB1")
    c.setFont("Helvetica", 5.5)
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y - 1.5) * mm, f"{db_calibre} A")
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y - 4.5) * mm,
                 f"{AGCP_SENSITIVITY_MA} mA · S")
    c.setLineWidth(1.4)
    c.line((x + bw / 2) * mm, MAIN_BUS_Y * mm, SLOTS_LEFT * mm, MAIN_BUS_Y * mm)


def _draw_id_symbol(c: Canvas, x: float, rcd: RCD, id_idx: int) -> None:
    w, h = 12.0, 8.0
    c.setLineWidth(1.1)
    c.rect((x - w / 2) * mm, (ID_SYM_Y - h / 2) * mm, w * mm, h * mm)
    c.line((x - w / 2 + 2) * mm, (ID_SYM_Y + h / 2 - 2) * mm,
           (x + w / 2 - 2) * mm, (ID_SYM_Y - h / 2 + 2) * mm)
    c.circle(x * mm, ID_SYM_Y * mm, 1.4 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x * mm, (ID_SYM_Y + h / 2 + 2) * mm, f"ID{id_idx}")
    c.setFont("Helvetica", 5)
    c.drawCentredString(x * mm, (ID_SYM_Y - h / 2 - 3) * mm, f"{rcd.amps}A 30mA")
    c.drawCentredString(x * mm, (ID_SYM_Y - h / 2 - 6) * mm, f"Type {rcd.rcd_type}")


def _draw_q_symbol(c: Canvas, x: float, circ, q_idx: int) -> None:
    w, h = 7.0, 6.0
    c.setLineWidth(1.0)
    c.rect((x - w / 2) * mm, (Q_SYM_Y - h / 2) * mm, w * mm, h * mm)
    c.line((x - w / 2 + 1) * mm, (Q_SYM_Y + h / 2 - 1) * mm,
           (x + w / 2 - 1) * mm, (Q_SYM_Y - h / 2 + 1) * mm)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x * mm, (Q_SYM_Y + h / 2 + 5) * mm, circuit_repere(q_idx))
    c.setFont("Helvetica", 5)
    c.drawCentredString(x * mm, (Q_SYM_Y + h / 2 + 1.5) * mm,
                        f"{DEFAULT_CURVE} {circ.breaker_amps}A")
    c.drawCentredString(x * mm, (Q_SYM_Y - h / 2 - 3) * mm, "L1,N")


def _draw_earth_drop(c: Canvas, x: float, y: float) -> None:
    c.setStrokeColor(colors.green)
    c.setLineWidth(0.8)
    c.line((x - 2) * mm, y * mm, (x + 2) * mm, y * mm)
    c.line((x - 1.3) * mm, (y - 0.9) * mm, (x + 1.3) * mm, (y - 0.9) * mm)
    c.line((x - 0.6) * mm, (y - 1.8) * mm, (x + 0.6) * mm, (y - 1.8) * mm)
    c.setStrokeColor(colors.black)


def _draw_picto_slot(c: Canvas, circ, x: float) -> None:
    svg_id = resolve_svg_id_for_circuit(circ)
    try:
        d = load_icon_as_drawing(svg_id)
    except FileNotFoundError:
        return
    ref = max(d.width, d.height) or 40.0
    s = (PICTO_SIZE_MM * mm) / ref
    d.width *= s
    d.height *= s
    d.scale(s, s)
    renderPDF.draw(d, c, (x - PICTO_SIZE_MM / 2) * mm, (PICTO_TOP_Y - PICTO_SIZE_MM) * mm)


def _draw_localisation(c: Canvas, circ, x: float) -> None:
    c.saveState()
    c.translate(x * mm, (CARTOUCHE_TOP_Y + 2) * mm)
    c.rotate(90)
    c.setFont("Helvetica", 5.5)
    c.drawString(0, -1.5 * mm, (circ.label or "")[:22])
    c.restoreState()


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio : bus principal, source/continuation, ID +
    bus secondaires, départs Q, barre de terre, pictos, localisation."""
    # Barre principale
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.4)
    c.line(SLOTS_LEFT * mm, MAIN_BUS_Y * mm, FRAME_RIGHT * mm, MAIN_BUS_Y * mm)

    # Barre de terre PE (verte, pointillés)
    c.setStrokeColor(colors.green)
    c.setLineWidth(1.2)
    c.setDash(4, 2)
    c.line(SLOTS_LEFT * mm, PE_Y * mm, FRAME_RIGHT * mm, PE_Y * mm)
    c.setDash()
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.green)
    c.drawRightString((SLOTS_LEFT - 1) * mm, (PE_Y + 1) * mm, "PE1")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # Source (folio 1) ou continuation
    if is_first:
        _draw_source(c, db_calibre)
    else:
        c.setFont("Helvetica-Oblique", 6)
        c.drawString(SLOTS_LEFT * mm, (MAIN_BUS_Y + 2) * mm,
                     f"suite du folio {folio_idx}")
    if folio_idx < total - 1:
        c.setFont("Helvetica-Oblique", 6)
        c.drawRightString((FRAME_RIGHT - 1) * mm, (MAIN_BUS_Y + 2) * mm,
                          f"suite folio {folio_idx + 2}")

    # Légendes colonne gauche
    c.saveState()
    c.translate((FRAME_LEFT + 5) * mm, (CARTOUCHE_TOP_Y + 4) * mm)
    c.rotate(90)
    c.setFont("Helvetica", 6)
    c.drawString(0, 0, "Application / Localisation des départs")
    c.restoreState()
    c.setFont("Helvetica", 6)
    c.drawString((FRAME_LEFT + 2) * mm, (PICTO_TOP_Y - PICTO_SIZE_MM / 2) * mm,
                 "Pictogramme")

    # Slots : ID puis ses départs
    local = 0
    id_idx = id_offset
    q_idx = q_offset
    for rcd in folio_rcds:
        id_idx += 1
        id_x = _slot_x(local)
        c.setLineWidth(1.0)
        c.line(id_x * mm, MAIN_BUS_Y * mm, id_x * mm, (ID_SYM_Y + 4) * mm)
        _draw_id_symbol(c, id_x, rcd, id_idx)
        local += 1
        n_q = len(rcd.circuits)
        if n_q:
            last_q_x = _slot_x(local + n_q - 1)
            c.setLineWidth(1.2)
            c.line(id_x * mm, (ID_SYM_Y - 4) * mm, id_x * mm, SEC_BUS_Y * mm)
            c.line(id_x * mm, SEC_BUS_Y * mm, last_q_x * mm, SEC_BUS_Y * mm)
        for circ in rcd.circuits:
            q_idx += 1
            qx = _slot_x(local)
            c.setLineWidth(1.0)
            c.line(qx * mm, SEC_BUS_Y * mm, qx * mm, (Q_SYM_Y + 4) * mm)
            _draw_q_symbol(c, qx, circ, q_idx)
            c.line(qx * mm, (Q_SYM_Y - 4) * mm, qx * mm, PE_Y * mm)
            _draw_earth_drop(c, qx, PE_Y)
            _draw_picto_slot(c, circ, qx)
            _draw_localisation(c, circ, qx)
            local += 1


def render_schema_unifilaire_pdf(tableau: Tableau, cartouche: CartoucheInfo) -> bytes:
    """Rend le PDF du schéma unifilaire (format Hager paysage, multi-folios)."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=landscape(A4))
    folios = _paginate_rcds_by_slots(tableau.rcds)
    total = len(folios)
    db_calibre = derive_db_calibre(cartouche.puissance_kva)
    id_offset = 0
    q_offset = 0
    for folio_idx, folio_rcds in enumerate(folios):
        _draw_grid_frame(c)
        _draw_folio_content(c, folio_rcds, folio_idx == 0, folio_idx, total,
                            id_offset, q_offset, db_calibre)
        _draw_cartouche(c, tableau, cartouche, folio_idx, total)
        c.showPage()
        id_offset += len(folio_rcds)
        q_offset += sum(len(r.circuits) for r in folio_rcds)
    c.save()
    return buf.getvalue()
