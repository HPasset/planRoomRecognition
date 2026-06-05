"""Tests du service Artisan : get_or_create_default, upsert."""
from __future__ import annotations


def test_get_default_artisan_aucun(db_session):
    from src.facturation.services.artisan import get_default_artisan
    assert get_default_artisan(db_session) is None


def test_create_or_update_artisan(db_session):
    from src.facturation.services.artisan import create_or_update_artisan
    from src.facturation.models import FormeJuridique

    payload = dict(
        raison_sociale="batIA Élec",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234",
        numero_tva_intra="FR12123456789",
        adresse_rue="1 rue", adresse_cp="75001", adresse_ville="Paris",
        adresse_pays="FR", email="h@b.com",
        iban="FR7612345987650123456789014",
    )
    a = create_or_update_artisan(db_session, **payload)
    assert a.id is not None
    assert a.raison_sociale == "batIA Élec"

    a2 = create_or_update_artisan(db_session, **{**payload, "raison_sociale": "batIA Élec 2"})
    assert a2.id == a.id
    assert a2.raison_sociale == "batIA Élec 2"


def test_get_default_artisan_apres_creation(db_session):
    from src.facturation.services.artisan import (
        create_or_update_artisan, get_default_artisan,
    )
    from src.facturation.models import FormeJuridique
    create_or_update_artisan(
        db_session,
        raison_sociale="X", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="e@e.com",
        iban="FR7612345987650123456789014",
    )
    a = get_default_artisan(db_session)
    assert a is not None
