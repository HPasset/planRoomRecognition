"""Avenant = modificatif d'un devis accepté en cours de chantier."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, LargeBinary, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.facturation.db import Base


class Avenant(Base):
    __tablename__ = "avenant"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    devis_origine_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("devis.id"), nullable=False, index=True,
    )
    numero: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    date_emission: Mapped[date] = mapped_column(Date, nullable=False)
    objet: Mapped[str] = mapped_column(String(500), nullable=False)
    lignes_supplementaires_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict,
    )
    montant_ht_supplementaire: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"),
    )
    date_acceptation: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    signature_client_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    devis = relationship("DevisDB", lazy="joined")
