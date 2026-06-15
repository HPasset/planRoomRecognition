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
