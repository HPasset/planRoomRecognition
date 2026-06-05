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
