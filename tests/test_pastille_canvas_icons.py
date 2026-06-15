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
    """Liste les SVG pictogrammes (exclut batia_logo.svg qui suit une
    charte différente puisque c'est un logo de marque, pas un picto)."""
    return sorted(
        p for p in ICONS_DIR.glob("*.svg")
        if p.name != "batia_logo.svg"
    )


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


def test_each_equipment_type_has_matching_icon():
    """Pour chaque EquipmentType supporté par batIA (sauf alias internes),
    il existe un fichier .svg correspondant dans assets/icons/.

    Garde-fou : si on ajoute un nouveau EquipmentType, on doit aussi ajouter
    son icône, sinon le canvas affichera le fallback '?' à la place.
    """
    from src.planrec.nfc_equipments import EQUIP_TYPES

    svg_files = {p.stem for p in _list_svg_files()}
    # Convertir les svg_id du registre EQUIP_TYPES en stems de fichier
    expected = {info["svg_id"] for info in EQUIP_TYPES.values()}
    # Le set d'icônes peut contenir des fichiers en plus (ex. 'differential'
    # uniquement utilisé par le PDF étiquettes) mais doit couvrir tous
    # les svg_id du registre.
    # Le composant React (PastilleCanvas.tsx) résout chaque svg_id vers un
    # fichier .svg via une lookup explicite : la plupart des svg_id matchent
    # directement le stem du fichier, mais quelques-uns suivent la convention
    # "sans underscore" côté Python alors que le fichier porte un underscore.
    # On encode ici le même mapping que la lookup TSX pour rester aligné.
    SVG_ID_TO_FILENAME = {
        "washingmachine": "washing_machine",
        "towelwarmer": "towel_warmer",
        "specfeed": "special_feed",
    }
    for required in expected:
        filename = SVG_ID_TO_FILENAME.get(required, required)
        assert filename in svg_files, (
            f"svg_id '{required}' du registre EQUIP_TYPES n'a pas de fichier "
            f"correspondant ('{filename}.svg') dans assets/icons/. Fichiers "
            f"disponibles : {sorted(svg_files)}"
        )


def test_differential_icon_exists_for_etiquettes():
    """L'icône 'differential' est requise pour le PDF étiquettes (cellule ID
    sur chaque rangée RCD), même si elle n'est pas dans EQUIP_TYPES."""
    svg_files = {p.stem for p in _list_svg_files()}
    assert "differential" in svg_files, (
        "differential.svg manquant — utilisé par le PDF étiquettes (cellule "
        "ID 'Interrupteur différentiel')"
    )
