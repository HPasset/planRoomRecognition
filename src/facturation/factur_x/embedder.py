"""Embarquement du XML Factur-X dans un PDF/A-3 via la lib facturx."""
from __future__ import annotations

from facturx import generate_from_binary


def embed_xml_in_pdf(pdf_bytes: bytes, xml_bytes: bytes,
                     level: str = "en16931") -> bytes:
    """Renvoie un PDF/A-3 contenant le XML CII embarqué.

    level : 'minimum' | 'basicwl' | 'basic' | 'en16931' | 'extended'
    flavor : 'factur-x' (FR) — la lib auto-détecte.
    """
    pdf_a3 = generate_from_binary(
        pdf_bytes,
        xml_bytes,
        check_xsd=False,
        check_schematron=False,
        flavor="factur-x",
        level=level,
    )
    return pdf_a3
