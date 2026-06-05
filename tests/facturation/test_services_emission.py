from __future__ import annotations
from datetime import date
from decimal import Decimal
import pytest


def _setup(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureLigne, FactureType,
        FormeJuridique, TypeClient, CategorieTVA, UniteFacturation,
    )
    a = Artisan(raison_sociale="batIA",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014",
        mentions_assurance_decennale="MAAF n°ABC")
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="C", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    s.add(c); s.commit(); s.refresh(c)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="Test")
    f.lignes.append(FactureLigne(ordre=1, designation="X",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=Decimal("100"), montant_ht_ligne=Decimal("100"),
        taux_tva=Decimal("20"), categorie_tva=CategorieTVA.STANDARD))
    f.montant_ht = Decimal("100"); f.total_tva = Decimal("20")
    f.montant_ttc = Decimal("120"); f.montant_du_ttc = Decimal("120")
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_emit_facture_passe_brouillon_a_emise(db_session, tmp_path):
    from src.facturation.services.emission import emit_facture
    from src.facturation.models import FactureStatut
    _, _, f = _setup(db_session)
    f2 = emit_facture(db_session, f.id, archives_root=tmp_path)
    assert f2.statut == FactureStatut.EMISE
    assert f2.pdf_path is not None
    assert f2.hash_sha256 is not None
    assert len(f2.hash_sha256) == 64


def test_emit_facture_genere_pdf_a3(db_session, tmp_path):
    from src.facturation.services.emission import emit_facture
    from pathlib import Path
    _, _, f = _setup(db_session)
    emit_facture(db_session, f.id, archives_root=tmp_path)
    db_session.refresh(f)
    p = Path(f.pdf_path)
    assert p.exists()
    assert p.read_bytes().startswith(b"%PDF-")


def test_emit_facture_deja_emise_refuse(db_session, tmp_path):
    from src.facturation.services.emission import emit_facture
    _, _, f = _setup(db_session)
    emit_facture(db_session, f.id, archives_root=tmp_path)
    with pytest.raises(ValueError, match="brouillon"):
        emit_facture(db_session, f.id, archives_root=tmp_path)
