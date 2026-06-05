from __future__ import annotations
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

PAGE = (Path(__file__).resolve().parents[2]
        / "app" / "pages" / "2_👥_Clients.py")


@pytest.fixture
def at_with_artisan(tmp_path, monkeypatch):
    monkeypatch.setenv("BATIA_DB_PATH", str(tmp_path / "test.db"))
    from src.facturation.db import reset_engine, init_db, get_session_factory
    # IMPORTANT : importer les models AVANT init_db pour que les tables
    # soient enregistrées dans Base.metadata
    from src.facturation.models import Base, Artisan, Client  # noqa: F401
    reset_engine()
    init_db()
    SessionLocal = get_session_factory()
    s = SessionLocal()
    from src.facturation.services.artisan import create_or_update_artisan
    from src.facturation.models import FormeJuridique
    create_or_update_artisan(s, raison_sociale="A",
        forme_juridique=FormeJuridique.EI,
        siret="12345678901234", numero_tva_intra="FR12123456789",
        adresse_rue="r", adresse_cp="75001", adresse_ville="P",
        adresse_pays="FR", email="a@a.com",
        iban="FR7612345987650123456789014")
    s.close()
    yield AppTest.from_file(str(PAGE), default_timeout=15)
    reset_engine()


def test_page_clients_sans_artisan(tmp_path, monkeypatch):
    monkeypatch.setenv("BATIA_DB_PATH", str(tmp_path / "empty.db"))
    from src.facturation.db import reset_engine, init_db
    from src.facturation.models import Base, Artisan, Client  # noqa: F401
    reset_engine(); init_db()
    at = AppTest.from_file(str(PAGE), default_timeout=15)
    at.run()
    assert not at.exception
    assert any("Paramètres" in str(w.value) for w in at.warning)
    reset_engine()


def test_page_clients_liste_vide(at_with_artisan):
    at_with_artisan.run()
    assert not at_with_artisan.exception
    assert any("Aucun client" in str(i.value) for i in at_with_artisan.info)
