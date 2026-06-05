from __future__ import annotations
from datetime import date
from decimal import Decimal
import pytest


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
        objet="X",
        montant_ht=Decimal("100"), total_tva=Decimal("20"),
        montant_ttc=Decimal("120"), montant_du_ttc=Decimal("120"))
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_paiement_total_passe_a_payee(db_session):
    from src.facturation.services.paiements import register_paiement
    from src.facturation.models import ModePaiement, FactureStatut
    a, c, f = _facture(db_session)
    register_paiement(db_session, f.id, Decimal("120"), ModePaiement.VIREMENT)
    db_session.refresh(f)
    assert f.statut == FactureStatut.PAYEE


def test_paiement_partiel_passe_a_partiellement_payee(db_session):
    from src.facturation.services.paiements import register_paiement
    from src.facturation.models import ModePaiement, FactureStatut
    a, c, f = _facture(db_session)
    register_paiement(db_session, f.id, Decimal("50"), ModePaiement.VIREMENT)
    db_session.refresh(f)
    assert f.statut == FactureStatut.PARTIELLEMENT_PAYEE


def test_paiement_facture_annulee_refuse(db_session):
    from src.facturation.services.paiements import register_paiement
    from src.facturation.models import ModePaiement, FactureStatut
    a, c, f = _facture(db_session)
    f.statut = FactureStatut.ANNULEE
    db_session.commit()
    with pytest.raises(ValueError, match="annulée"):
        register_paiement(db_session, f.id, Decimal("100"), ModePaiement.VIREMENT)
