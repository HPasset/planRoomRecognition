"""Orchestrateur : émission complète d'une facture (XML + PDF + embed + archive)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.factur_x.builder import build_xml_cii
from src.facturation.factur_x.embedder import embed_xml_in_pdf
from src.facturation.factur_x.validator import validate_minimal
from src.facturation.models import (
    ActionAudit, Facture, FactureStatut,
)
from src.facturation.pdf.archive import archive_pdf, compute_sha256
from src.facturation.pdf.renderer import render_facture_pdf
from src.facturation.services.audit import log_audit


def _default_archives_root() -> Path:
    from src.facturation.db import PROJECT_ROOT
    return PROJECT_ROOT / "data" / "factures"


def _normalize_statut(value):
    if isinstance(value, FactureStatut):
        return value
    return FactureStatut(value)


def emit_facture(session: Session, facture_id: str,
                 archives_root: Optional[Path] = None) -> Facture:
    """Pipeline complet d'émission :
    1. Vérifie statut == brouillon
    2. Build XML CII + validate
    3. Render PDF visuel
    4. Embed XML dans PDF/A-3
    5. Archive PDF + calcule hash SHA-256
    6. Update Facture (pdf_path, hash, statut emise)
    7. Audit log EMISSION
    """
    facture = session.get(Facture, facture_id)
    if facture is None:
        raise ValueError(f"Facture {facture_id} introuvable")
    if _normalize_statut(facture.statut) != FactureStatut.BROUILLON:
        raise ValueError(
            f"Facture doit être 'brouillon' pour être émise, "
            f"actuel : {facture.statut}"
        )

    archives_root = archives_root or _default_archives_root()

    xml = build_xml_cii(facture)
    validate_minimal(xml)
    pdf_visuel = render_facture_pdf(facture)
    pdf_a3 = embed_xml_in_pdf(pdf_visuel, xml, level="en16931")

    path, _ = archive_pdf(pdf_a3, facture, archives_root)
    hash_hex = compute_sha256(pdf_a3)

    xml_path = path.with_suffix(".xml")
    xml_path.write_bytes(xml)

    facture.pdf_path = str(path)
    facture.facturx_xml_path = str(xml_path)
    facture.hash_sha256 = hash_hex
    facture.statut = FactureStatut.EMISE
    session.commit(); session.refresh(facture)

    log_audit(session, facture.artisan_id, "Facture", facture.id,
              ActionAudit.EMISSION,
              details={"numero": facture.numero, "hash": hash_hex,
                       "pdf_path": str(path)})
    return facture
