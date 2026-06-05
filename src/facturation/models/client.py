"""Modèle Client = Buyer Party EN16931 (BT-44..55).

Référentiel client par artisan (FK obligatoire).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.facturation.db import Base
from src.facturation.models.enums import TypeClient
from src.facturation.models.artisan import _validate_siret


class Client(Base):
    __tablename__ = "client"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artisan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artisan.id"), nullable=False, index=True,
    )

    type: Mapped[TypeClient] = mapped_column(
        String(20), nullable=False, default=TypeClient.PARTICULIER
    )
    nom_ou_raison: Mapped[str] = mapped_column(String(255), nullable=False)
    siret: Mapped[Optional[str]] = mapped_column(String(14), nullable=True)
    numero_tva_intra: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    adresse_rue: Mapped[str] = mapped_column(String(255), nullable=False)
    adresse_complement: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    adresse_cp: Mapped[str] = mapped_column(String(5), nullable=False)
    adresse_ville: Mapped[str] = mapped_column(String(100), nullable=False)
    adresse_pays: Mapped[str] = mapped_column(String(2), nullable=False, default="FR")

    telephone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    artisan = relationship("Artisan", lazy="joined")

    def __init__(self, **kwargs):
        if "siret" in kwargs and kwargs["siret"]:
            kwargs["siret"] = _validate_siret(kwargs["siret"])
        super().__init__(**kwargs)
