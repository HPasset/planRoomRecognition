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
