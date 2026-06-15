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
    lx = x0 + 36
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


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio (bus + ID + départs + terre + pictos +
    localisation). Implémenté en Task 2."""
    pass  # Task 2


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
