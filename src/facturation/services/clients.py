"""CRUD Client : create, list, get, update, delete."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import Client


def create_client(session: Session, **fields) -> Client:
    c = Client(**fields)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def list_clients(session: Session, artisan_id: str) -> list[Client]:
    return (session.query(Client)
            .filter(Client.artisan_id == artisan_id)
            .order_by(Client.nom_ou_raison.asc())
            .all())


def get_client(session: Session, client_id: str) -> Optional[Client]:
    return session.get(Client, client_id)


def update_client(session: Session, client_id: str, **fields) -> Client:
    c = session.get(Client, client_id)
    if c is None:
        raise ValueError(f"Client {client_id} introuvable")
    for k, v in fields.items():
        if k == "siret" and v:
            from src.facturation.models.artisan import _validate_siret
            v = _validate_siret(v)
        setattr(c, k, v)
    session.commit()
    session.refresh(c)
    return c


def delete_client(session: Session, client_id: str) -> None:
    c = session.get(Client, client_id)
    if c is not None:
        session.delete(c)
        session.commit()
