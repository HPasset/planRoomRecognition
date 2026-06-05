from __future__ import annotations
from datetime import date
from decimal import Decimal
import pytest


def _devis(s, statut=None):
    from src.facturation.models import (
        Artisan, Client, DevisDB, FormeJuridique, TypeClient, DevisStatut,
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
    d = DevisDB(artisan_id=a.id, client_id=c.id, numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X", devis_global_json={},
        montant_ht=Decimal("1000"), total_tva=Decimal("200"),
        montant_ttc=Decimal("1200"),
        statut=statut or DevisStatut.ACCEPTE)
    s.add(d); s.commit(); s.refresh(d)
    return a, c, d


def test_create_avenant_devis_accepte(db_session):
    from src.facturation.services.avenants import create_avenant
    a, c, d = _devis(db_session)
    av = create_avenant(db_session, devis_id=d.id, objet="Ajout prises",
        lignes_supplementaires={"prises": 3},
        montant_ht_supplementaire=Decimal("75"))
    assert av.numero.startswith("AVE-")
    assert av.date_acceptation is None


def test_create_avenant_devis_brouillon_refuse(db_session):
    from src.facturation.services.avenants import create_avenant
    from src.facturation.models import DevisStatut
    a, c, d = _devis(db_session, statut=DevisStatut.BROUILLON)
    with pytest.raises(ValueError, match="accepte"):
        create_avenant(db_session, devis_id=d.id, objet="X",
            lignes_supplementaires={}, montant_ht_supplementaire=Decimal("0"))


def test_accept_avenant(db_session):
    from src.facturation.services.avenants import create_avenant, accept_avenant
    a, c, d = _devis(db_session)
    av = create_avenant(db_session, devis_id=d.id, objet="X",
        lignes_supplementaires={}, montant_ht_supplementaire=Decimal("0"))
    accepted = accept_avenant(db_session, av.id)
    assert accepted.date_acceptation is not None
