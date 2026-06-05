from __future__ import annotations
from datetime import date
from pathlib import Path


def _facture(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureType,
        FormeJuridique, TypeClient,
    )
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="C", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    s.add(c); s.commit(); s.refresh(c)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="X")
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_compute_sha256():
    from src.facturation.pdf.archive import compute_sha256
    h = compute_sha256(b"hello")
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_archive_pdf_ecrit_fichier(db_session, tmp_path):
    from src.facturation.pdf.archive import archive_pdf
    _, _, f = _facture(db_session)
    pdf = b"%PDF-fake"
    path, h = archive_pdf(pdf, f, archives_root=tmp_path)
    assert path.exists()
    assert path.read_bytes() == pdf
    assert path.relative_to(tmp_path) == Path(f.artisan_id) / "2026" / "FAC-2026-0001.pdf"
    assert len(h) == 64
