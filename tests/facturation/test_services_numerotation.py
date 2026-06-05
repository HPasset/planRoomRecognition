from __future__ import annotations


def _artisan(s):
    from src.facturation.models import Artisan, FormeJuridique
    a = Artisan(raison_sociale="A", forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    s.add(a); s.commit(); s.refresh(a); return a


def test_next_numero_sequence(db_session):
    from src.facturation.services.numerotation import next_numero
    from src.facturation.models import TypeCompteur
    a = _artisan(db_session)
    n1 = next_numero(db_session, a.id, 2026, TypeCompteur.FACTURE)
    n2 = next_numero(db_session, a.id, 2026, TypeCompteur.FACTURE)
    n3 = next_numero(db_session, a.id, 2026, TypeCompteur.FACTURE)
    assert n1 == "FAC-2026-0001"
    assert n2 == "FAC-2026-0002"
    assert n3 == "FAC-2026-0003"


def test_compteurs_independants_par_type(db_session):
    from src.facturation.services.numerotation import next_numero
    from src.facturation.models import TypeCompteur
    a = _artisan(db_session)
    f1 = next_numero(db_session, a.id, 2026, TypeCompteur.FACTURE)
    d1 = next_numero(db_session, a.id, 2026, TypeCompteur.DEVIS)
    avo1 = next_numero(db_session, a.id, 2026, TypeCompteur.AVOIR)
    ave1 = next_numero(db_session, a.id, 2026, TypeCompteur.AVENANT)
    assert f1 == "FAC-2026-0001"
    assert d1 == "DEV-2026-0001"
    assert avo1 == "AVO-2026-0001"
    assert ave1 == "AVE-2026-0001"


def test_compteurs_independants_par_annee(db_session):
    from src.facturation.services.numerotation import next_numero
    from src.facturation.models import TypeCompteur
    a = _artisan(db_session)
    n_2025 = next_numero(db_session, a.id, 2025, TypeCompteur.FACTURE)
    n_2026 = next_numero(db_session, a.id, 2026, TypeCompteur.FACTURE)
    assert n_2025 == "FAC-2025-0001"
    assert n_2026 == "FAC-2026-0001"
