from __future__ import annotations
from io import BytesIO

from pypdf import PdfReader


def test_embed_xml_in_pdf_a3():
    """Embed XML CII dans un PDF généré par notre renderer."""
    # Génère un PDF avec notre renderer pour avoir un input réaliste
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
        iban="FR7612345987650123456789014",
        mentions_assurance_decennale="MAAF n°ABC")
    c = Client(artisan_id="placeholder", type=TypeClient.PARTICULIER,
        nom_ou_raison="C", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    f = Facture(artisan_id="placeholder", client_id="placeholder",
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="X",
        montant_ht=Decimal("100"), total_tva=Decimal("20"),
        montant_ttc=Decimal("120"), montant_du_ttc=Decimal("120"))
    f.lignes.append(FactureLigne(ordre=1, designation="X",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=Decimal("100"), montant_ht_ligne=Decimal("100"),
        taux_tva=Decimal("20"), categorie_tva=CategorieTVA.STANDARD))
    # Forcer les relations directement (les FK ne sont pas persistées dans ce test)
    f.artisan = a
    f.client = c

    from src.facturation.pdf.renderer import render_facture_pdf
    from src.facturation.factur_x.builder import build_xml_cii
    from src.facturation.factur_x.embedder import embed_xml_in_pdf

    pdf_in = render_facture_pdf(f)
    xml = build_xml_cii(f)
    pdf_out = embed_xml_in_pdf(pdf_in, xml)

    assert pdf_out.startswith(b"%PDF-")
    # Sortie supérieure ou égale (XML attaché augmente la taille)
    assert len(pdf_out) >= len(pdf_in)
    reader = PdfReader(BytesIO(pdf_out))
    assert len(reader.pages) >= 1
