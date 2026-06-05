from __future__ import annotations
from datetime import date
from decimal import Decimal
import pytest


def _facture_avec_lignes(s):
    from src.facturation.models import (
        Artisan, Client, Facture, FactureLigne, FactureType,
        FormeJuridique, TypeClient, CategorieTVA, UniteFacturation,
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
    f.lignes.append(FactureLigne(ordre=1, designation="Prise",
        quantite=Decimal("1"), unite=UniteFacturation.UNITE,
        prix_unitaire_ht=Decimal("100"), montant_ht_ligne=Decimal("100"),
        taux_tva=Decimal("20"), categorie_tva=CategorieTVA.STANDARD))
    s.add(f); s.commit(); s.refresh(f)
    return a, c, f


def test_cancel_facture_genere_avoir(db_session):
    from src.facturation.services.avoirs import cancel_facture
    from src.facturation.models import FactureStatut, FactureType
    a, c, f = _facture_avec_lignes(db_session)
    avoir = cancel_facture(db_session, f.id, motif="Erreur facturation")
    db_session.refresh(f)
    assert f.statut == FactureStatut.ANNULEE
    assert avoir.type == FactureType.AVOIR
    assert avoir.montant_ttc == Decimal("-120")
    assert avoir.facture_remplacee_id == f.id


def test_cancel_facture_deja_annulee_refuse(db_session):
    from src.facturation.services.avoirs import cancel_facture
    a, c, f = _facture_avec_lignes(db_session)
    cancel_facture(db_session, f.id, motif="X")
    with pytest.raises(ValueError, match="déjà annulée"):
        cancel_facture(db_session, f.id, motif="Y")
