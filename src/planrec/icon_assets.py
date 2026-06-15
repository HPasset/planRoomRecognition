"""Helpers partagés pour charger les pictogrammes d'usage (assets/icons/) et
résoudre le picto le plus adapté à un circuit. Utilisé par etiquettes_renderer
et schema_unifilaire — logique pure, aucun import Streamlit/React.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.graphics.shapes import Drawing
from svglib.svglib import svg2rlg

from src.planrec.nfc_tableau import Circuit, CircuitType

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def load_icon_as_drawing(svg_id: str) -> Drawing:
    """Charge assets/icons/<svg_id>.svg en reportlab Drawing.

    Substitue 'currentColor' par '#000000' (svglib ne sait pas l'évaluer).

    Raises:
        FileNotFoundError: si le fichier n'existe pas.
    """
    svg_path = ICONS_DIR / f"{svg_id}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(
            f"Icône introuvable : {svg_path}. "
            f"Liste autorisée = {sorted(p.stem for p in ICONS_DIR.glob('*.svg'))}"
        )
    raw = svg_path.read_text(encoding="utf-8")
    raw = raw.replace("currentColor", "#000000")
    return svg2rlg(BytesIO(raw.encode("utf-8")))


# Mapping CircuitType -> svg_id (fallback large).
CIRCUIT_TYPE_TO_SVG_ID: dict[CircuitType, str] = {
    CircuitType.LIGHTING: "light",
    CircuitType.SOCKET: "socket",
    CircuitType.KITCHEN_SPECIAL: "cooktop",
    CircuitType.LAUNDRY: "washing_machine",
    CircuitType.BOILER: "boiler",
    CircuitType.HEATING: "convector",
    CircuitType.TOWEL_WARMER: "towel_warmer",
}

# Mapping prioritaire sur le préfixe du label (sous-types cuisine/buanderie).
LABEL_PREFIX_TO_SVG_ID: dict[str, str] = {
    "Plaque cuisson": "cooktop",
    "Four": "oven",
    "Lave-vaisselle": "dishwasher",
    "Lave-linge": "washing_machine",
    "Sèche-linge": "dryer",
    "Chaudière": "boiler",
    "Cumulus": "boiler",
    "Sèche-serviettes": "towel_warmer",
    "Chauffage": "convector",
    "Éclairage": "light",
    "Prises": "socket",
}


def resolve_svg_id_for_circuit(circuit: Circuit) -> str:
    """Picto le plus adapté : priorité au préfixe du label, fallback CircuitType."""
    label = circuit.label or ""
    for prefix, svg_id in LABEL_PREFIX_TO_SVG_ID.items():
        if label.startswith(prefix):
            return svg_id
    return CIRCUIT_TYPE_TO_SVG_ID.get(circuit.type, "special_feed")
