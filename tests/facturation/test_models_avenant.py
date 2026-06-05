from __future__ import annotations
from datetime import date
from decimal import Decimal


def _devis_accepte(s):
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
    d = DevisDB(artisan_id=a.id, client_id=c.id, numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X", devis_global_json={},
        montant_ht=Decimal("1000"), total_tva=Decimal("200"),
        montant_ttc=Decimal("1200"), statut=DevisStatut.ACCEPTE)
    s.add(d); s.commit(); s.refresh(d)
    return a, c, d


def test_avenant_creation(db_session):
    from src.facturation.models import Avenant
    a, c, d = _devis_accepte(db_session)
    av = Avenant(devis_origine_id=d.id, numero="AVE-2026-0001",
        date_emission=date(2026, 7, 1),
        objet="Ajout 3 prises Cuisine",
        lignes_supplementaires_json={"lignes": [{"designation": "Prise", "qte": 3}]},
        montant_ht_supplementaire=Decimal("75.00"))
    db_session.add(av); db_session.commit(); db_session.refresh(av)
    assert av.id is not None
    assert av.date_acceptation is None
