"""Compteurs de numérotation séquentielle par (artisan, année, type)."""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.facturation.db import Base
from src.facturation.models.enums import TypeCompteur


class Compteur(Base):
    __tablename__ = "compteur"
    __table_args__ = (
        UniqueConstraint(
            "artisan_id", "annee", "type",
            name="uq_compteur_artisan_annee_type",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artisan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artisan.id"), nullable=False, index=True,
    )
    annee: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[TypeCompteur] = mapped_column(String(5), nullable=False)
    valeur_courante: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
