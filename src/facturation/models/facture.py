"""Modèles Facture + FactureLigne EN16931."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.facturation.db import Base
from src.facturation.models.enums import (
    CategorieTVA, FactureStatut, FactureType, UniteFacturation,
)


class Facture(Base):
    __tablename__ = "facture"
    __table_args__ = (UniqueConstraint("numero", name="uq_facture_numero"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    artisan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("artisan.id"), nullable=False, index=True,
    )
    client_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("client.id"), nullable=False, index=True,
    )
    devis_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("devis.id"), nullable=True, index=True,
    )
    facture_remplacee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("facture.id"), nullable=True,
    )

    numero: Mapped[str] = mapped_column(String(20), nullable=False)
    type: Mapped[FactureType] = mapped_column(String(5), nullable=False)
    statut: Mapped[FactureStatut] = mapped_column(
        String(25), nullable=False, default=FactureStatut.BROUILLON,
    )

    date_emission: Mapped[date] = mapped_column(Date, nullable=False)
    date_echeance: Mapped[date] = mapped_column(Date, nullable=False)
    date_envoi: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    date_paiement: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    objet: Mapped[str] = mapped_column(String(500), nullable=False)
    devise: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    montant_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total_tva: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    montant_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    acompte_montant_ht: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    montant_du_ttc: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))

    conditions_paiement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_devis: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    motif_avoir: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    pdf_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    facturx_xml_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    hash_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )

    artisan = relationship("Artisan", lazy="joined")
    client = relationship("Client", lazy="joined")
    devis = relationship("DevisDB", lazy="joined")
    lignes = relationship(
        "FactureLigne", back_populates="facture",
        cascade="all, delete-orphan", order_by="FactureLigne.ordre",
    )


class FactureLigne(Base):
    __tablename__ = "facture_ligne"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    facture_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facture.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    ordre: Mapped[int] = mapped_column(Integer, nullable=False)

    designation: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_article: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    quantite: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unite: Mapped[UniteFacturation] = mapped_column(String(5), nullable=False, default=UniteFacturation.UNITE)
    prix_unitaire_ht: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    montant_ht_ligne: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    categorie_tva: Mapped[CategorieTVA] = mapped_column(
        String(5), nullable=False, default=CategorieTVA.STANDARD,
    )

    facture = relationship("Facture", back_populates="lignes")
