"""Renderer du schéma unifilaire — format Hager (A4 paysage, bus horizontal).

Cadre normalisé à double bordure (repères A-G / 1-14 dans la marge), arrivée
AGCP → jeu de barres → ID 30 mA → disjoncteurs divisionnaires → barre de terre,
bande pictogrammes (bibliothèque batIA) et cartouche en cellules.

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
# Bordure extérieure
FRAME_LEFT = 6.0
FRAME_RIGHT = PAGE_W_MM - 6.0      # 291
FRAME_BOT = 6.0
FRAME_TOP = PAGE_H_MM - 6.0        # 204
# Bordure intérieure (les repères de grille vivent dans la bande entre les deux)
CONTENT_MARGIN = 6.0
CONTENT_LEFT = FRAME_LEFT + CONTENT_MARGIN      # 12
CONTENT_RIGHT = FRAME_RIGHT - CONTENT_MARGIN    # 285
CONTENT_BOT = FRAME_BOT + CONTENT_MARGIN        # 12
CONTENT_TOP = FRAME_TOP - CONTENT_MARGIN        # 198
N_GRID_COLS = 14
GRID_ROWS = "ABCDEFG"
SLOTS_PER_FOLIO = 12

# Zones verticales (y depuis le bas, mm)
MAIN_BUS_Y = 185.0
ID_SYM_Y = 173.0
SEC_BUS_Y = 164.0
Q_SYM_Y = 148.0
PE_Y = 92.0
PICTO_TOP_Y = 84.0
PICTO_SIZE_MM = 9.0
LOCAL_LABEL_BASE_Y = 50.0          # base des libellés verticaux de localisation
CARTOUCHE_TOP_Y = 48.0

# Zones horizontales (x, mm)
LEGEND_RIGHT = 42.0
SLOTS_LEFT = 42.0


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
    """Double cadre + repères de grille (colonnes 1-14, lignes A-G) dans la
    bande entre bordure extérieure et intérieure (façon plan normalisé)."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.rect(FRAME_LEFT * mm, FRAME_BOT * mm,
           (FRAME_RIGHT - FRAME_LEFT) * mm, (FRAME_TOP - FRAME_BOT) * mm)
    c.setLineWidth(0.6)
    c.rect(CONTENT_LEFT * mm, CONTENT_BOT * mm,
           (CONTENT_RIGHT - CONTENT_LEFT) * mm, (CONTENT_TOP - CONTENT_BOT) * mm)

    # Repères colonnes 1..14 (haut et bas, dans la bande)
    col_w = (CONTENT_RIGHT - CONTENT_LEFT) / N_GRID_COLS
    y_top = (FRAME_TOP + CONTENT_TOP) / 2
    y_bot = (FRAME_BOT + CONTENT_BOT) / 2
    c.setFont("Helvetica", 6)
    for i in range(N_GRID_COLS):
        x = CONTENT_LEFT + (i + 0.5) * col_w
        c.drawCentredString(x * mm, (y_top - 1) * mm, str(i + 1))
        c.drawCentredString(x * mm, (y_bot - 1) * mm, str(i + 1))
        if i > 0:
            gx = (CONTENT_LEFT + i * col_w) * mm
            c.setLineWidth(0.3)
            c.line(gx, FRAME_TOP * mm, gx, CONTENT_TOP * mm)
            c.line(gx, FRAME_BOT * mm, gx, CONTENT_BOT * mm)

    # Repères lignes A..G (gauche et droite, dans la bande)
    row_h = (CONTENT_TOP - CONTENT_BOT) / len(GRID_ROWS)
    x_left = (FRAME_LEFT + CONTENT_LEFT) / 2
    x_right = (FRAME_RIGHT + CONTENT_RIGHT) / 2
    for j, letter in enumerate(GRID_ROWS):
        y = CONTENT_TOP - (j + 0.5) * row_h
        c.drawCentredString(x_left * mm, (y - 1) * mm, letter)
        c.drawCentredString(x_right * mm, (y - 1) * mm, letter)
        if j > 0:
            gy = (CONTENT_TOP - j * row_h) * mm
            c.setLineWidth(0.3)
            c.line(FRAME_LEFT * mm, gy, CONTENT_LEFT * mm, gy)
            c.line(CONTENT_RIGHT * mm, gy, FRAME_RIGHT * mm, gy)


def _draw_cartouche(c: Canvas, tableau: Tableau, cartouche: CartoucheInfo,
                    folio_idx: int, total: int) -> None:
    """Cartouche bas en cellules bordées (façon Hager) : logo + tableau de
    champs + bandeau de réserve."""
    x0 = CONTENT_LEFT
    y0 = CONTENT_BOT
    w = CONTENT_RIGHT - CONTENT_LEFT
    h = CARTOUCHE_TOP_Y - CONTENT_BOT
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.8)
    c.rect(x0 * mm, y0 * mm, w * mm, h * mm)

    # Cellule logo (gauche)
    logo_w = 34.0
    c.line((x0 + logo_w) * mm, y0 * mm, (x0 + logo_w) * mm, (y0 + h) * mm)
    _draw_batia_logo_cartouche(c, x0 + 1, y0 + 1, logo_w - 2, h - 2)

    # Bandeau de réserve (pleine largeur, en bas de la zone champs)
    res_h = 5.0
    tbl_x = x0 + logo_w
    tbl_w = w - logo_w
    c.setLineWidth(0.4)
    c.line(tbl_x * mm, (y0 + res_h) * mm, (x0 + w) * mm, (y0 + res_h) * mm)
    c.setFont("Helvetica-Oblique", 5)
    c.drawString((tbl_x + 2) * mm, (y0 + 1.7) * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. Sections "
                 "indicatives. L'artisan valide la conformité finale.")

    # Tableau de champs (cellules bordées), 4 colonnes × 2 lignes
    tbl_y = y0 + res_h
    tbl_h = h - res_h
    ncol, nrow = 4, 2
    cw = tbl_w / ncol
    ch = tbl_h / nrow
    fields = [
        ("Projet", cartouche.projet or "—"),
        ("Client", (cartouche.client_nom or "—") +
                   (f" · {cartouche.client_ville}" if cartouche.client_ville else "")),
        ("Puissance prévisionnelle", f"{cartouche.puissance_kva} kVA"),
        ("Date", cartouche.date_iso),
        ("Tableau", f"Tableau électrique — {tableau.typology}"),
        ("Régime de neutre", cartouche.regime_neutre),
        ("Folio", f"{folio_idx + 1} / {total}"),
        ("", ""),
    ]
    for k, (label, value) in enumerate(fields):
        col = k % ncol
        row = k // ncol
        cx = tbl_x + col * cw
        cyt = tbl_y + tbl_h - row * ch     # haut de la cellule
        cyb = cyt - ch                      # bas de la cellule
        c.setLineWidth(0.3)
        c.rect(cx * mm, cyb * mm, cw * mm, ch * mm)
        if label:
            c.setFont("Helvetica", 5)
            c.drawString((cx + 1.5) * mm, (cyt - 3) * mm, label)
            c.setFont("Helvetica-Bold", 7.5)
            c.drawString((cx + 1.5) * mm, (cyb + 2.5) * mm, str(value)[:42])


def _slot_x(local_slot_idx: int) -> float:
    """Centre x (mm) d'un slot dans la grille de départs."""
    slot_w = (CONTENT_RIGHT - SLOTS_LEFT) / SLOTS_PER_FOLIO
    return SLOTS_LEFT + (local_slot_idx + 0.5) * slot_w


def _draw_breaker_glyph(c: Canvas, x: float, yc: float, with_cross: bool = True) -> None:
    """Symbole disjoncteur unipolaire EN 60617 (contact-levier ouvert + croix),
    dessiné sur un conducteur vertical, centré en (x, yc), hauteur ~6 mm.
    L'appelant raccorde le fil jusqu'à yc+3 (haut) et depuis yc-3 (bas)."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    # Contact fixe (stub haut) + pivot (bas)
    c.line(x * mm, (yc + 3) * mm, x * mm, (yc + 2.2) * mm)
    c.circle(x * mm, (yc - 3) * mm, 0.5 * mm, stroke=1, fill=1)
    # Levier mobile (contact ouvert), du pivot vers le haut-droite
    c.line(x * mm, (yc - 3) * mm, (x + 2.8) * mm, (yc + 2.4) * mm)
    if with_cross:
        c.line((x - 1) * mm, (yc + 3.2) * mm, (x + 1) * mm, (yc + 5.2) * mm)
        c.line((x - 1) * mm, (yc + 5.2) * mm, (x + 1) * mm, (yc + 3.2) * mm)


def _draw_diff_glyph(c: Canvas, x: float, yc: float) -> None:
    """Symbole interrupteur différentiel (DDR) EN 60617 : boîtier + tore (cercle)
    et contact diagonal, centré en (x, yc), hauteur ~7 mm. L'appelant raccorde le
    fil jusqu'à yc+3.5 (haut) et depuis yc-3.5 (bas)."""
    w, h = 9.0, 7.0
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.rect((x - w / 2) * mm, (yc - h / 2) * mm, w * mm, h * mm)
    c.circle(x * mm, yc * mm, 1.7 * mm, stroke=1, fill=0)
    c.line((x - w / 2 + 1.4) * mm, (yc - h / 2 + 1.4) * mm,
           (x + w / 2 - 1.4) * mm, (yc + h / 2 - 1.4) * mm)


def _draw_source(c: Canvas, db_calibre: int) -> None:
    """Alim. BT (flèche) + disjoncteur de branchement DB1, relié à la barre."""
    x = CONTENT_LEFT + 14
    db_yc = MAIN_BUS_Y + 7
    # Flèche Alim. BT au-dessus du DB
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    top = db_yc + 8
    c.line(x * mm, top * mm, x * mm, (db_yc + 3.2) * mm)
    c.line((x - 1.5) * mm, (db_yc + 5) * mm, x * mm, (db_yc + 3.2) * mm)
    c.line((x + 1.5) * mm, (db_yc + 5) * mm, x * mm, (db_yc + 3.2) * mm)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x * mm, (top + 1) * mm, "Alim. BT")
    # Symbole disjoncteur de branchement
    _draw_breaker_glyph(c, x, db_yc, with_cross=True)
    # Fil DB → barre principale
    c.setLineWidth(1.2)
    c.line(x * mm, (db_yc - 3) * mm, x * mm, MAIN_BUS_Y * mm)
    c.setLineWidth(1.4)
    c.line(x * mm, MAIN_BUS_Y * mm, SLOTS_LEFT * mm, MAIN_BUS_Y * mm)
    # Annotations à droite du symbole (jamais sur le fil)
    tx = x + 4
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(tx * mm, (db_yc + 2) * mm, "DB1")
    c.setFont("Helvetica", 5.5)
    c.drawString(tx * mm, (db_yc - 1.5) * mm, f"{db_calibre} A")
    c.drawString(tx * mm, (db_yc - 4.5) * mm, f"{AGCP_SENSITIVITY_MA} mA · S")


def _draw_id(c: Canvas, x: float, rcd: RCD, id_idx: int) -> None:
    """Départ ID : symbole DDR + annotations en colonne à droite."""
    _draw_diff_glyph(c, x, ID_SYM_Y)
    tx = x + 6
    c.setFont("Helvetica-Bold", 6)
    c.drawString(tx * mm, (ID_SYM_Y + 2) * mm, f"ID{id_idx}")
    c.setFont("Helvetica", 5)
    c.drawString(tx * mm, (ID_SYM_Y - 1.5) * mm, f"{rcd.amps}A {rcd.sensitivity_ma}mA")
    c.drawString(tx * mm, (ID_SYM_Y - 4.5) * mm, f"Type {rcd.rcd_type}")


def _draw_q(c: Canvas, x: float, circ, q_idx: int) -> None:
    """Départ Q : symbole disjoncteur + annotations en colonne à droite + L1,N."""
    _draw_breaker_glyph(c, x, Q_SYM_Y, with_cross=True)
    tx = x + 4
    c.setFont("Helvetica-Bold", 6)
    c.drawString(tx * mm, (Q_SYM_Y + 1.5) * mm, circuit_repere(q_idx))
    c.setFont("Helvetica", 5)
    c.drawString(tx * mm, (Q_SYM_Y - 2) * mm, f"{DEFAULT_CURVE} {circ.breaker_amps}A")
    # Repère de phase près du haut de la descente
    c.setFont("Helvetica", 4.5)
    c.drawString((x + 1.5) * mm, (SEC_BUS_Y - 3) * mm, "L1,N")


def _draw_earth_drop(c: Canvas, x: float, y: float) -> None:
    """Symbole de mise à la terre (3 traits décroissants) sous un départ."""
    c.setStrokeColor(colors.green)
    c.setLineWidth(0.8)
    c.line((x - 2) * mm, y * mm, (x + 2) * mm, y * mm)
    c.line((x - 1.3) * mm, (y - 0.9) * mm, (x + 1.3) * mm, (y - 0.9) * mm)
    c.line((x - 0.6) * mm, (y - 1.8) * mm, (x + 0.6) * mm, (y - 1.8) * mm)
    c.setStrokeColor(colors.black)


def _draw_picto_slot(c: Canvas, x: float, circ) -> None:
    """Picto d'usage (bibliothèque batIA) dans la bande Pictogramme."""
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


def _draw_localisation(c: Canvas, x: float, circ) -> None:
    """Désignation du départ en texte vertical (bande Localisation)."""
    c.saveState()
    c.translate(x * mm, LOCAL_LABEL_BASE_Y * mm)
    c.rotate(90)
    c.setFont("Helvetica", 5.5)
    c.drawString(0, -1.5 * mm, (circ.label or "")[:16])
    c.restoreState()


def _draw_band_legends(c: Canvas) -> None:
    """Libellés de la colonne gauche : Pictogramme + Application/Localisation."""
    c.setStrokeColor(colors.black)
    c.setFont("Helvetica", 5.5)
    c.drawString((CONTENT_LEFT + 1.5) * mm, (PICTO_TOP_Y - PICTO_SIZE_MM / 2) * mm,
                 "Pictogramme")
    for i, line in enumerate(("Application", "Localisation", "des départs")):
        c.drawString((CONTENT_LEFT + 1.5) * mm, (66 - i * 3.4) * mm, line)


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio : bus principal, source/continuation, ID +
    bus secondaires, départs Q, barre de terre, pictos, localisation."""
    # Barre principale
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.4)
    c.line(SLOTS_LEFT * mm, MAIN_BUS_Y * mm, CONTENT_RIGHT * mm, MAIN_BUS_Y * mm)

    # Barre de terre PE (verte, trait mixte tiret-point)
    c.setStrokeColor(colors.green)
    c.setLineWidth(1.2)
    c.setDash([5, 2, 1, 2], 0)
    c.line(SLOTS_LEFT * mm, PE_Y * mm, CONTENT_RIGHT * mm, PE_Y * mm)
    c.setDash([], 0)
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
        c.drawRightString((CONTENT_RIGHT - 1) * mm, (MAIN_BUS_Y + 2) * mm,
                          f"suite folio {folio_idx + 2}")

    _draw_band_legends(c)

    # Slots : ID puis ses départs
    local = 0
    id_idx = id_offset
    q_idx = q_offset
    for rcd in folio_rcds:
        id_idx += 1
        id_x = _slot_x(local)
        # Descente barre principale → ID (gap pour le symbole)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.line(id_x * mm, MAIN_BUS_Y * mm, id_x * mm, (ID_SYM_Y + 3.5) * mm)
        _draw_id(c, id_x, rcd, id_idx)
        c.setLineWidth(1.0)
        c.line(id_x * mm, (ID_SYM_Y - 3.5) * mm, id_x * mm, SEC_BUS_Y * mm)
        local += 1
        n_q = len(rcd.circuits)
        if n_q:
            last_q_x = _slot_x(local + n_q - 1)
            c.setLineWidth(1.2)
            c.line(id_x * mm, SEC_BUS_Y * mm, last_q_x * mm, SEC_BUS_Y * mm)
        for circ in rcd.circuits:
            q_idx += 1
            qx = _slot_x(local)
            # Descente bus secondaire → Q (gap) → terre
            c.setStrokeColor(colors.black)
            c.setLineWidth(1.0)
            c.line(qx * mm, SEC_BUS_Y * mm, qx * mm, (Q_SYM_Y + 3) * mm)
            _draw_q(c, qx, circ, q_idx)
            c.setLineWidth(1.0)
            c.line(qx * mm, (Q_SYM_Y - 3) * mm, qx * mm, PE_Y * mm)
            _draw_earth_drop(c, qx, PE_Y)
            _draw_picto_slot(c, qx, circ)
            _draw_localisation(c, qx, circ)
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
