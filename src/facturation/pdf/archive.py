"""Archivage des PDF émis + calcul hash SHA-256 (intégrité)."""
from __future__ import annotations

import hashlib
from pathlib import Path

from src.facturation.models import Facture


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def archive_pdf(pdf_bytes: bytes, facture: Facture,
                archives_root: Path) -> tuple[Path, str]:
    """Écrit le PDF dans data/factures/<artisan>/<annee>/<numero>.pdf.

    Renvoie (path, hash_hex).
    """
    annee = facture.date_emission.year
    folder = archives_root / facture.artisan_id / str(annee)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{facture.numero}.pdf"
    out.write_bytes(pdf_bytes)
    return out, compute_sha256(pdf_bytes)
