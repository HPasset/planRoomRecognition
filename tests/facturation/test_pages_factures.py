from __future__ import annotations
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


PAGE = (Path(__file__).resolve().parents[2]
        / "app" / "pages" / "1_📄_Factures.py")


def _seed(monkeypatch, tmp_path, with_devis=True):
    monkeypatch.setenv("BATIA_DB_PATH", str(tmp_path / "test.db"))
    from src.facturation.db import reset_engine, init_db, get_session_factory
    from src.facturation.models import (
        Base, Artisan, Client, DevisDB, FactureStatut, FactureType,
        Compteur, Facture, FactureLigne, Avenant, Paiement, AuditLog,
    )  # noqa: F401
    reset_engine(); init_db()
    SessionLocal = get_session_factory()
    s = SessionLocal()
    from src.facturation.models import FormeJuridique, TypeClient, DevisStatut
    a = Artisan(raison_sociale="batIA",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014",
        mentions_assurance_decennale="MAAF n°ABC")
    s.add(a); s.commit(); s.refresh(a)
    c = Client(artisan_id=a.id, type=TypeClient.PARTICULIER,
        nom_ou_raison="Cli", adresse_rue="r", adresse_cp="75001",
        adresse_ville="P", adresse_pays="FR", email="c@c.com")
    s.add(c); s.commit(); s.refresh(c)
    if with_devis:
        d = DevisDB(artisan_id=a.id, client_id=c.id, numero="DEV-2026-0001",
            date_emission=date(2026, 6, 5), date_validite=date(2026, 9, 5),
            objet="X", devis_global_json={},
            montant_ht=Decimal("1000"), total_tva=Decimal("200"),
            montant_ttc=Decimal("1200"), statut=DevisStatut.ACCEPTE)
        s.add(d); s.commit()
    s.close()


def test_page_factures_sans_artisan(monkeypatch, tmp_path):
    monkeypatch.setenv("BATIA_DB_PATH", str(tmp_path / "empty.db"))
    from src.facturation.db import reset_engine, init_db
    from src.facturation.models import Base, Artisan, Client, Facture  # noqa: F401
    reset_engine(); init_db()
    at = AppTest.from_file(str(PAGE), default_timeout=15)
    at.run()
    assert not at.exception
    assert any("Paramètres" in str(w.value) for w in at.warning)


def test_page_factures_liste_vide(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    at = AppTest.from_file(str(PAGE), default_timeout=15)
    at.run()
    assert not at.exception
    assert any("Aucune facture" in str(i.value) for i in at.info)


def test_page_factures_creer_acompte_via_service(monkeypatch, tmp_path):
    """E2E indirect : depuis devis accepté → créer acompte 30% via service.
    L'UI Streamlit AppTest est limitée pour les tabs+forms — on valide
    le flux par le service que la page expose."""
    _seed(monkeypatch, tmp_path)
    from src.facturation.db import get_session_factory
    SessionLocal = get_session_factory()
    s = SessionLocal()
    from src.facturation.models import DevisDB
    from src.facturation.services.creation import create_acompte
    d = s.query(DevisDB).first()
    f = create_acompte(s, d.id, pourcentage=30)
    assert f.numero.startswith("FAC-")
    assert f.montant_ttc == Decimal("360.00")
    s.close()
