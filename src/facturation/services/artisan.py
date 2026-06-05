"""Service Artisan : helpers de création / récupération du default.

Prototype = 1 artisan unique. Cette couche centralise la logique pour
faciliter le passage en multi-tenant plus tard.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from src.facturation.models import Artisan


def get_default_artisan(session: Session) -> Optional[Artisan]:
    """Retourne le premier (et seul) Artisan du prototype, ou None si absent."""
    return session.query(Artisan).order_by(Artisan.created_at.asc()).first()


def create_or_update_artisan(session: Session, **fields) -> Artisan:
    """Crée le default artisan s'il n'existe pas, sinon update ses champs."""
    existing = get_default_artisan(session)
    if existing is None:
        artisan = Artisan(**fields)
        session.add(artisan)
        session.commit()
        session.refresh(artisan)
        return artisan
    for key, value in fields.items():
        if key == "siret":
            from src.facturation.models.artisan import _validate_siret
            value = _validate_siret(value)
        if key == "iban":
            from src.facturation.models.artisan import _normalize_iban
            value = _normalize_iban(value)
        setattr(existing, key, value)
    session.commit()
    session.refresh(existing)
    return existing
