"""Tests du module db.py : engine, session, init, isolation in-memory."""
from __future__ import annotations

from sqlalchemy import text


def test_get_db_url_inmemory(monkeypatch):
    monkeypatch.setenv("BATIA_DB_PATH", ":memory:")
    from src.facturation.db import reset_engine, get_db_url
    reset_engine()
    assert get_db_url() == "sqlite:///:memory:"


def test_engine_sqlite_pragmas(engine_inmem):
    """foreign_keys doit être ON dès la connexion."""
    with engine_inmem.connect() as conn:
        fk = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk == 1


def test_session_isolation_between_tests(db_session):
    """La DB est in-memory, doit être vide à chaque test."""
    from src.facturation.models import Base
    for table in Base.metadata.sorted_tables:
        count = db_session.execute(text(f"SELECT COUNT(*) FROM {table.name}")).scalar()
        assert count == 0


def test_enums_importable():
    from src.facturation.models import (
        FactureStatut, FactureType, DevisStatut, ModePaiement,
        CategorieTVA, TypeClient, TypeCompteur, UniteFacturation,
        FormeJuridique, ActionAudit,
    )
    assert FactureStatut.BROUILLON.value == "brouillon"
    assert FactureType.STANDARD.value == "380"
    assert ModePaiement.VIREMENT.value == "30"
    assert CategorieTVA.STANDARD.value == "S"
