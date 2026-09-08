"""Renderer du schéma unifilaire — format Hager (A4 paysage, bus horizontal).

Cadre normalisé à double bordure (repères A-G / 1-14 dans la marge), arrivée
AGCP → jeu de barres JB1 → ID 30 mA → disjoncteurs divisionnaires → barre de
terre PE, bandes Pictogramme + Localisation encadrées (pictos violet batIA) et
cartouche en cellules. Symboles d'appareillage EN 60617.

Module pur : reportlab uniquement, aucun import Streamlit/React/DB. Voir
docs/superpowers/specs/2026-06-15-schema-unifilaire-hager-design.md
"""
from __future__ import annotations

import bisect
import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics import renderPDF
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau, RCD
from src.planrec.icon_assets import load_icon_as_drawing, resolve_svg_id_for_circuit
from src.planrec.etiquettes_renderer import _draw_batia_logo_cartouche

# --- AGCP / courbe / couleur ---
AGCP_SENSITIVITY_MA = 500
DEFAULT_CURVE = "C"
PICTO_PURPLE = "#8217fd"           # violet batIA (charte logo)

# --- Dérivations ---
_PUISSANCE_BY_TYPO = {"T1": 6, "T2": 6, "T3": 9, "T4": 12, "T5": 12}
_DB_CALIBRE_BY_KVA = {3: 15, 6: 30, 9: 45, 12: 60, 15: 60, 18: 90}
_DB_CALIBRE_KVA_SORTED = sorted(_DB_CALIBRE_BY_KVA)


def derive_puissance_kva(typology: str) -> int:
    """Puissance prévisionnelle par défaut selon la typologie (kVA, monophasé)."""
    return _PUISSANCE_BY_TYPO.get(typology, 9)


def derive_db_calibre(puissance_kva: int) -> int:
    """Calibre du disjoncteur de branchement (A) dérivé de la puissance (kVA)."""
    idx = max(0, bisect.bisect_right(_DB_CALIBRE_KVA_SORTED, puissance_kva) - 1)
    return _DB_CALIBRE_BY_KVA[_DB_CALIBRE_KVA_SORTED[idx]]


@dataclass
class CartoucheInfo:
    projet: str
    client_nom: str
    client_ville: str
    puissance_kva: int
    regime_neutre: str
    date_iso: str


# --- Géométrie page (mm, A4 paysage) ---
PAGE_W_MM = 297.0
PAGE_H_MM = 210.0
FRAME_LEFT = 6.0
FRAME_RIGHT = PAGE_W_MM - 6.0      # 291
FRAME_BOT = 6.0
FRAME_TOP = PAGE_H_MM - 6.0        # 204
CONTENT_MARGIN = 6.0
CONTENT_LEFT = FRAME_LEFT + CONTENT_MARGIN      # 12
CONTENT_RIGHT = FRAME_RIGHT - CONTENT_MARGIN    # 285
CONTENT_BOT = FRAME_BOT + CONTENT_MARGIN        # 12
CONTENT_TOP = FRAME_TOP - CONTENT_MARGIN        # 198
N_GRID_COLS = 14
GRID_ROWS = "ABCDEFG"
SLOTS_PER_FOLIO = 12

# Zones verticales (y depuis le bas, mm)
MAIN_BUS_Y = 180.0
ID_SYM_Y = 169.0
SEC_BUS_Y = 158.0
Q_SYM_Y = 144.0
PE_Y = 95.0
PICTO_BAND_TOP = 88.0
PICTO_BAND_BOT = 74.0
PICTO_SIZE_MM = 9.0
LOCAL_LABEL_BASE_Y = 50.0
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

    logo_w = 34.0
    c.line((x0 + logo_w) * mm, y0 * mm, (x0 + logo_w) * mm, (y0 + h) * mm)
    _draw_batia_logo_cartouche(c, x0 + 1, y0 + 1, logo_w - 2, h - 2)

    res_h = 5.0
    tbl_x = x0 + logo_w
    tbl_w = w - logo_w
    c.setLineWidth(0.4)
    c.line(tbl_x * mm, (y0 + res_h) * mm, (x0 + w) * mm, (y0 + res_h) * mm)
    c.setFont("Helvetica-Oblique", 5)
    c.drawString((tbl_x + 2) * mm, (y0 + 1.7) * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. Sections "
                 "indicatives. L'artisan valide la conformité finale.")

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
        cyt = tbl_y + tbl_h - row * ch
        cyb = cyt - ch
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


# --- Symboles d'appareillage EN 60617 (SVG normalisés, assets/icons/) ---
Q_SYM_H = 9.0                      # hauteur de rendu du symbole disjoncteur (mm)
DIFF_SYM_H = 14.0                  # hauteur de rendu des symboles différentiels (mm)


def _draw_symbol_svg(c: Canvas, svg_id: str, x: float, yc: float, height_mm: float) -> None:
    """Rend un symbole d'appareillage EN 60617 (SVG carré 40×40) centré en
    (x, yc), à `height_mm` de haut. Le SVG porte son propre conducteur vertical
    bord à bord : l'appelant raccorde les fils à yc ± height_mm/2."""
    d = load_icon_as_drawing(svg_id)
    ref = max(d.width, d.height) or 40.0
    s = (height_mm * mm) / ref
    d.width *= s
    d.height *= s
    d.scale(s, s)
    renderPDF.draw(d, c, (x - height_mm / 2) * mm, (yc - height_mm / 2) * mm)


def _draw_q_glyph(c: Canvas, x: float, yc: float) -> None:
    """Disjoncteur unipolaire EN 60617. Gap appelant : yc ± Q_SYM_H/2."""
    _draw_symbol_svg(c, "sym_disjoncteur", x, yc, Q_SYM_H)


def _draw_diff_glyph(c: Canvas, x: float, yc: float, asterisk: bool,
                     height_mm: float = DIFF_SYM_H) -> None:
    """Appareil différentiel EN 60617. `asterisk` = disjoncteur de branchement
    diff. sélectif (DB) ; sinon interrupteur différentiel (ID). Gap appelant :
    yc ± height_mm/2."""
    svg_id = "sym_disjoncteur_branchement" if asterisk else "sym_interrupteur_differentiel"
    _draw_symbol_svg(c, svg_id, x, yc, height_mm)


def _draw_source(c: Canvas, db_calibre: int) -> None:
    """Alim. BT (flèche) + disjoncteur de branchement DB1 (diff. sélectif),
    relié à la barre JB1."""
    x = CONTENT_LEFT + 14
    db_h = 11.0
    db_yc = MAIN_BUS_Y + db_h / 2     # bas du symbole posé sur la barre JB1
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    top = db_yc + db_h / 2 + 3
    c.line(x * mm, top * mm, x * mm, (db_yc + db_h / 2 + 0.2) * mm)
    c.line((x - 1.5) * mm, (db_yc + db_h / 2 + 2) * mm, x * mm, (db_yc + db_h / 2 + 0.2) * mm)
    c.line((x + 1.5) * mm, (db_yc + db_h / 2 + 2) * mm, x * mm, (db_yc + db_h / 2 + 0.2) * mm)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x * mm, (top + 1) * mm, "Alim. BT")
    _draw_diff_glyph(c, x, db_yc, asterisk=True, height_mm=db_h)
    c.setLineWidth(1.2)
    c.line(x * mm, (db_yc - db_h / 2) * mm, x * mm, MAIN_BUS_Y * mm)
    c.setLineWidth(1.4)
    c.line(x * mm, MAIN_BUS_Y * mm, SLOTS_LEFT * mm, MAIN_BUS_Y * mm)
    tx = x + 5
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(tx * mm, (db_yc + 4) * mm, "DB1")
    c.setFont("Helvetica", 5.5)
    c.drawString(tx * mm, (db_yc + 0.5) * mm, f"{db_calibre} A")
    c.drawString(tx * mm, (db_yc - 3) * mm, f"{AGCP_SENSITIVITY_MA} mA · S")


def _draw_id(c: Canvas, x: float, rcd: RCD, id_idx: int) -> None:
    """Départ ID : symbole interrupteur différentiel + annotations à droite."""
    _draw_diff_glyph(c, x, ID_SYM_Y, asterisk=False)
    tx = x + 6
    c.setFont("Helvetica-Bold", 6)
    c.drawString(tx * mm, (ID_SYM_Y + 3) * mm, f"ID{id_idx}")
    c.setFont("Helvetica", 5)
    c.drawString(tx * mm, (ID_SYM_Y - 0.5) * mm, f"{rcd.amps}A {rcd.sensitivity_ma}mA")
    c.drawString(tx * mm, (ID_SYM_Y - 3.5) * mm, f"Type {rcd.rcd_type}")


def _draw_q(c: Canvas, x: float, circ, q_idx: int) -> None:
    """Départ Q : symbole disjoncteur + annotations à droite + L1,N."""
    _draw_q_glyph(c, x, Q_SYM_Y)
    tx = x + 4
    c.setFont("Helvetica-Bold", 6)
    c.drawString(tx * mm, (Q_SYM_Y + 1.5) * mm, f"Q{q_idx}")
    c.setFont("Helvetica", 5)
    c.drawString(tx * mm, (Q_SYM_Y - 2) * mm, f"{DEFAULT_CURVE} {circ.breaker_amps}A")
    c.setFont("Helvetica", 4.5)
    c.drawString((x + 1.5) * mm, (SEC_BUS_Y - 3) * mm, "L1,N")


def _draw_down_arrow(c: Canvas, x: float, y_tip: float, color) -> None:
    """Flèche pleine-pointe (triangle creux) vers le bas, pointe en (x, y_tip)."""
    c.setStrokeColor(color)
    c.setLineWidth(1.0)
    c.line((x - 1.5) * mm, (y_tip + 3) * mm, x * mm, y_tip * mm)
    c.line((x + 1.5) * mm, (y_tip + 3) * mm, x * mm, y_tip * mm)
    c.line((x - 1.5) * mm, (y_tip + 3) * mm, (x + 1.5) * mm, (y_tip + 3) * mm)
    c.setStrokeColor(colors.black)


def _draw_pe_earth_tap(c: Canvas, x: float) -> None:
    """Prise de terre d'un départ : dérivation verte depuis la barre PE (point de
    jonction) descendant vers l'équipement, terminée par une flèche verte."""
    c.setStrokeColor(colors.green)
    c.setLineWidth(1.0)
    c.circle(x * mm, PE_Y * mm, 0.5 * mm, stroke=1, fill=1)
    c.line(x * mm, PE_Y * mm, x * mm, (PE_Y - 3) * mm)
    _draw_down_arrow(c, x, PE_Y - 6, colors.green)


def _draw_picto_slot(c: Canvas, x: float, circ) -> None:
    """Picto d'usage (bibliothèque batIA, violet) dans la bande Pictogramme."""
    svg_id = resolve_svg_id_for_circuit(circ)
    try:
        d = load_icon_as_drawing(svg_id, PICTO_PURPLE)
    except FileNotFoundError:
        return
    ref = max(d.width, d.height) or 40.0
    s = (PICTO_SIZE_MM * mm) / ref
    d.width *= s
    d.height *= s
    d.scale(s, s)
    y_bottom = PICTO_BAND_BOT + (PICTO_BAND_TOP - PICTO_BAND_BOT - PICTO_SIZE_MM) / 2
    renderPDF.draw(d, c, (x - PICTO_SIZE_MM / 2) * mm, y_bottom * mm)


LOCAL_LINE_STEP_MM = 2.6
LOCAL_TOP_Y = PICTO_BAND_BOT - 3.0


def _fit_text(text: str, max_w: float, font: str, size: float) -> str:
    while text and stringWidth(text, font, size) > max_w:
        text = text[:-1]
    return text


def _localisation_lines(label: str) -> list[str]:
    """Découpe un label compact « PC CH1 CH2 (×8) » en en-tête « PC (×8) »
    puis un code pièce par ligne. Un label sans compteur (« Lave-linge »)
    reste une seule ligne : même vocabulaire que les étiquettes."""
    tokens = (label or "").split()
    if len(tokens) >= 2 and tokens[-1].startswith("(×"):
        return [f"{tokens[0]} {tokens[-1]}", *tokens[1:-1]]
    return [label or ""]


def _draw_localisation(c: Canvas, x: float, circ) -> None:
    """Désignation du départ (bande Localisation) : en-tête du circuit puis
    le code de chaque pièce, un par ligne, à l'horizontale, centrés sous le
    départ. Source unique : Circuit.label (identique aux étiquettes)."""
    lines = _localisation_lines(circ.label)
    max_w = ((CONTENT_RIGHT - SLOTS_LEFT) / SLOTS_PER_FOLIO - 1.5) * mm
    max_lines = int((LOCAL_TOP_Y - CARTOUCHE_TOP_Y - 1.0) / LOCAL_LINE_STEP_MM)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [f"+{len(lines) - max_lines + 1} pièces"]
    for i, line in enumerate(lines):
        font = "Helvetica-Bold" if i == 0 else "Helvetica"
        c.setFont(font, 5.5)
        c.drawCentredString(x * mm, (LOCAL_TOP_Y - i * LOCAL_LINE_STEP_MM) * mm,
                            _fit_text(line, max_w, font, 5.5))


def _draw_bands_table(c: Canvas) -> None:
    """Encadre les deux bandes basses (Pictogramme + Localisation) avec colonne
    de libellés à gauche, façon Hager."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(0.6)
    c.rect(CONTENT_LEFT * mm, CARTOUCHE_TOP_Y * mm,
           (CONTENT_RIGHT - CONTENT_LEFT) * mm,
           (PICTO_BAND_TOP - CARTOUCHE_TOP_Y) * mm)
    c.setLineWidth(0.4)
    c.line(CONTENT_LEFT * mm, PICTO_BAND_BOT * mm,
           CONTENT_RIGHT * mm, PICTO_BAND_BOT * mm)
    c.line(LEGEND_RIGHT * mm, CARTOUCHE_TOP_Y * mm,
           LEGEND_RIGHT * mm, PICTO_BAND_TOP * mm)
    c.setFont("Helvetica", 6)
    c.drawString((CONTENT_LEFT + 1.5) * mm,
                 ((PICTO_BAND_TOP + PICTO_BAND_BOT) / 2 - 1) * mm, "Pictogramme")
    for i, line in enumerate(("Application", "Localisation", "des départs")):
        c.drawString((CONTENT_LEFT + 1.5) * mm, (66 - i * 3.4) * mm, line)


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio : barre JB1, source/continuation, ID + bus
    secondaires JBn, départs Q, barre de terre, pictos, localisation."""
    # Barre principale JB1
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.4)
    c.line(SLOTS_LEFT * mm, MAIN_BUS_Y * mm, CONTENT_RIGHT * mm, MAIN_BUS_Y * mm)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawString((SLOTS_LEFT + 1.5) * mm, (MAIN_BUS_Y + 1.5) * mm, "JB1")

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
        c.drawString(SLOTS_LEFT * mm, (MAIN_BUS_Y + 4) * mm,
                     f"suite du folio {folio_idx}")
    if folio_idx < total - 1:
        c.setFont("Helvetica-Oblique", 6)
        c.drawRightString((CONTENT_RIGHT - 1) * mm, (MAIN_BUS_Y + 4) * mm,
                          f"suite folio {folio_idx + 2}")

    _draw_bands_table(c)

    # Slots : ID puis ses départs
    local = 0
    id_idx = id_offset
    q_idx = q_offset
    for rcd in folio_rcds:
        id_idx += 1
        id_x = _slot_x(local)
        c.setStrokeColor(colors.black)
        c.setLineWidth(1.0)
        c.line(id_x * mm, MAIN_BUS_Y * mm, id_x * mm, (ID_SYM_Y + DIFF_SYM_H / 2) * mm)
        _draw_id(c, id_x, rcd, id_idx)
        c.setLineWidth(1.0)
        c.line(id_x * mm, (ID_SYM_Y - DIFF_SYM_H / 2) * mm, id_x * mm, SEC_BUS_Y * mm)
        local += 1
        n_q = len(rcd.circuits)
        if n_q:
            last_q_x = _slot_x(local + n_q - 1)
            c.setLineWidth(1.2)
            c.line(id_x * mm, SEC_BUS_Y * mm, last_q_x * mm, SEC_BUS_Y * mm)
            c.setFont("Helvetica-Bold", 4.5)
            c.drawString((id_x + 1.5) * mm, (SEC_BUS_Y + 1.5) * mm, f"JB{id_idx + 1}")
        for circ in rcd.circuits:
            q_idx += 1
            qx = _slot_x(local)
            c.setStrokeColor(colors.black)
            c.setLineWidth(1.0)
            c.line(qx * mm, SEC_BUS_Y * mm, qx * mm, (Q_SYM_Y + Q_SYM_H / 2) * mm)
            _draw_q(c, qx, circ, q_idx)
            # Conducteur du départ (phase/neutre) : traverse la barre PE en
            # restant noir (croisement sans jonction) puis flèche vers le bas.
            c.setStrokeColor(colors.black)
            c.setLineWidth(1.0)
            c.line(qx * mm, (Q_SYM_Y - Q_SYM_H / 2) * mm, qx * mm, (PE_Y - 3) * mm)
            _draw_down_arrow(c, qx, PE_Y - 6, colors.black)
            # Prise de terre du départ : flèche verte partant de la barre PE.
            _draw_pe_earth_tap(c, qx - 3)
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
