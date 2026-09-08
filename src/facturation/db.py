"""Configuration SQLAlchemy : engine, session factory, Base déclarative.

Single source of truth pour la connexion DB du module facturation.
DB par défaut : data/batia.db (SQLite WAL mode pour concurrence).
Override via env BATIA_DB_PATH (utile pour tests in-memory).
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "batia.db"


def get_db_url() -> str:
    """Renvoie l'URL SQLAlchemy. ENV BATIA_DB_PATH override le défaut."""
    db_path = os.environ.get("BATIA_DB_PATH")
    if db_path is None:
        DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(DEFAULT_DB_PATH)
    if db_path == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{db_path}"


def make_engine(url: str | None = None) -> Engine:
    """Crée l'engine SQLAlchemy.

    WAL mode + foreign_keys=ON pour SQLite : concurrence amicale et FK actives.
    """
    url = url or get_db_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_sqlite_pragmas(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA journal_mode = WAL")
            cursor.close()

    return engine


class Base(DeclarativeBase):
    """Base déclarative SQLAlchemy 2.x pour tous les modèles facturation."""
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def reset_engine() -> None:
    """Reset le singleton engine — utilisé par les tests pour isoler."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    """Crée toutes les tables (utile pour tests, pour la prod on utilise Alembic)."""
    Base.metadata.create_all(get_engine())
