"""Tests de conformité du set de pictogrammes batIA.

Ces tests gardent la charte stylistique (cf. assets/icons/_README.md) et
servent de gate avant chaque ajout/modif d'un picto. Ils sont volontairement
permissifs au début (set vide accepté), et deviennent contraignants à
mesure que les 14 icônes prévues par le spec sont créées.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent.parent / "src" / "planrec" / "assets" / "icons"

# SVG namespace pour les éléments parsés via ElementTree
SVG_NS = "http://www.w3.org/2000/svg"


def _list_svg_files() -> list[Path]:
    return sorted(ICONS_DIR.glob("*.svg"))


def test_icons_directory_exists():
    """Le dossier assets/icons/ existe et est dans le bon emplacement."""
    assert ICONS_DIR.is_dir(), f"Dossier introuvable : {ICONS_DIR}"


def test_each_svg_parses_as_xml():
    """Tous les .svg parsent comme XML valide (pas de fichier corrompu)."""
    for svg in _list_svg_files():
        try:
            ET.parse(svg)
        except ET.ParseError as e:
            raise AssertionError(f"{svg.name} n'est pas un XML valide : {e}")


def test_each_svg_has_correct_viewbox():
    """viewBox='0 0 40 40' obligatoire pour cohérence d'échelle."""
    for svg in _list_svg_files():
        tree = ET.parse(svg)
        root = tree.getroot()
        viewbox = root.get("viewBox")
        assert viewbox == "0 0 40 40", (
            f"{svg.name} : viewBox attendu '0 0 40 40', trouvé '{viewbox}'"
        )


def test_each_svg_uses_currentcolor_or_no_hardcoded_color():
    """Aucun stroke/fill avec couleur hardcodée hex/rgb. Seul 'currentColor',
    'white', 'none' ou pas d'attribut sont autorisés."""
    hex_or_rgb = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgb\()")
    for svg in _list_svg_files():
        content = svg.read_text()
        # cherche les motifs stroke="..." ou fill="..."
        for match in re.finditer(r'(stroke|fill)\s*=\s*"([^"]+)"', content):
            attr, value = match.group(1), match.group(2)
            if value in ("currentColor", "white", "none"):
                continue
            assert not hex_or_rgb.match(value), (
                f"{svg.name} : couleur hardcodée '{attr}={value}' interdite "
                f"(utilise 'currentColor' ou 'white')"
            )
