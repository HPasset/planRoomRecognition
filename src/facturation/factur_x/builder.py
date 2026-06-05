"""Construction du XML CII EN16931 depuis une Facture SQLAlchemy.

Profile : COMFORT (EN16931). Conforme à la réforme française 2026 (process A1).

Note SQLite : les enums stockés en String reviennent parfois comme str brut
au lieu d'instances Enum après load DB. Le builder normalise.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from lxml import etree

from src.facturation.models import (
    CategorieTVA, Facture, FactureType, UniteFacturation,
)
from src.facturation.services.totals import compute_facture_totals


_TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["xml"]),
    trim_blocks=True, lstrip_blocks=True,
)


def _format_date(d: date) -> str:
    """Format CII (UN/EDIFACT code 102) : YYYYMMDD."""
    return d.strftime("%Y%m%d")


def _enum_value(v, enum_cls):
    """Renvoie .value pour un enum, ou la str telle quelle si SQLite l'a dénaturée."""
    if hasattr(v, "value"):
        return v.value
    return str(v)


def build_xml_cii(facture: Facture) -> bytes:
    """Construit le XML CII conforme EN16931 depuis la Facture."""
    totals = compute_facture_totals(facture.lignes)
    template = _env.get_template("cii.xml.j2")

    # Pré-extrait les enum values des lignes (Jinja a du mal avec les attrs str-enum SQLite)
    ligne_unite = {l.ordre: _enum_value(l.unite, UniteFacturation) for l in facture.lignes}
    ligne_categorie = {l.ordre: _enum_value(l.categorie_tva, CategorieTVA) for l in facture.lignes}
    facture_type_value = _enum_value(facture.type, FactureType)

    rendered = template.render(
        facture=facture, totals=totals, format_date=_format_date,
        ligne_unite=ligne_unite, ligne_categorie=ligne_categorie,
        facture_type_value=facture_type_value,
    )
    root = etree.fromstring(rendered.encode("utf-8"))
    return etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", pretty_print=True,
    )
