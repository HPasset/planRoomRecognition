"""Renderer pour les étiquettes PDF imprimables 1:1 à coller dans le
porte-étiquettes du tableau électrique physique. Conçu pour A4 paysage avec
des modules DIN 17.5 mm standards FR (Hager-compatible, Schneider, Legrand).

Voir docs/superpowers/specs/2026-06-03-etiquettes-tableau-design.md
"""
from __future__ import annotations

from io import BytesIO

from svglib.svglib import svg2rlg

from src.planrec.nfc_tableau import Circuit, RCD
from src.planrec.icon_assets import (
    ICONS_DIR,
    load_icon_as_drawing,
    resolve_svg_id_for_circuit as _resolve_svg_id_for_circuit,
)
from src.planrec.tableau_renderer import _tokenize_hyphen


# Constantes de layout (en millimètres, A4 paysage)
INDEX_COL_W_MM = 6.0           # colonne index rangée (1, 2, 3, ...)
ID_CELL_W_MM = 35.0            # cellule "Interrupteur différentiel" (2 modules DIN)
DISJONCTEUR_CELL_W_MM = 17.5   # cellule disjoncteur standard (1 module DIN)
LOGO_CELL_W_MM = 25.0          # cellule dédiée logo batIA en fin de ligne (Hager-like)


def compute_strip_widths(
    n_disjoncteurs: int,
    page_usable_width_mm: float,
    index_col_w_mm: float = INDEX_COL_W_MM,
) -> dict:
    """Calcule la largeur de chaque cellule d'une rangée RCD en mm.

    La rangée = index + ID + n_disjoncteurs Qn + zone blanche (écriture
    libre) + cellule logo batIA. Comme Hager, le logo a sa propre cellule
    à largeur fixe, séparée par une bordure de la zone blanche.

    Args:
        n_disjoncteurs: nombre de disjoncteurs effectivement présents sur le RCD
                        (typiquement 1 à 7, max 8 avec overflow géré ailleurs)
        page_usable_width_mm: largeur imprimable de la page (zone hors marges)
        index_col_w_mm: largeur de la colonne index. Par défaut INDEX_COL_W_MM,
                        mais un document contenant une rangée "x bis" doit
                        utiliser une largeur élargie sur TOUTES ses rangées
                        (colonnes alignées) — cf. compute_index_col_width.

    Returns:
        dict avec clés "index", "id", "disjoncteurs" (list[float]),
        "blank" (zone libre), "logo" (cellule logo batIA).
    """
    disjoncteurs_widths = [DISJONCTEUR_CELL_W_MM] * n_disjoncteurs
    consumed = index_col_w_mm + ID_CELL_W_MM + sum(disjoncteurs_widths) + LOGO_CELL_W_MM
    blank_w = page_usable_width_mm - consumed
    return {
        "index": index_col_w_mm,
        "id": ID_CELL_W_MM,
        "disjoncteurs": disjoncteurs_widths,
        "blank": blank_w,
        "logo": LOGO_CELL_W_MM,
    }


MAX_DISJONCTEURS_PER_ROW = 7   # cellules Qn par rangée d'étiquette (cf. spec)
RCDS_PER_PAGE = 5               # nombre de rangées RCD par page A4 paysage


def split_rcd_into_rows(
    rcd: RCD,
    max_per_row: int = MAX_DISJONCTEURS_PER_ROW,
) -> list[list[Circuit]]:
    """Découpe les circuits d'un RCD en rangées de max max_per_row circuits.

    Si le RCD a ≤ max_per_row circuits → 1 seule rangée.
    Sinon, rangée principale puis rangée(s) de débordement ("1 bis"…).
    """
    rows: list[list[Circuit]] = []
    i = 0
    while i < len(rcd.circuits):
        rows.append(rcd.circuits[i : i + max_per_row])
        i += max_per_row
    if not rows:
        # RCD sans disjoncteur (cas dégénéré) : on garde une rangée vide pour
        # afficher quand même l'ID
        rows.append([])
    return rows


def paginate_rcds(
    rcds: list[RCD],
    per_page: int = RCDS_PER_PAGE,
) -> list[list[RCD]]:
    """Découpe la liste de RCDs en pages par CAPACITÉ DE RANGÉES (per_page
    rangées max par page, cf. split_rcd_into_rows), en gardant toutes les
    rangées d'un même RCD (rangée principale + "bis") sur la même page —
    un RCD avec >7 disjoncteurs occupe 2+ rangées et ne doit jamais être
    coupé entre deux pages.

    Cas dégénéré : un RCD à lui seul ayant plus de per_page rangées déborde
    simplement sur la page suivante (fallback simple, acceptable)."""
    pages: list[list[RCD]] = []
    current_page: list[RCD] = []
    current_rows = 0
    for rcd in rcds:
        n_rows = len(split_rcd_into_rows(rcd, max_per_row=MAX_DISJONCTEURS_PER_ROW))
        if current_page and current_rows + n_rows > per_page:
            pages.append(current_page)
            current_page = []
            current_rows = 0
        current_page.append(rcd)
        current_rows += n_rows
    if current_page:
        pages.append(current_page)
    return pages


def compute_index_col_width(rcds: list[RCD]) -> float:
    """Largeur de colonne index à utiliser pour TOUTES les rangées du
    document : INDEX_COL_W_MM par défaut, ou une largeur élargie si au
    moins une rangée de débordement ("x bis") existe (le label est alors
    plus long que le simple numéro)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    has_overflow = any(
        len(split_rcd_into_rows(rcd, max_per_row=MAX_DISJONCTEURS_PER_ROW)) > 1
        for rcd in rcds
    )
    if not has_overflow:
        return INDEX_COL_W_MM
    widest_label = f"{len(rcds)} bis"
    widest_w_mm = stringWidth(widest_label, "Helvetica-Bold", 8) / mm + 2.0  # marge 1 mm de chaque côté
    return max(INDEX_COL_W_MM, widest_w_mm)


from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics import renderPDF

# Conventions de dimensions (mm)
HEADER_STRIP_H_MM = 8.0        # hauteur du strip header (IDx, Qn, ...)
BODY_STRIP_H_MM = 22.0         # hauteur du strip body (picto + label)
ROW_VERTICAL_GAP_MM = 4.0      # gap entre rangées RCD (était 6 avant ajout STRIP_INNER_GAP_MM)
STRIP_INNER_GAP_MM = 2.0       # gap entre header strip et body strip d'une même rangée RCD
PICTO_SIZE_MM = 10.0           # taille du pictogramme dans la cellule body (10 mm : 4 lignes de texte dessous)
PICTO_TOP_OFFSET_MM = 2.0      # marge haute entre le picto et le bord du strip
TEXT_BELOW_PICTO_GAP_MM = 1.0  # gap vertical entre picto et label texte


def _draw_cell_text(canvas, x_mm, y_mm, w_mm, h_mm, text, font_size=10, bold=False):
    """Centre un texte dans une cellule rectangulaire (coords origine bas-gauche en mm).

    Centrage vertical : le baseline est positionné à ~0.123 × font_size en
    dessous du centre du rectangle. Ce facteur (cap_height/2 normalisé en mm)
    donne un visuel proprement centré pour les polices Helvetica.
    """
    canvas.setFont("Helvetica-Bold" if bold else "Helvetica", font_size)
    canvas.drawCentredString(
        (x_mm + w_mm / 2) * mm,
        (y_mm + h_mm / 2 - font_size * 0.123) * mm,
        text,
    )


def _draw_cell_box(canvas, x_mm, y_mm, w_mm, h_mm, fill_grey=False):
    """Trace le contour d'une cellule rectangulaire (coords bas-gauche en mm)."""
    canvas.setStrokeColor(colors.black)
    if fill_grey:
        canvas.setFillColor(colors.HexColor("#E8E8E8"))
        canvas.rect(x_mm * mm, y_mm * mm, w_mm * mm, h_mm * mm, stroke=1, fill=1)
        canvas.setFillColor(colors.black)
    else:
        canvas.rect(x_mm * mm, y_mm * mm, w_mm * mm, h_mm * mm, stroke=1, fill=0)


def _draw_picto_in_cell(canvas, svg_id, cell_x_mm, cell_y_mm, cell_w_mm, cell_h_mm):
    """Place un picto SVG centré horizontalement, calé en haut de la cellule
    body, à 12 mm × 12 mm avec une marge supérieure de 2 mm."""
    drawing = load_icon_as_drawing(svg_id)
    # svg2rlg retourne un Drawing dont width/height reflètent le viewBox SVG
    # (40x40 par charte). On le re-scale pour atteindre PICTO_SIZE_MM.
    scale = (PICTO_SIZE_MM * mm) / drawing.width
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    # Coordonnée bas-gauche du picto dans la cellule
    x_picto_mm = cell_x_mm + (cell_w_mm - PICTO_SIZE_MM) / 2
    y_picto_mm = cell_y_mm + cell_h_mm - PICTO_TOP_OFFSET_MM - PICTO_SIZE_MM
    renderPDF.draw(drawing, canvas, x_picto_mm * mm, y_picto_mm * mm)


def _draw_batia_logo_cartouche(canvas, x_mm: float, y_mm: float,
                                w_mm: float, h_mm: float):
    """Charge le logo batIA officiel depuis assets/icons/batia_logo.svg
    et le rend centré dans la cellule du body cartouche.

    Le logo conserve son aspect ratio (viewBox 400x150 ~ 2.67:1) et est
    scalé pour tenir dans h_mm en hauteur avec une marge de 2 mm.
    """
    # Charge le logo (CAS SPÉCIAL : svg_id "batia_logo" + ne pas
    # appliquer la substitution currentColor → noir, le logo a ses
    # propres couleurs de marque).
    svg_path = ICONS_DIR / "batia_logo.svg"
    if not svg_path.is_file():
        # Fallback texte si le fichier manque
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawCentredString(
            (x_mm + w_mm / 2) * mm,
            (y_mm + h_mm / 2 - 14 * 0.123) * mm,
            "Bat ia",
        )
        return

    raw = svg_path.read_text(encoding="utf-8")
    # Le logo a ses propres couleurs hex, pas de currentColor à substituer.
    drawing = svg2rlg(BytesIO(raw.encode("utf-8")))

    # Scale pour que le logo tienne dans (h_mm - 2 mm padding) en hauteur
    target_h_mm = h_mm - 2.0
    scale = (target_h_mm * mm) / drawing.height
    # Aspect ratio préservé
    drawing_w_mm = drawing.width * scale / mm
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)

    # Si le logo scalé est plus large que la cellule, re-scale par la largeur
    if drawing_w_mm > w_mm - 4.0:
        scale_w = ((w_mm - 4.0) * mm) / drawing.width
        drawing.width *= scale_w
        drawing.height *= scale_w
        drawing.scale(scale_w, scale_w)
        drawing_w_mm = drawing.width / mm

    # Centre dans la cellule
    x_logo_mm = x_mm + (w_mm - drawing_w_mm) / 2
    drawing_h_mm = drawing.height / mm
    y_logo_mm = y_mm + (h_mm - drawing_h_mm) / 2
    renderPDF.draw(drawing, canvas, x_logo_mm * mm, y_logo_mm * mm)


def _wrap_cell_label(label: str, max_chars: int = 8, max_lines: int = 4) -> list[str]:
    """Découpe un label en lignes de ≤ max_chars pour tenir dans 17.5 mm.
    Réutilise la stratégie de _wrap_label de tableau_renderer (espaces + traits
    d'union). 4 lignes en 6 pt tiennent sous le picto de 10 mm (« Écl. CH2 /
    CH3 DGT / BAIN CEL / ×5 »)."""
    words = _tokenize_hyphen(label)
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= max_chars:
            current = current + " " + word
        else:
            lines.append(current)
            if len(lines) >= max_lines:
                break
            current = word
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def render_rcd_row(
    canvas,
    rcd,
    row_circuits: list,
    rcd_index: int,
    global_q_start: int,
    y_top_mm: float,
    page_usable_width_mm: float,
    is_overflow_row: bool = False,
    x_left_mm: float = 10.0,
    index_col_w_mm: float = INDEX_COL_W_MM,
) -> int:
    """Rend UNE rangée RCD (header strip + body strip) sur le canvas.

    Args:
        canvas: reportlab Canvas (origine bas-gauche en pt)
        rcd: RCD à rendre
        row_circuits: liste des circuits effectivement affichés sur cette rangée
                      (peut être un sous-ensemble de rcd.circuits si overflow)
        rcd_index: numéro 1-based du RCD dans le tableau (pour la cellule index)
        global_q_start: numéro global du 1er Qn de cette rangée (Q1, Q8, ...)
        y_top_mm: coord Y du haut du strip header (origine canvas bas-gauche
                  signifie qu'on dessine vers le bas en soustrayant)
        page_usable_width_mm: largeur imprimable de la page
        is_overflow_row: True si c'est une rangée de débordement (1 bis, ...)
                         → on grise la cellule ID pour distinguer

    Returns:
        global_q_next: numéro global du prochain Q (= global_q_start + len(row_circuits))
                       à passer à la rangée suivante.
    """
    widths = compute_strip_widths(
        n_disjoncteurs=len(row_circuits),
        page_usable_width_mm=page_usable_width_mm,
        index_col_w_mm=index_col_w_mm,
    )

    # Y bas-gauche des deux strips (reportlab Canvas mesure de bas en haut).
    # STRIP_INNER_GAP_MM laisse un espace blanc visible entre header et body,
    # comme dans le format Hager (les 2 strips ne se touchent pas).
    y_header_bottom_mm = y_top_mm - HEADER_STRIP_H_MM
    y_body_bottom_mm = y_header_bottom_mm - STRIP_INNER_GAP_MM - BODY_STRIP_H_MM

    # -- STRIP HEADER (ligne du haut : index, IDx, Q-numéros, batIA) --
    x_cursor_mm = x_left_mm

    # Cellule index rangée
    _draw_cell_box(canvas, x_cursor_mm, y_header_bottom_mm, widths["index"], HEADER_STRIP_H_MM)
    index_label = f"{rcd_index} bis" if is_overflow_row else str(rcd_index)
    _draw_cell_text(canvas, x_cursor_mm, y_header_bottom_mm, widths["index"],
                    HEADER_STRIP_H_MM, index_label, font_size=8, bold=True)
    x_cursor_mm += widths["index"]

    # Cellule ID
    _draw_cell_box(canvas, x_cursor_mm, y_header_bottom_mm, widths["id"], HEADER_STRIP_H_MM,
                   fill_grey=is_overflow_row)
    _draw_cell_text(canvas, x_cursor_mm, y_header_bottom_mm, widths["id"],
                    HEADER_STRIP_H_MM, f"ID {rcd_index}", font_size=10, bold=True)
    x_cursor_mm += widths["id"]

    # Cellules Qn
    for i, _circuit in enumerate(row_circuits):
        q_num = global_q_start + i
        _draw_cell_box(canvas, x_cursor_mm, y_header_bottom_mm,
                       DISJONCTEUR_CELL_W_MM, HEADER_STRIP_H_MM)
        _draw_cell_text(canvas, x_cursor_mm, y_header_bottom_mm,
                        DISJONCTEUR_CELL_W_MM, HEADER_STRIP_H_MM,
                        f"Q{q_num}", font_size=9, bold=True)
        x_cursor_mm += DISJONCTEUR_CELL_W_MM

    # Header : zone blanche (écriture libre) puis cellule logo (vide ici)
    _draw_cell_box(canvas, x_cursor_mm, y_header_bottom_mm,
                   widths["blank"], HEADER_STRIP_H_MM)
    x_cursor_mm += widths["blank"]
    _draw_cell_box(canvas, x_cursor_mm, y_header_bottom_mm,
                   widths["logo"], HEADER_STRIP_H_MM)

    # -- STRIP BODY (ligne du bas : picto + label par cellule) --
    x_cursor_mm = x_left_mm

    # Cellule index body (vide ou répétée selon préférence ; on laisse vide)
    _draw_cell_box(canvas, x_cursor_mm, y_body_bottom_mm, widths["index"], BODY_STRIP_H_MM)
    x_cursor_mm += widths["index"]

    # Cellule ID body : picto interrupteur différentiel + texte "Interrupteur différentiel"
    _draw_cell_box(canvas, x_cursor_mm, y_body_bottom_mm, widths["id"], BODY_STRIP_H_MM,
                   fill_grey=is_overflow_row)
    if not is_overflow_row:
        _draw_picto_in_cell(canvas, "differential",
                            x_cursor_mm, y_body_bottom_mm,
                            widths["id"], BODY_STRIP_H_MM)
        # Texte sur 2 lignes : "Interrupteur" / "différentiel"
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(
            (x_cursor_mm + widths["id"] / 2) * mm,
            (y_body_bottom_mm + 5) * mm,
            "Interrupteur",
        )
        canvas.drawCentredString(
            (x_cursor_mm + widths["id"] / 2) * mm,
            (y_body_bottom_mm + 2) * mm,
            "différentiel",
        )
    x_cursor_mm += widths["id"]

    # Cellules Qn body : picto + label tronqué
    for circuit in row_circuits:
        _draw_cell_box(canvas, x_cursor_mm, y_body_bottom_mm,
                       DISJONCTEUR_CELL_W_MM, BODY_STRIP_H_MM)
        svg_id = _resolve_svg_id_for_circuit(circuit)
        _draw_picto_in_cell(canvas, svg_id,
                            x_cursor_mm, y_body_bottom_mm,
                            DISJONCTEUR_CELL_W_MM, BODY_STRIP_H_MM)
        # Label sur 4 lignes max, sous le picto (qui occupe les 12 mm du haut)
        label_lines = _wrap_cell_label(circuit.label, max_chars=8)
        canvas.setFont("Helvetica", 6)
        for i, line in enumerate(label_lines):
            y_text_mm = y_body_bottom_mm + 7.6 - (i * 2.2)
            canvas.drawCentredString(
                (x_cursor_mm + DISJONCTEUR_CELL_W_MM / 2) * mm,
                y_text_mm * mm,
                line,
            )
        x_cursor_mm += DISJONCTEUR_CELL_W_MM

    # Body : zone blanche (écriture libre, sans logo) puis cellule logo dédiée
    _draw_cell_box(canvas, x_cursor_mm, y_body_bottom_mm,
                   widths["blank"], BODY_STRIP_H_MM)
    x_cursor_mm += widths["blank"]
    _draw_cell_box(canvas, x_cursor_mm, y_body_bottom_mm,
                   widths["logo"], BODY_STRIP_H_MM)
    _draw_batia_logo_cartouche(canvas, x_cursor_mm, y_body_bottom_mm,
                                widths["logo"], BODY_STRIP_H_MM)

    return global_q_start + len(row_circuits)


# --- Task 10 : orchestrateur PDF complet ---------------------------------
import io
from datetime import date

from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau

# Marges et zone imprimable (mm)
PAGE_MARGIN_MM = 10.0
A4_LANDSCAPE_W_MM = 297.0
A4_LANDSCAPE_H_MM = 210.0
USABLE_W_MM = A4_LANDSCAPE_W_MM - 2 * PAGE_MARGIN_MM  # 277 mm
USABLE_H_MM = A4_LANDSCAPE_H_MM - 2 * PAGE_MARGIN_MM  # 190 mm
FOOTER_H_MM = 5.0


def _draw_footer(canvas, tableau, page_idx: int, total_pages: int):
    """Pied de page identique sur chaque page : date + projet + page n/N à
    gauche, instruction d'échelle à droite."""
    y_mm = PAGE_MARGIN_MM / 2
    canvas.setFont("Helvetica-Oblique", 7)
    today = date.today().isoformat()
    left = (
        f"{today}  -  Tableau electrique  -  Logement {tableau.typology}  "
        f"-  Page {page_idx + 1}/{total_pages}"
    )
    canvas.drawString(PAGE_MARGIN_MM * mm, y_mm * mm, left)
    right = "Imprimer à l'échelle 1:1 (option « Taille réelle » ou « 100 % »)"
    canvas.drawRightString(
        (A4_LANDSCAPE_W_MM - PAGE_MARGIN_MM) * mm, y_mm * mm, right
    )


def render_etiquettes_pdf(tableau: Tableau) -> bytes:
    """Rend le PDF complet des etiquettes (multi-pages si necessaire).

    Format A4 paysage, 5 RCDs max par page (rangee header + body =
    30 mm chacun + gap 6 mm = 36 mm total ; 190 mm utiles / 36 ~ 5 RCDs).
    Si un RCD a > 7 disjoncteurs (max NFC = 8), il est eclate en 2 rangees
    consecutives (1 et 1 bis).

    Args:
        tableau: instance Tableau produite par generate_tableau()

    Returns:
        bytes du PDF pret a telechargement.
    """
    buf = io.BytesIO()
    canvas = Canvas(buf, pagesize=landscape(A4))
    pages = paginate_rcds(tableau.rcds, per_page=RCDS_PER_PAGE)
    total_pages = max(len(pages), 1)

    global_q_counter = 1
    rcd_counter = 0  # numéro 1-based du RCD dans le tableau, continu entre pages
    index_col_w_mm = compute_index_col_width(tableau.rcds)

    for page_idx, rcds_in_page in enumerate(pages):
        # Coord y "top" du strip header du 1er RCD : zone utile descendante
        y_top_mm = A4_LANDSCAPE_H_MM - PAGE_MARGIN_MM

        for local_idx, rcd in enumerate(rcds_in_page):
            rcd_counter += 1
            rows = split_rcd_into_rows(rcd, max_per_row=MAX_DISJONCTEURS_PER_ROW)
            for row_idx, row_circuits in enumerate(rows):
                is_overflow = row_idx > 0
                global_q_counter = render_rcd_row(
                    canvas=canvas,
                    rcd=rcd,
                    row_circuits=row_circuits,
                    rcd_index=rcd_counter,
                    global_q_start=global_q_counter,
                    y_top_mm=y_top_mm,
                    page_usable_width_mm=USABLE_W_MM,
                    is_overflow_row=is_overflow,
                    x_left_mm=PAGE_MARGIN_MM,
                    index_col_w_mm=index_col_w_mm,
                )
                y_top_mm -= (HEADER_STRIP_H_MM + STRIP_INNER_GAP_MM + BODY_STRIP_H_MM + ROW_VERTICAL_GAP_MM)

        _draw_footer(canvas, tableau, page_idx, total_pages)
        canvas.showPage()

    # Cas tableau vide : on emet quand meme une page d'avertissement
    if not pages:
        canvas.setFont("Helvetica", 12)
        canvas.drawCentredString(
            (A4_LANDSCAPE_W_MM / 2) * mm,
            (A4_LANDSCAPE_H_MM / 2) * mm,
            "Aucun RCD a etiqueter (tableau vide)",
        )
        _draw_footer(canvas, tableau, 0, 1)
        canvas.showPage()

    canvas.save()
    return buf.getvalue()
