from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal


def _facture_brouillon(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureType,
        FormeJuridique, TypeClient,
    )
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014",
        delai_grace_jours=3)
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


def test_mark_envoyee_depuis_emise(db_session):
    from src.facturation.services.statuts import mark_envoyee
    from src.facturation.models import FactureStatut
    a, c, f = _facture_brouillon(db_session)
    f.statut = FactureStatut.EMISE
    db_session.commit()
    f2 = mark_envoyee(db_session, f.id)
    assert f2.statut == FactureStatut.ENVOYEE
    assert f2.date_envoi is not None


def test_mark_envoyee_depuis_brouillon_refuse(db_session):
    import pytest
    from src.facturation.services.statuts import mark_envoyee
    a, c, f = _facture_brouillon(db_session)
    with pytest.raises(ValueError, match="emise"):
        mark_envoyee(db_session, f.id)


def test_is_en_retard_calcul(db_session):
    from src.facturation.services.statuts import is_en_retard
    from src.facturation.models import FactureStatut
    a, c, f = _facture_brouillon(db_session)
    f.statut = FactureStatut.ENVOYEE
    f.date_echeance = date.today() - timedelta(days=10)
    db_session.commit()
    assert is_en_retard(f, today=date.today()) is True


def test_is_en_retard_pas_envoyee(db_session):
    from src.facturation.services.statuts import is_en_retard
    a, c, f = _facture_brouillon(db_session)
    f.date_echeance = date.today() - timedelta(days=10)
    db_session.commit()
    assert is_en_retard(f, today=date.today()) is False


def test_is_en_retard_grace_period(db_session):
    from src.facturation.services.statuts import is_en_retard
    from src.facturation.models import FactureStatut
    a, c, f = _facture_brouillon(db_session)
    f.statut = FactureStatut.ENVOYEE
    f.date_echeance = date.today() - timedelta(days=2)
    db_session.commit()
    assert is_en_retard(f, today=date.today()) is False


def test_jours_de_retard(db_session):
    from src.facturation.services.statuts import jours_de_retard
    from src.facturation.models import FactureStatut
    a, c, f = _facture_brouillon(db_session)
    f.statut = FactureStatut.ENVOYEE
    f.date_echeance = date.today() - timedelta(days=10)
    db_session.commit()
    assert jours_de_retard(f, today=date.today()) == 7
