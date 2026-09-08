"""Tests du modèle Artisan : création, validation SIRET, dérivation SIREN."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError


def test_artisan_creation_minimale(db_session):
    from src.facturation.models.artisan import Artisan
    from src.facturation.models.enums import FormeJuridique

    artisan = Artisan(
        raison_sociale="batIA Élec",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234",
        numero_tva_intra="FR12123456789",
        adresse_rue="1 rue de la République",
        adresse_cp="75001",
        adresse_ville="Paris",
        adresse_pays="FR",
        email="hadrien@batia.example",
        iban="FR7612345987650123456789014",
    )
    db_session.add(artisan)
    db_session.commit()
    db_session.refresh(artisan)

    assert artisan.id is not None
    assert artisan.forme_juridique == FormeJuridique.EI


def test_artisan_siret_unique(db_session):
    from src.facturation.models.artisan import Artisan
    from src.facturation.models.enums import FormeJuridique

    base = dict(
        raison_sociale="batIA", forme_juridique=FormeJuridique.SARL,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="1 rue", adresse_cp="75001", adresse_ville="Paris",
        adresse_pays="FR", email="a@b.com", iban="FR7612345987650123456789014",
    )
    db_session.add(Artisan(**base))
    db_session.commit()
    db_session.add(Artisan(**{**base, "raison_sociale": "Autre"}))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_artisan_siret_doit_etre_14_chiffres(db_session):
    from src.facturation.models.artisan import _validate_siret
    with pytest.raises(ValueError, match="14 chiffres"):
        _validate_siret("1234")
    with pytest.raises(ValueError, match="14 chiffres"):
        _validate_siret("abcdefghijklmn")
    assert _validate_siret("12345678901234") == "12345678901234"


def test_artisan_iban_normalize(db_session):
    from src.facturation.models.artisan import _normalize_iban
    assert _normalize_iban("FR76 1234 5987 6501 2345 6789 014") == "FR7612345987650123456789014"
    assert _normalize_iban("fr7612345987650123456789014") == "FR7612345987650123456789014"
