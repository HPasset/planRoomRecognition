from __future__ import annotations
from datetime import date
from decimal import Decimal
import pytest


def _setup(s):
    from src.facturation.models import (
        Artisan, Client, DevisDB, FormeJuridique, TypeClient, DevisStatut,
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
    d = DevisDB(artisan_id=a.id, client_id=c.id,
        numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="Installation 100m²",
        devis_global_json={"per_room": [], "montant_ht": "5000.00"},
        montant_ht=Decimal("5000.00"), total_tva=Decimal("1000.00"),
        montant_ttc=Decimal("6000.00"),
        statut=DevisStatut.ACCEPTE,
    )
    s.add(d); s.commit(); s.refresh(d)
    return a, c, d


def test_create_acompte_30pct(db_session):
    from src.facturation.services.creation import create_acompte
    from src.facturation.models import FactureType
    a, c, d = _setup(db_session)
    f = create_acompte(db_session, devis_id=d.id, pourcentage=30)
    assert f.type == FactureType.ACOMPTE
    assert f.montant_ht == Decimal("1500.00")
    assert f.total_tva == Decimal("300.00")
    assert f.montant_ttc == Decimal("1800.00")
    assert f.devis_id == d.id
    assert f.numero.startswith("FAC-")


def test_create_acompte_devis_non_accepte_refuse(db_session):
    from src.facturation.services.creation import create_acompte
    from src.facturation.models import DevisStatut
    a, c, d = _setup(db_session)
    d.statut = DevisStatut.BROUILLON
    db_session.commit()
    with pytest.raises(ValueError, match="accepte"):
        create_acompte(db_session, devis_id=d.id, pourcentage=30)


def test_create_solde_apres_acompte(db_session):
    from src.facturation.services.creation import create_acompte, create_solde
    from src.facturation.models import FactureType
    a, c, d = _setup(db_session)
    create_acompte(db_session, devis_id=d.id, pourcentage=30)
    solde = create_solde(db_session, devis_id=d.id)
    assert solde.type == FactureType.STANDARD
    assert solde.acompte_montant_ht == Decimal("1500.00")
    assert solde.montant_ht == Decimal("5000.00")
    assert solde.montant_du_ttc == Decimal("4200.00")
