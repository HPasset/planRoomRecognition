"""Génère une présentation PPTX (palette batIA) pour le board.

Usage :
    pip install python-pptx
    python scripts/generate_board_presentation.py

Output : docs/presentations/avancement_stage_a_2026_05_11.pptx
"""
from __future__ import annotations
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn
from copy import deepcopy
from lxml import etree


# ─────────────────────────────────────────────────────────────────────
# PALETTE BATIA (extraite du deck officiel)
# ─────────────────────────────────────────────────────────────────────
PALETTE = {
    "primary_dark": RGBColor(0x21, 0x1B, 0x57),      # indigo navy
    "accent_purple": RGBColor(0x76, 0x47, 0xE5),     # violet vif
    "light_lilac": RGBColor(0xEB, 0xE0, 0xFB),       # mauve clair (cards)
    "lilac_mid": RGBColor(0xC9, 0xB5, 0xF2),         # mauve mi-clair
    "white": RGBColor(0xFF, 0xFF, 0xFF),
    "text_dark": RGBColor(0x33, 0x33, 0x3F),
    "text_secondary": RGBColor(0x66, 0x66, 0x80),
    "success": RGBColor(0x22, 0xC5, 0x5E),
    "warning": RGBColor(0xF5, 0x9E, 0x0B),
    "error": RGBColor(0xEF, 0x44, 0x44),
    "neutral_gray": RGBColor(0xD8, 0xD8, 0xE5),
}

FONT_TITLE = "Calibri"
FONT_BODY = "Calibri"

SLIDE_W_IN = 13.333  # 16:9 widescreen
SLIDE_H_IN = 7.5


# ─────────────────────────────────────────────────────────────────────
# UTILITAIRES DE STYLE
# ─────────────────────────────────────────────────────────────────────
def set_slide_background(slide, color: RGBColor):
    """Set the background color of a slide."""
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rectangle(slide, x_in, y_in, w_in, h_in, fill_color, line_color=None,
                  rounded=False):
    """Add a colored rectangle. Returns the shape."""
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(
        shape_type,
        Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line_color
        shape.line.width = Pt(1)
    if rounded:
        # Adoucir les coins
        shape.adjustments[0] = 0.10
    return shape


def add_text(slide, text, x_in, y_in, w_in, h_in,
             font_size=18, font_color=None, bold=False, italic=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font_name=FONT_BODY):
    """Add a text box. Returns the shape."""
    if font_color is None:
        font_color = PALETTE["text_dark"]
    txBox = slide.shapes.add_textbox(
        Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.color.rgb = font_color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = font_name
    return txBox


def add_bullet_list(slide, bullets: list[str], x_in, y_in, w_in, h_in,
                    font_size=16, font_color=None, font_name=FONT_BODY):
    """Add a bullet list."""
    if font_color is None:
        font_color = PALETTE["text_dark"]
    txBox = slide.shapes.add_textbox(
        Inches(x_in), Inches(y_in), Inches(w_in), Inches(h_in)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, bullet_text in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        p.level = 0
        run = p.add_run()
        run.text = "• " + bullet_text
        run.font.size = Pt(font_size)
        run.font.color.rgb = font_color
        run.font.name = font_name
        # spacing between bullets
        p.space_after = Pt(8)
    return txBox


def add_header_strip(slide, slide_number=None):
    """Add the dark navy header strip with optional slide number."""
    add_rectangle(slide, 0, 0, SLIDE_W_IN, 0.6, PALETTE["primary_dark"])
    add_text(slide, "Bat IA — Avancement segmentation",
             0.4, 0.1, 8, 0.4,
             font_size=14, font_color=PALETTE["white"], bold=True, italic=True)
    if slide_number:
        add_text(slide, f"{slide_number} / 14",
                 SLIDE_W_IN - 1.2, 0.1, 0.8, 0.4,
                 font_size=11, font_color=PALETTE["lilac_mid"], align=PP_ALIGN.RIGHT)


def add_footer(slide):
    """Add the bottom footer line."""
    add_rectangle(slide, 0, SLIDE_H_IN - 0.15, SLIDE_W_IN, 0.15,
                  PALETTE["accent_purple"])


def add_section_title(slide, title, subtitle=None):
    """Add a title at the top of a content slide (after the header)."""
    add_text(slide, title, 0.6, 0.85, SLIDE_W_IN - 1.2, 0.7,
             font_size=32, font_color=PALETTE["primary_dark"],
             bold=True, italic=True)
    if subtitle:
        add_text(slide, subtitle, 0.6, 1.55, SLIDE_W_IN - 1.2, 0.45,
                 font_size=15, font_color=PALETTE["text_secondary"], italic=True)


def add_card(slide, title, text, x_in, y_in, w_in, h_in,
             title_color=None, bg_color=None):
    """Add a rounded card with title + text."""
    if bg_color is None:
        bg_color = PALETTE["light_lilac"]
    if title_color is None:
        title_color = PALETTE["primary_dark"]
    add_rectangle(slide, x_in, y_in, w_in, h_in, bg_color, rounded=True)
    add_text(slide, title, x_in + 0.15, y_in + 0.1, w_in - 0.3, 0.4,
             font_size=14, font_color=title_color, bold=True, italic=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, text, x_in + 0.15, y_in + 0.55, w_in - 0.3, h_in - 0.7,
             font_size=12, font_color=PALETTE["text_dark"],
             align=PP_ALIGN.CENTER)


def add_metric_box(slide, label, value, x_in, y_in, w_in, h_in,
                   value_color=None):
    """Add a metric highlight box (big number + small label)."""
    if value_color is None:
        value_color = PALETTE["accent_purple"]
    add_rectangle(slide, x_in, y_in, w_in, h_in, PALETTE["light_lilac"],
                  rounded=True)
    add_text(slide, value, x_in, y_in + 0.15, w_in, h_in / 2,
             font_size=32, font_color=value_color, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(slide, label, x_in, y_in + h_in / 2 + 0.15, w_in, h_in / 2 - 0.2,
             font_size=11, font_color=PALETTE["text_secondary"],
             align=PP_ALIGN.CENTER, italic=True)


def add_table_slide(slide, headers: list[str], rows: list[list[str]],
                    x_in: float, y_in: float, w_in: float, h_in: float,
                    header_bg=None, alt_row_bg=None,
                    cell_text_color=None, cell_font_size=11):
    """Add a styled table to the slide."""
    if header_bg is None:
        header_bg = PALETTE["primary_dark"]
    if alt_row_bg is None:
        alt_row_bg = PALETTE["light_lilac"]
    if cell_text_color is None:
        cell_text_color = PALETTE["text_dark"]

    rows_count = len(rows) + 1  # +1 for header
    cols_count = len(headers)
    table_shape = slide.shapes.add_table(
        rows_count, cols_count,
        Inches(x_in), Inches(y_in),
        Inches(w_in), Inches(h_in),
    )
    table = table_shape.table

    # Header row
    for c, h in enumerate(headers):
        cell = table.cell(0, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = header_bg
        tf = cell.text_frame
        tf.text = h
        for p in tf.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(cell_font_size + 1)
                r.font.color.rgb = PALETTE["white"]
                r.font.name = FONT_BODY

    # Data rows
    for r_idx, row in enumerate(rows, start=1):
        bg = alt_row_bg if r_idx % 2 == 1 else PALETTE["white"]
        for c_idx, value in enumerate(row):
            cell = table.cell(r_idx, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg
            tf = cell.text_frame
            tf.text = str(value)
            for p in tf.paragraphs:
                p.alignment = PP_ALIGN.CENTER if c_idx > 0 else PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.size = Pt(cell_font_size)
                    r.font.color.rgb = cell_text_color
                    r.font.name = FONT_BODY


# ─────────────────────────────────────────────────────────────────────
# CONSTRUCTION DES SLIDES
# ─────────────────────────────────────────────────────────────────────
def build_slide_1_cover(prs):
    """Slide 1 — Couverture."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    set_slide_background(slide, PALETTE["white"])

    # Bandeau diagonal foncé en haut
    add_rectangle(slide, 0, 0, SLIDE_W_IN, 2.5, PALETTE["primary_dark"])

    # Titre principal
    add_text(slide, "Avancement technique",
             0.6, 0.6, SLIDE_W_IN - 1.2, 0.8,
             font_size=42, font_color=PALETTE["white"], bold=True, italic=True)
    add_text(slide, "Brique B — Segmentation des pièces",
             0.6, 1.4, SLIDE_W_IN - 1.2, 0.6,
             font_size=24, font_color=PALETTE["lilac_mid"], italic=True)

    # Bloc principal central
    add_rectangle(slide, 1.5, 3.2, 10.3, 2.8, PALETTE["light_lilac"], rounded=True)
    add_text(slide, "Stage A — Pré-entraînement",
             1.5, 3.4, 10.3, 0.6,
             font_size=28, font_color=PALETTE["primary_dark"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide, "Modèle Mask2Former entraîné sur dataset CubiCasa5K (4 745 plans)",
             1.5, 4.0, 10.3, 0.5,
             font_size=15, font_color=PALETTE["text_dark"],
             align=PP_ALIGN.CENTER, italic=True)
    add_text(slide, "Présentation board — 11 mai 2026",
             1.5, 5.1, 10.3, 0.4,
             font_size=14, font_color=PALETTE["accent_purple"],
             bold=True, align=PP_ALIGN.CENTER)
    add_text(slide, "Hadrien Passet — CTO",
             1.5, 5.5, 10.3, 0.4,
             font_size=13, font_color=PALETTE["text_secondary"],
             align=PP_ALIGN.CENTER, italic=True)

    add_footer(slide)


def build_slide_2_role(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=2)
    add_section_title(slide, "Rôle de la brique segmentation",
                      "La colonne vertébrale du pipeline IA batIA")

    bullets = [
        "Le pipeline batIA prend un plan d'étage en entrée et produit un devis électrique en sortie",
        "La brique segmentation détecte chaque pièce et son type (cuisine, chambre, sdb, garage…)",
        "Sans cette information, IMPOSSIBLE d'appliquer les règles NF C 15-100 par pièce",
    ]
    add_bullet_list(slide, bullets, 0.7, 2.3, SLIDE_W_IN - 1.4, 1.5,
                    font_size=17)

    # 3 cartes exemples règles NFC
    add_card(slide, "Cuisine",
             "min 6 prises 16A\n+ prise spécialisée 32A pour plaque",
             0.7, 4.2, 4.0, 2.6)
    add_card(slide, "Salle de bain",
             "Volumes 0/1/2 strictement définis\nzones interdites prises",
             4.65, 4.2, 4.0, 2.6)
    add_card(slide, "Chambre",
             "1 va-et-vient principal\n+ 2 va-et-vient au chevet du lit",
             8.6, 4.2, 4.0, 2.6)
    add_footer(slide)


def build_slide_3_architecture(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=3)
    add_section_title(slide, "Architecture choisie : Mask2Former",
                      "État de l'art segmentation panoptique (Meta AI 2022)")

    # Comparaison YOLO vs Mask2Former en 2 colonnes
    add_rectangle(slide, 0.7, 2.2, 5.95, 4.3, PALETTE["light_lilac"], rounded=True)
    add_text(slide, "YOLO (existant)", 0.9, 2.35, 5.6, 0.5,
             font_size=18, font_color=PALETTE["primary_dark"],
             bold=True, italic=True)
    add_bullet_list(slide, [
        "Détecte des OBJETS (lit, canapé, évier...)",
        "Sortie : RECTANGLES (bbox approximatifs)",
        "Ne dit rien sur la géométrie des pièces",
        "Insuffisant pour appliquer NFC par pièce",
    ], 0.9, 2.95, 5.6, 3.5, font_size=13)

    add_rectangle(slide, 6.85, 2.2, 5.95, 4.3, PALETTE["accent_purple"], rounded=True)
    add_text(slide, "Mask2Former (nouveau)", 7.05, 2.35, 5.6, 0.5,
             font_size=18, font_color=PALETTE["white"], bold=True, italic=True)
    add_bullet_list(slide, [
        "Détecte des PIÈCES (cuisine, chambre, sdb...)",
        "Sortie : POLYGONES (contours exacts des murs)",
        "Donne géométrie + type + surface",
        "Permet calcul précis et règles NFC",
    ], 7.05, 2.95, 5.6, 3.5, font_size=13, font_color=PALETTE["white"])

    # Bandeau bas explicatif
    add_text(slide,
             "Vulgarisation : c'est comme un coloriage automatique où chaque pièce reçoit sa couleur correspondant à son type.",
             0.7, 6.7, SLIDE_W_IN - 1.4, 0.5,
             font_size=12, font_color=PALETTE["text_secondary"],
             italic=True, align=PP_ALIGN.CENTER)
    add_footer(slide)


def build_slide_4_taxonomy(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=4)
    add_section_title(slide, "Taxonomie : 10 classes alignées NFC",
                      "Choix : on garde uniquement les distinctions qui changent les règles électriques")

    headers = ["ID", "Classe", "Rôle"]
    rows = [
        ["0", "Background", "Extérieur du bâtiment"],
        ["1", "Wall", "Murs porteurs + cloisons"],
        ["2", "Kitchen", "Cuisine"],
        ["3", "LivingRoom", "Séjour / salon / dining"],
        ["4", "BedRoom", "Chambre"],
        ["5", "Bath", "Salle de bain + WC fusionnés"],
        ["6", "Entry", "Entrée + couloir / circulation"],
        ["7", "Storage", "Rangement, dressing, buanderie"],
        ["8", "Garage", "Garage"],
        ["9", "Outdoor", "Balcon, terrasse"],
    ]
    add_table_slide(slide, headers, rows, 1.5, 2.2, 10.3, 4.6,
                    cell_font_size=12)
    add_footer(slide)


def build_slide_5_dataset(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=5)
    add_section_title(slide, "Dataset : CubiCasa5K",
                      "4 745 plans d'étage open source — Aalto University (Finlande)")

    add_bullet_list(slide, [
        "Dataset open source utilisé par les chercheurs en deep learning sur plans architecturaux",
        "Annotations polygones de pièces + meubles + structure (très précis)",
        "Splits train / val / test : 4 000 / 467 / 479 plans",
        "Volume : ~10 GB de données traitées en format panoptic prêt pour entraînement",
        "Licence permissive autorisant l'usage commercial",
    ], 0.7, 2.2, SLIDE_W_IN - 1.4, 2.5, font_size=15)

    # 3 metric boxes
    add_metric_box(slide, "Plans utilisés", "4 745", 0.7, 5.1, 4.0, 1.5)
    add_metric_box(slide, "Classes annotées", "10", 4.65, 5.1, 4.0, 1.5)
    add_metric_box(slide, "Format de sortie", "Panoptic", 8.6, 5.1, 4.0, 1.5)

    add_text(slide,
             "Limite : style finlandais → besoin d'adaptation pour plans français (Stage B prévu)",
             0.7, 6.85, SLIDE_W_IN - 1.4, 0.4,
             font_size=11, font_color=PALETTE["text_secondary"],
             italic=True, align=PP_ALIGN.CENTER)
    add_footer(slide)


def build_slide_6_results_global(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=6)
    add_section_title(slide, "Résultats Stage A — métriques globales",
                      "4 jours de training sur Mac M5 Pro")

    # 3 grandes metrics
    add_metric_box(slide, "Loss training (descente)", "95 → 30", 0.7, 2.4, 4.0, 1.7,
                   value_color=PALETTE["accent_purple"])
    add_metric_box(slide, "mIoU validation (×3.8)", "0.13 → 0.51", 4.65, 2.4, 4.0, 1.7,
                   value_color=PALETTE["accent_purple"])
    add_metric_box(slide, "Cible MVP", "≥ 0.55", 8.6, 2.4, 4.0, 1.7,
                   value_color=PALETTE["primary_dark"])

    add_text(slide, "État actuel — epoch 55 / 80",
             0.7, 4.4, SLIDE_W_IN - 1.4, 0.5,
             font_size=18, font_color=PALETTE["primary_dark"],
             bold=True, italic=True)
    add_bullet_list(slide, [
        "Modèle stable : aucune divergence depuis les correctifs",
        "Cible MVP atteignable d'ici 25 epochs (mardi-mercredi prochain)",
        "Train loss continue à descendre lentement (phase d'affinage cosine decay)",
        "Pas d'overfitting : val/mIoU encore en croissance régulière",
    ], 0.7, 4.95, SLIDE_W_IN - 1.4, 1.8, font_size=14)

    add_text(slide,
             "mIoU = mean Intersection over Union, métrique standard segmentation. "
             "0.5+ = bon résultat industriel sur ce type de tâche.",
             0.7, 6.85, SLIDE_W_IN - 1.4, 0.4,
             font_size=10, font_color=PALETTE["text_secondary"],
             italic=True, align=PP_ALIGN.CENTER)
    add_footer(slide)


def build_slide_7_results_per_class(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=7)
    add_section_title(slide, "Résultats par type de pièce",
                      "À l'epoch 55 — les classes principales pour batIA sont solidement apprises")

    headers = ["Classe", "IoU", "État"]
    rows = [
        ["Background (extérieur)", "0.83", "✓ Excellent"],
        ["BedRoom (chambre)", "0.60", "✓ Excellent"],
        ["LivingRoom (séjour)", "0.60", "✓ Excellent"],
        ["Kitchen (cuisine)", "0.60", "✓ Excellent"],
        ["Outdoor (balcon/terrasse)", "0.54", "✓ Bon"],
        ["Entry (entrée/couloir)", "0.48", "Correct"],
        ["Bath (salle de bain)", "0.46", "Correct"],
        ["Garage", "0.46", "Correct (rare)"],
        ["Storage (rangement)", "0.35", "Modeste (hétérogène)"],
        ["Wall (murs)", "0.26", "Difficile (lignes fines)"],
    ]
    add_table_slide(slide, headers, rows, 1.5, 2.2, 10.3, 4.6,
                    cell_font_size=12)
    add_footer(slide)


def build_slide_8_difficulties(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=8)
    add_section_title(slide, "Difficultés rencontrées et résolues",
                      "Transparence sur les itérations techniques")

    bugs = [
        ("Bug mapping CubiCasa", "La classe 'Bedroom' (la plus fréquente !) n'était pas reconnue → audit complet des labels"),
        ("Bug Background non entraîné", "Architecturalement absente comme cible → mIoU plafonnée à 9/10 du potentiel. Corrigé."),
        ("NaN loss en BF16", "Précision BF16 sur Mac MPS provoquait des explosions numériques → migration FP32"),
        ("MPS missing op", "Opération grid_sampler_2d_backward non implémentée sur Mac → fallback CPU activé"),
        ("Optim thermique nocturne", "Sleep macOS ralentissait training → utilisation `caffeinate` pour empêcher le sleep"),
    ]
    y_start = 2.3
    card_h = 0.85
    for i, (title, desc) in enumerate(bugs):
        y = y_start + i * (card_h + 0.05)
        add_rectangle(slide, 0.7, y, SLIDE_W_IN - 1.4, card_h,
                      PALETTE["light_lilac"], rounded=True)
        add_text(slide, title, 0.95, y + 0.1, 4.5, 0.4,
                 font_size=13, font_color=PALETTE["primary_dark"],
                 bold=True, italic=True)
        add_text(slide, desc, 5.5, y + 0.1, 6.8, card_h - 0.2,
                 font_size=11, font_color=PALETTE["text_dark"])

    add_footer(slide)


def build_slide_9_domain_gap(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=9)
    add_section_title(slide, "Limite actuelle : domain gap CubiCasa ↔ FR",
                      "Pourquoi un Stage B (fine-tuning sur plans FR) est nécessaire")

    add_bullet_list(slide, [
        "Le modèle est entraîné sur des plans finlandais (style standardisé, icônes spécifiques)",
        "Les plans FR ont des conventions visuelles différentes :",
    ], 0.7, 2.3, SLIDE_W_IN - 1.4, 1.0, font_size=15)

    # 3 sous-bullets
    sub_bullets = [
        "Symboles de meubles distincts (lavabo, baignoire, lit dessinés autrement)",
        "Cotations en mètres partout (CubiCasa n'en a pas)",
        "Légendes, hachures de murs spécifiques au cabinet",
    ]
    for i, b in enumerate(sub_bullets):
        add_text(slide, "    – " + b, 0.7, 3.3 + i * 0.4, SLIDE_W_IN - 1.4, 0.4,
                 font_size=13, font_color=PALETTE["text_dark"])

    # Solution
    add_rectangle(slide, 0.7, 5.0, SLIDE_W_IN - 1.4, 1.7,
                  PALETTE["accent_purple"], rounded=True)
    add_text(slide, "Solution : Stage B = fine-tuning sur ~150 plans FR annotés",
             0.7, 5.15, SLIDE_W_IN - 1.4, 0.5,
             font_size=18, font_color=PALETTE["white"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide,
             "On garde tout ce qui a été appris (transfer learning) et on adapte au domaine FR.\n"
             "Investissement : ~15-25h d'annotation + ~24-48h de fine-tuning.",
             0.7, 5.7, SLIDE_W_IN - 1.4, 1.0,
             font_size=13, font_color=PALETTE["white"],
             italic=True, align=PP_ALIGN.CENTER)

    add_footer(slide)


def build_slide_10_stage_b_roadmap(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=10)
    add_section_title(slide, "Stage B — roadmap fine-tuning FR",
                      "Plan détaillé sur 3-4 semaines")

    phases = [
        ("1. Collecte", "150 plans FR (contacts électriciens, data.gouv.fr, plans perso)"),
        ("2. Annotation", "CVAT (open-source, gratuit, hébergé localement)\nPré-annotation auto + correction humaine ≈ 5 min/plan"),
        ("3. Fine-tuning", "Modèle Stage A + plans FR pondérés ×8\nLR 10× plus bas pour adaptation subtile"),
        ("4. Évaluation", "50 plans FR 'gold standard' jamais touchés\nCible : mIoU ≥ 0.55 sur plans FR"),
    ]
    card_w = 3.0
    gap = 0.15
    start_x = (SLIDE_W_IN - (4 * card_w + 3 * gap)) / 2
    for i, (title, desc) in enumerate(phases):
        x = start_x + i * (card_w + gap)
        add_rectangle(slide, x, 2.5, card_w, 4.0,
                      PALETTE["light_lilac"], rounded=True)
        add_text(slide, title, x, 2.7, card_w, 0.5,
                 font_size=16, font_color=PALETTE["primary_dark"],
                 bold=True, italic=True, align=PP_ALIGN.CENTER)
        add_text(slide, desc, x + 0.15, 3.3, card_w - 0.3, 3.0,
                 font_size=11, font_color=PALETTE["text_dark"],
                 align=PP_ALIGN.CENTER)

    add_text(slide,
             "Pendant l'annotation, le YOLO meubles (brique A) et la brique OCR pourront être préparés en parallèle.",
             0.7, 6.85, SLIDE_W_IN - 1.4, 0.4,
             font_size=11, font_color=PALETTE["text_secondary"],
             italic=True, align=PP_ALIGN.CENTER)

    add_footer(slide)


def build_slide_11_pipeline(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=11)
    add_section_title(slide, "Pipeline batIA — vue multi-briques",
                      "Chaque brique compense les faiblesses des autres")

    # Plan input
    add_rectangle(slide, 5.5, 2.0, 2.3, 0.6, PALETTE["primary_dark"], rounded=True)
    add_text(slide, "Plan d'étage", 5.5, 2.05, 2.3, 0.5,
             font_size=12, font_color=PALETTE["white"], bold=True,
             align=PP_ALIGN.CENTER)

    # Brique B (current)
    add_rectangle(slide, 0.7, 3.0, 5.95, 0.85, PALETTE["accent_purple"], rounded=True)
    add_text(slide, "Brique B — Mask2Former (segmentation)",
             0.7, 3.1, 5.95, 0.35,
             font_size=12, font_color=PALETTE["white"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide, "→ polygones de pièces typées + masque murs",
             0.7, 3.45, 5.95, 0.3,
             font_size=10, font_color=PALETTE["white"], align=PP_ALIGN.CENTER)

    # Brique A
    add_rectangle(slide, 6.85, 3.0, 5.95, 0.85, PALETTE["lilac_mid"], rounded=True)
    add_text(slide, "Brique A — YOLO (détection meubles)",
             6.85, 3.1, 5.95, 0.35,
             font_size=12, font_color=PALETTE["primary_dark"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide, "→ bbox lits, baignoires, plaques, frigo, etc.",
             6.85, 3.45, 5.95, 0.3,
             font_size=10, font_color=PALETTE["primary_dark"], align=PP_ALIGN.CENTER)

    # OCR
    add_rectangle(slide, 0.7, 4.05, 5.95, 0.85, PALETTE["light_lilac"], rounded=True)
    add_text(slide, "OCR (lecture des labels écrits)",
             0.7, 4.15, 5.95, 0.35,
             font_size=12, font_color=PALETTE["primary_dark"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide, "→ confirme le type des pièces (ex : 'Cuisine')",
             0.7, 4.5, 5.95, 0.3,
             font_size=10, font_color=PALETTE["text_dark"], align=PP_ALIGN.CENTER)

    # NFC
    add_rectangle(slide, 6.85, 4.05, 5.95, 0.85, PALETTE["light_lilac"], rounded=True)
    add_text(slide, "Moteur de règles NF C 15-100",
             6.85, 4.15, 5.95, 0.35,
             font_size=12, font_color=PALETTE["primary_dark"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)
    add_text(slide, "→ placement automatique prises + interrupteurs",
             6.85, 4.5, 5.95, 0.3,
             font_size=10, font_color=PALETTE["text_dark"], align=PP_ALIGN.CENTER)

    # Output
    add_rectangle(slide, 4.5, 5.4, 4.3, 0.8, PALETTE["accent_purple"], rounded=True)
    add_text(slide, "Plan annoté + devis automatique",
             4.5, 5.55, 4.3, 0.5,
             font_size=14, font_color=PALETTE["white"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)

    add_text(slide,
             "Légende : violet plein = brique en cours (Mask2Former Stage A) — "
             "violet clair = à faire — lilas = à commencer",
             0.7, 6.6, SLIDE_W_IN - 1.4, 0.6,
             font_size=11, font_color=PALETTE["text_secondary"],
             italic=True, align=PP_ALIGN.CENTER)
    add_footer(slide)


def build_slide_12_calendar(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=12)
    add_section_title(slide, "Calendrier prévisionnel jusqu'à beta",
                      "Roadmap MVP — objectifs et jalons")

    headers = ["Période", "Livrable"]
    rows = [
        ["mi-mai 2026", "Stage A terminé — modèle CubiCasa baseline"],
        ["fin mai", "Annotation FR commencée + YOLO meubles refonte 10 classes"],
        ["mi-juin", "Stage B fine-tune FR terminé — mIoU ≥ 0.55 atteint"],
        ["fin juin", "Brique OCR opérationnelle"],
        ["juillet", "Intégration moteur NFC + UX MVP"],
        ["août", "Tests internes sur cas d'usage réels"],
        ["sept-oct", "Pilotes utilisateurs (3-5 électriciens)"],
        ["mars 2026 (officiel)", "Mise en production BAT IA — beta"],
    ]
    add_table_slide(slide, headers, rows, 1.5, 2.2, 10.3, 4.6,
                    cell_font_size=13)
    add_footer(slide)


def build_slide_13_health(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=13)
    add_section_title(slide, "État technique global",
                      "Synthèse santé du projet")

    headers = ["Indicateur", "État", "Commentaire"]
    rows = [
        ["Architecture pipeline", "✓ Validée", "5 briques, design éprouvé"],
        ["Brique B (segmentation)", "🟡 Stage A 70%", "mIoU 0.51 → cible 0.55"],
        ["Brique A (YOLO objets)", "🟡 v3 OK doors/windows", "Refonte 10 classes prévue"],
        ["OCR", "⚪ À démarrer", "Non bloquant pour Stage B"],
        ["Moteur NFC", "⚪ À écrire", "Code applicatif post-IA"],
        ["Dataset CubiCasa", "✓ Complet", "4 745 plans exportés"],
        ["Dataset FR", "🔴 0 plans", "ACTION PRINCIPALE à venir"],
        ["Infrastructure code", "✓ Stable", "50+ tests automatisés"],
    ]
    add_table_slide(slide, headers, rows, 0.7, 2.2, SLIDE_W_IN - 1.4, 4.5,
                    cell_font_size=12)

    add_text(slide,
             "Risque principal identifié : collecte plans FR. "
             "Action en cours : activation réseau électriciens.",
             0.7, 6.85, SLIDE_W_IN - 1.4, 0.4,
             font_size=11, font_color=PALETTE["error"],
             italic=True, align=PP_ALIGN.CENTER)
    add_footer(slide)


def build_slide_14_conclusion(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide, PALETTE["white"])
    add_header_strip(slide, slide_number=14)
    add_section_title(slide, "Conclusion — à retenir")

    bullets = [
        "Stage A en finition : modèle CubiCasa atteindra son palier sous 24-48h",
        "Tous les bugs majeurs corrigés : training stable, métrique en croissance régulière",
        "Pipeline complet design validé : 5 briques, architecture multi-modèles",
        "Prochain jalon majeur : collecte 150 plans FR + annotation (3-4 semaines)",
        "Risque principal identifié : qualité du dataset FR — gérable via réseau électriciens",
        "Beta mars 2026 reste atteignable",
    ]
    add_bullet_list(slide, bullets, 0.7, 2.4, SLIDE_W_IN - 1.4, 3.5,
                    font_size=16)

    # Bloc Q&A
    add_rectangle(slide, 1.5, 6.0, 10.3, 1.0, PALETTE["accent_purple"], rounded=True)
    add_text(slide, "Questions ?", 1.5, 6.2, 10.3, 0.6,
             font_size=24, font_color=PALETTE["white"],
             bold=True, italic=True, align=PP_ALIGN.CENTER)

    add_footer(slide)


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────
def main():
    prs = Presentation()
    prs.slide_width = Inches(SLIDE_W_IN)
    prs.slide_height = Inches(SLIDE_H_IN)

    # Build all slides
    build_slide_1_cover(prs)
    build_slide_2_role(prs)
    build_slide_3_architecture(prs)
    build_slide_4_taxonomy(prs)
    build_slide_5_dataset(prs)
    build_slide_6_results_global(prs)
    build_slide_7_results_per_class(prs)
    build_slide_8_difficulties(prs)
    build_slide_9_domain_gap(prs)
    build_slide_10_stage_b_roadmap(prs)
    build_slide_11_pipeline(prs)
    build_slide_12_calendar(prs)
    build_slide_13_health(prs)
    build_slide_14_conclusion(prs)

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "presentations"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "avancement_stage_a_2026_05_11.pptx"
    prs.save(str(out_path))
    print(f"✓ Generated: {out_path}")
    print(f"  Open with: open '{out_path}'")


if __name__ == "__main__":
    main()
