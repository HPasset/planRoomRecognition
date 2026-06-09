"""Modèle DevisDB : persistance du devis.

Le runtime utilise `src.planrec.nfc_rules.DevisGlobal` (dataclass). DevisDB
en stocke la sérialisation pydantic dans `devis_global_json` + métadonnées
de cycle de vie (statut, signature, acceptation).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.facturation.db import Base
from src.facturation.models.enums import DevisStatut


class DevisDB(Base):
    __tablename__ = "devis"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artisan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artisan.id"), nullable=False, index=True,
    )
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("client.id"), nullable=False, index=True,
    )

    numero: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    date_emission: Mapped[date] = mapped_column(Date, nullable=False)
    date_validite: Mapped[date] = mapped_column(Date, nullable=False)
    objet: Mapped[str] = mapped_column(String(500), nullable=False)

    devis_global_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    montant_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_tva: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    statut: Mapped[DevisStatut] = mapped_column(
        String(20), nullable=False, default=DevisStatut.BROUILLON
    )
    date_acceptation: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    signature_client_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Plan d'origine — persistance cross-session : permet de réouvrir un
    # devis ancien (après fermeture du navigateur) et voir l'image du plan.
    plan_image_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    plan_image_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    plan_image_mime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    artisan = relationship("Artisan", lazy="joined")
    client = relationship("Client", lazy="joined")
