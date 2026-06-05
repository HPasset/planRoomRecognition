"""Paiement enregistré contre une facture (partiel ou total)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.facturation.db import Base
from src.facturation.models.enums import ModePaiement


class Paiement(Base):
    __tablename__ = "paiement"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    facture_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facture.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    montant: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    mode: Mapped[ModePaiement] = mapped_column(String(5), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    facture = relationship("Facture", lazy="joined")
