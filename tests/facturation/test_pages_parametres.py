"""Tests AppTest pour la page Paramètres artisan."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


PAGE = (Path(__file__).resolve().parents[2]
        / "app" / "pages" / "3_⚙️_Paramètres.py")


@pytest.fixture
def at(tmp_path, monkeypatch):
    """AppTest sur fichier DB temporaire."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("BATIA_DB_PATH", str(db_path))
    # Import models BEFORE init_db so Base.metadata has all tables registered.
    from src.facturation.models import Base  # noqa: F401 — registers Artisan in metadata
    from src.facturation.db import reset_engine, init_db
    reset_engine()
    init_db()
    yield AppTest.from_file(str(PAGE), default_timeout=15)
    reset_engine()


def test_page_charge_sans_artisan(at):
    at.run()
    assert not at.exception
    assert any("Paramètres artisan" in str(t.value) for t in at.title)


def test_creation_artisan_via_form(at):
    at.run()

    inputs = {ti.label: ti for ti in at.text_input}
    inputs["Raison sociale"].set_value("batIA Élec")
    inputs["SIRET (14 chiffres)"].set_value("12345678901234")
    inputs["N° TVA intra"].set_value("FR12123456789")
    inputs["Rue"].set_value("1 rue")
    inputs["Code postal"].set_value("75001")
    inputs["Ville"].set_value("Paris")
    inputs["Email"].set_value("h@b.com")
    inputs["IBAN"].set_value("FR7612345987650123456789014")

    at.button[0].click().run()
    assert not at.exception
    assert any("Artisan enregistré" in str(s.value) for s in at.success)


def test_page_charge_avec_artisan_existant(tmp_path, monkeypatch):
    """Régression : SQLite renvoie forme_juridique comme str (pas Enum) au reload.
    La page doit gérer les deux cas sans planter sur .value."""
    monkeypatch.setenv("BATIA_DB_PATH", str(tmp_path / "test.db"))
    from src.facturation.models import Base  # noqa: F401
    from src.facturation.db import reset_engine, init_db, get_session_factory
    reset_engine(); init_db()

    SessionLocal = get_session_factory()
    s = SessionLocal()
    from src.facturation.services.artisan import create_or_update_artisan
    from src.facturation.models import FormeJuridique
    create_or_update_artisan(
        s, raison_sociale="batIA pré-existant",
        forme_juridique=FormeJuridique.SARL,
        siret="98765432109876", numero_tva_intra="FR98987654321",
        adresse_rue="2 av", adresse_cp="92100", adresse_ville="Boulogne",
        adresse_pays="FR", email="h@b.com",
        iban="FR7612345987650123456789014",
    )
    s.close()

    at = AppTest.from_file(str(PAGE), default_timeout=15)
    at.run()
    assert not at.exception, f"Exception sur reload avec artisan existant : {at.exception}"
    # Champ rempli avec la valeur DB
    inputs = {ti.label: ti for ti in at.text_input}
    assert inputs["Raison sociale"].value == "batIA pré-existant"
    reset_engine()
