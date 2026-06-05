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


def test_save_devis_from_payload(db_session):
    from src.facturation.services.devis import save_devis_from_payload
    a, c = _ac(db_session)
    d = save_devis_from_payload(
        db_session, artisan_id=a.id, client_id=c.id, numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X",
        devis_global_json={"rooms": [], "total_ht": "100.00"},
        montant_ht=Decimal("100.00"), total_tva=Decimal("20.00"),
        montant_ttc=Decimal("120.00"),
    )
    assert d.id is not None
    assert d.numero == "DEV-2026-0001"


def test_accept_devis(db_session):
    from src.facturation.services.devis import save_devis_from_payload, accept_devis
    from src.facturation.models import DevisStatut
    a, c = _ac(db_session)
    d = save_devis_from_payload(db_session, artisan_id=a.id, client_id=c.id,
        numero="DEV-2026-0001",
        date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
        objet="X", devis_global_json={},
        montant_ht=Decimal("0"), total_tva=Decimal("0"), montant_ttc=Decimal("0"))
    d2 = accept_devis(db_session, d.id)
    assert d2.statut == DevisStatut.ACCEPTE
    assert d2.date_acceptation is not None
