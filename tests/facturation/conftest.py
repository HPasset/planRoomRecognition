"""Fixtures pytest pour le module facturation.

- db_session : session SQLAlchemy sur SQLite in-memory (rollback à chaque test)
- engine_inmem : engine in-memory si besoin direct
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture(autouse=True)
def _use_inmemory_db(monkeypatch):
    """Force la DB en mémoire pour TOUS les tests facturation."""
    monkeypatch.setenv("BATIA_DB_PATH", ":memory:")
    from src.facturation.db import reset_engine
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def engine_inmem():
    from src.facturation.db import get_engine
    from src.facturation.models import Base
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(engine_inmem) -> Iterator[Session]:
    SessionLocal = sessionmaker(bind=engine_inmem, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
