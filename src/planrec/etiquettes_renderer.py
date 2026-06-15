"""Renderer pour les étiquettes PDF imprimables 1:1 à coller dans le
porte-étiquettes du tableau électrique physique. Conçu pour A4 paysage avec
des modules DIN 17.5 mm standards FR (Hager-compatible, Schneider, Legrand).

Voir docs/superpowers/specs/2026-06-03-etiquettes-tableau-design.md
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.graphics.shapes import Drawing
from svglib.svglib import svg2rlg

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def load_icon_as_drawing(svg_id: str) -> Drawing:
    """Charge un fichier .svg depuis assets/icons/ et le convertit en
    reportlab Drawing prêt à être placé sur un Canvas.

    Substitue 'currentColor' par '#000000' avant le parsing : svglib ne
    sait pas évaluer currentColor (qui nécessite un contexte CSS parent
    inexistant côté reportlab), donc on injecte la couleur cible (noir
    pour impression monochrome) à la main.

    Args:
        svg_id: nom du fichier sans extension (ex. 'socket', 'light')

    Returns:
        reportlab.graphics.shapes.Drawing prêt à être placé.

    Raises:
        FileNotFoundError: si le fichier .svg n'existe pas dans le dossier.
    """
    svg_path = ICONS_DIR / f"{svg_id}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(
            f"Icône introuvable : {svg_path}. "
            f"Liste autorisée = {sorted(p.stem for p in ICONS_DIR.glob('*.svg'))}"
        )
    raw = svg_path.read_text(encoding="utf-8")
    raw = raw.replace("currentColor", "#000000")
    drawing = svg2rlg(BytesIO(raw.encode("utf-8")))
    return drawing


# Constantes de layout (en millimètres, A4 paysage)
INDEX_COL_W_MM = 6.0           # colonne index rangée (1, 2, 3, ...)
ID_CELL_W_MM = 35.0            # cellule "Interrupteur différentiel" (2 modules DIN)
DISJONCTEUR_CELL_W_MM = 17.5   # cellule disjoncteur standard (1 module DIN)
CARTOUCHE_MIN_W_MM = 30.0      # largeur minimale du cartouche batIA en fin de ligne


def compute_strip_widths(
    n_disjoncteurs: int,
    page_usable_width_mm: float,
) -> dict:
    """Calcule la largeur de chaque cellule d'une rangée RCD en mm.

    La rangée = index + cellule ID + n_disjoncteurs cellules Qn + cartouche batIA
    en fin de ligne. Le cartouche occupe l'espace restant (>= 30 mm minimum).

    Args:
        n_disjoncteurs: nombre de disjoncteurs effectivement présents sur le RCD
                        (typiquement 1 à 7, max 8 avec overflow géré ailleurs)
        page_usable_width_mm: largeur imprimable de la page (zone hors marges)

    Returns:
        dict avec clés "index", "id", "disjoncteurs" (list[float]), "cartouche".
    """
    disjoncteurs_widths = [DISJONCTEUR_CELL_W_MM] * n_disjoncteurs
    consumed = INDEX_COL_W_MM + ID_CELL_W_MM + sum(disjoncteurs_widths)
    cartouche_w = page_usable_width_mm - consumed
    return {
        "index": INDEX_COL_W_MM,
        "id": ID_CELL_W_MM,
        "disjoncteurs": disjoncteurs_widths,
        "cartouche": cartouche_w,
    }
