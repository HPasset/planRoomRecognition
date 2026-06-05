from __future__ import annotations
from datetime import date
from decimal import Decimal


def _ac(s):
    from src.facturation.models import Artisan, Client, FormeJuridique, TypeClient
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
    return a, c


def test_facture_brouillon_creation(db_session):
    from src.facturation.models import Facture, FactureType, FactureStatut
    a, c = _ac(db_session)
    f = Facture(
        artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="Test",
    )
    db_session.add(f); db_session.commit(); db_session.refresh(f)
    assert f.statut == FactureStatut.BROUILLON
    assert f.devise == "EUR"
    assert f.montant_ht == Decimal("0")


def test_facture_avec_lignes_cascade_delete(db_session):
    from src.facturation.models import (
        Facture, FactureLigne, FactureType, CategorieTVA, UniteFacturation,
    )
    a, c = _ac(db_session)
    f = Facture(artisan_id=a.id, client_id=c.id,
        numero="FAC-2026-0001", type=FactureType.STANDARD,
        date_emission=date(2026, 6, 5), date_echeance=date(2026, 7, 5),
        objet="X")
    f.lignes.append(FactureLigne(
        ordre=1, designation="Prise", quantite=Decimal("10"),
        unite=UniteFacturation.PIECE, prix_unitaire_ht=Decimal("25.00"),
        montant_ht_ligne=Decimal("250.00"), taux_tva=Decimal("20.00"),
        categorie_tva=CategorieTVA.STANDARD,
    ))
    db_session.add(f); db_session.commit(); db_session.refresh(f)
    assert len(f.lignes) == 1
    db_session.delete(f); db_session.commit()
    assert db_session.query(FactureLigne).count() == 0
