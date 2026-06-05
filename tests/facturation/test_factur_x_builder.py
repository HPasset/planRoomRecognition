"""Tests du builder XML CII EN16931 depuis Facture."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from lxml import etree


def _full_facture(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureLigne, FactureType,
        FormeJuridique, TypeClient, CategorieTVA, UniteFacturation,
    )
    a = Artisan(raison_sociale="batIA Élec",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="1 rue de la République",
        adresse_cp="75001", adresse_ville="Paris",
        adresse_pays="FR", email="h@b.com",
        iban="FR7612345987650123456789014",
        delai_grace_jours=3)
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Jean Dupont",
        adresse_rue="2 av des Lilas", adresse_cp="92100",
        adresse_ville="Boulogne", adresse_pays="FR",
        email="dupont@example.com")
    s.add(c); s.commit(); s.refresh(c)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="Installation électrique 100m²",
        montant_ht=Decimal("450.00"), total_tva=Decimal("90.00"),
        montant_ttc=Decimal("540.00"), montant_du_ttc=Decimal("540.00"))
    f.lignes.append(FactureLigne(
        ordre=1, designation="Prise 16A", quantite=Decimal("10"),
        unite=UniteFacturation.PIECE, prix_unitaire_ht=Decimal("25.00"),
        montant_ht_ligne=Decimal("250.00"),
        taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD))
    f.lignes.append(FactureLigne(
        ordre=2, designation="Interrupteur va-et-vient",
        quantite=Decimal("5"), unite=UniteFacturation.PIECE,
        prix_unitaire_ht=Decimal("40.00"), montant_ht_ligne=Decimal("200.00"),
        taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD))
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_build_xml_returns_bytes(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    assert isinstance(xml, bytes)
    assert b"CrossIndustryInvoice" in xml


def test_build_xml_contient_numero(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    root = etree.fromstring(xml)
    ns = {
        "rsm": "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100",
        "ram": "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100",
    }
    invoice_ids = root.xpath("//rsm:ExchangedDocument/ram:ID", namespaces=ns)
    assert len(invoice_ids) == 1
    assert invoice_ids[0].text == "FAC-2026-0001"


def test_build_xml_contient_type_code_380(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    assert b"<ram:TypeCode>380</ram:TypeCode>" in xml


def test_build_xml_contient_seller_siret(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    assert b"12345678901234" in xml


def test_build_xml_contient_buyer_nom(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    assert b"Jean Dupont" in xml


def test_build_xml_lignes_avec_montants(db_session):
    from src.facturation.factur_x.builder import build_xml_cii
    _, _, f = _full_facture(db_session)
    xml = build_xml_cii(f)
    assert b"Prise 16A" in xml
    assert b"450.00" in xml or b"450" in xml
