from __future__ import annotations
from datetime import date
from decimal import Decimal


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


def test_paiement_creation(db_session):
    from src.facturation.models import Paiement, ModePaiement
    a, c, f = _facture(db_session)
    p = Paiement(facture_id=f.id, montant=Decimal("100.00"),
        date=date(2026, 6, 10), mode=ModePaiement.VIREMENT,
        reference="VIR-12345")
    db_session.add(p); db_session.commit(); db_session.refresh(p)
    assert p.id is not None
    assert p.mode == ModePaiement.VIREMENT
