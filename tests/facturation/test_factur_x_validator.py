from __future__ import annotations
import pytest


def test_validate_xml_malforme_raise():
    from src.facturation.factur_x.validator import (
        validate_minimal, FacturXValidationError,
    )
    with pytest.raises(FacturXValidationError, match="malformé"):
        validate_minimal(b"<not valid xml>")


def test_validate_xml_minimal_manque_champs():
    from src.facturation.factur_x.validator import (
        validate_minimal, FacturXValidationError,
    )
    with pytest.raises(FacturXValidationError, match="manquants"):
        validate_minimal(b"<?xml version='1.0'?><root/>")


def test_validate_xml_genere_passe(db_session):
    """Le XML généré par le builder doit passer la validation minimale."""
    from src.facturation.factur_x.builder import build_xml_cii
    from src.facturation.factur_x.validator import validate_minimal
    from datetime import date
    from decimal import Decimal
    from src.facturation.models import (
        Artisan, Client, Facture, FactureLigne, FactureType,
        FormeJuridique, TypeClient, CategorieTVA, UniteFacturation,
    )
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Cli", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    db_session.add(c); db_session.commit(); db_session.refresh(c)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="X",
        montant_ht=Decimal("100"), total_tva=Decimal("20"),
        montant_ttc=Decimal("120"), montant_du_ttc=Decimal("120"))
    f.lignes.append(FactureLigne(ordre=1, designation="X",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=Decimal("100"), montant_ht_ligne=Decimal("100"),
        taux_tva=Decimal("20"), categorie_tva=CategorieTVA.STANDARD))
    db_session.add(f); db_session.commit(); db_session.refresh(f)

    xml = build_xml_cii(f)
    validate_minimal(xml)  # ne doit pas lever
