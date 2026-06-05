from __future__ import annotations
from datetime import date
from decimal import Decimal


def _make_artisan_client(s):
    from src.facturation.models import Artisan, Client, FormeJuridique, TypeClient
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Cli", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    s.add(c); s.commit(); s.refresh(c)
    return a, c


def test_devis_creation_brouillon(db_session):
    from src.facturation.models import DevisDB, DevisStatut
    a, c = _make_artisan_client(db_session)
    d = DevisDB(
        artisan_id=a.id, client_id=c.id,
        numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5),
        date_validite=date(2026, 9, 5),
        objet="Installation électrique 100m²",
        devis_global_json={"rooms": [], "total_ht": "5000.00"},
        montant_ht="5000.00", total_tva="1000.00", montant_ttc="6000.00",
    )
    db_session.add(d); db_session.commit(); db_session.refresh(d)
    assert d.id is not None
    assert d.statut == DevisStatut.BROUILLON


def test_devis_montants_decimal(db_session):
    from src.facturation.models import DevisDB
    from decimal import Decimal
    a, c = _make_artisan_client(db_session)
    d = DevisDB(
        artisan_id=a.id, client_id=c.id, numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X", devis_global_json={},
        montant_ht=Decimal("123.45"), total_tva=Decimal("24.69"),
        montant_ttc=Decimal("148.14"),
    )
    db_session.add(d); db_session.commit(); db_session.refresh(d)
    assert d.montant_ht == Decimal("123.45")
    assert d.montant_ttc == Decimal("148.14")
