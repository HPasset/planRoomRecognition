from __future__ import annotations
from datetime import date
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader


def _facture_complete(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureLigne, FactureType,
        FormeJuridique, TypeClient, CategorieTVA, UniteFacturation,
    )
    a = Artisan(raison_sociale="batIA Élec",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="1 rue de la République",
        adresse_cp="75001", adresse_ville="Paris", adresse_pays="FR",
        telephone="0142000000", email="h@b.com",
        iban="FR7612345987650123456789014", bic="BNPAFRPP",
        nom_banque="BNP Paribas",
        mentions_assurance_decennale="MAAF Assurances n°ABC-12345 — France entière",
        delai_grace_jours=3)
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Jean Dupont", adresse_rue="2 av des Lilas",
        adresse_cp="92100", adresse_ville="Boulogne", adresse_pays="FR",
        email="dupont@example.com")
    s.add(c); s.commit(); s.refresh(c)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="Installation électrique 100m²",
        montant_ht=Decimal("450.00"), total_tva=Decimal("90.00"),
        montant_ttc=Decimal("540.00"), montant_du_ttc=Decimal("540.00"),
        conditions_paiement="Paiement à 30 jours fin de mois.")
    f.lignes.append(FactureLigne(ordre=1, designation="Prise 16A",
        quantite=Decimal("10"), unite=UniteFacturation.PIECE,
        prix_unitaire_ht=Decimal("25.00"), montant_ht_ligne=Decimal("250.00"),
        taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD))
    f.lignes.append(FactureLigne(ordre=2, designation="Interrupteur",
        quantite=Decimal("5"), unite=UniteFacturation.PIECE,
        prix_unitaire_ht=Decimal("40.00"), montant_ht_ligne=Decimal("200.00"),
        taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD))
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_render_pdf_bytes(db_session):
    from src.facturation.pdf.renderer import render_facture_pdf
    _, _, f = _facture_complete(db_session)
    pdf = render_facture_pdf(f)
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-")


def test_render_pdf_parsing(db_session):
    from src.facturation.pdf.renderer import render_facture_pdf
    _, _, f = _facture_complete(db_session)
    pdf = render_facture_pdf(f)
    reader = PdfReader(BytesIO(pdf))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "FAC-2026-0001" in text
    assert "Jean Dupont" in text
    assert "batIA" in text


def test_render_pdf_mentions_legales(db_session):
    from src.facturation.pdf.renderer import render_facture_pdf
    _, _, f = _facture_complete(db_session)
    pdf = render_facture_pdf(f)
    reader = PdfReader(BytesIO(pdf))
    full = "\n".join(p.extract_text() for p in reader.pages)
    assert "MAAF" in full or "décennale" in full.lower()


def test_render_pdf_avoir_negatif(db_session):
    from src.facturation.pdf.renderer import render_facture_pdf
    from src.facturation.models import (
        Facture, FactureLigne, FactureType, CategorieTVA, UniteFacturation,
    )
    a, c, f = _facture_complete(db_session)
    avoir = Facture(artisan_id=a.id, client_id=c.id,
        numero="AVO-2026-0001", type=FactureType.AVOIR,
        date_emission=date(2026, 7, 1), date_echeance=date(2026, 7, 1),
        objet="Avoir sur facture FAC-2026-0001",
        motif_avoir="Erreur de facturation",
        montant_ht=Decimal("-450.00"), total_tva=Decimal("-90.00"),
        montant_ttc=Decimal("-540.00"), montant_du_ttc=Decimal("0"))
    avoir.lignes.append(FactureLigne(ordre=1, designation="Avoir : Prise",
        quantite=Decimal("10"), unite=UniteFacturation.PIECE,
        prix_unitaire_ht=Decimal("-25.00"), montant_ht_ligne=Decimal("-250.00"),
        taux_tva=Decimal("20.00"), categorie_tva=CategorieTVA.STANDARD))
    db_session.add(avoir); db_session.commit(); db_session.refresh(avoir)
    pdf = render_facture_pdf(avoir)
    reader = PdfReader(BytesIO(pdf))
    text = reader.pages[0].extract_text()
    assert "AVO-2026-0001" in text
    assert "AVOIR" in text.upper()
