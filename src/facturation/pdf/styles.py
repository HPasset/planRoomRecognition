"""Styles reportlab partagés (couleurs, polices, marges)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm


PAGE_SIZE = A4
MARGIN = 15 * mm

BATIA_BLUE = colors.HexColor("#1f4e79")
BATIA_GREY = colors.HexColor("#666666")


def get_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title", parent=base["Heading1"], fontSize=18, textColor=BATIA_BLUE,
        ),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontSize=9,
            leading=11),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontSize=7,
            leading=9, textColor=BATIA_GREY),
    }
