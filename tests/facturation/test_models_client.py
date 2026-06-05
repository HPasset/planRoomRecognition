from __future__ import annotations
import pytest


def _make_artisan(db_session):
    from src.facturation.models import Artisan, FormeJuridique
    a = Artisan(
        raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_client_particulier_creation(db_session):
    from src.facturation.models import Client, TypeClient
    a = _make_artisan(db_session)
    c = Client(
        artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Jean Dupont",
        adresse_rue="2 av des Lilas", adresse_cp="92100",
        adresse_ville="Boulogne", adresse_pays="FR",
        email="dupont@example.com",
    )
    db_session.add(c); db_session.commit(); db_session.refresh(c)
    assert c.id is not None
    assert c.siret is None
    assert c.type == TypeClient.PARTICULIER


def test_client_professionnel_avec_siret(db_session):
    from src.facturation.models import Client, TypeClient
    a = _make_artisan(db_session)
    c = Client(
        artisan_id=a.id, type=TypeClient.PROFESSIONNEL,
        nom_ou_raison="SCI Patrimoine",
        siret="98765432109876", numero_tva_intra="FR98987654321",
        adresse_rue="r", adresse_cp="75002", adresse_ville="P",
        adresse_pays="FR", email="contact@sci.fr",
    )
    db_session.add(c); db_session.commit(); db_session.refresh(c)
    assert c.siret == "98765432109876"


def test_client_fk_artisan_obligatoire(db_session):
    from src.facturation.models import Client, TypeClient
    from sqlalchemy.exc import IntegrityError
    c = Client(
        type=TypeClient.PARTICULIER, nom_ou_raison="X",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="x@x.com",
    )
    db_session.add(c)
    with pytest.raises(IntegrityError):
        db_session.commit()
