"""Modèle Artisan = Seller Party EN16931 (BT-27..40, BT-84..86).

Identité légale de l'utilisateur batIA. SIRET unique. Multi-tenant futur
via FK depuis Client/Devis/Facture/etc.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import LargeBinary, String, Text, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.facturation.db import Base
from src.facturation.models.enums import FormeJuridique


_SIRET_RE = re.compile(r"^\d{14}$")


def _validate_siret(value: str) -> str:
    cleaned = (value or "").replace(" ", "")
    if not _SIRET_RE.match(cleaned):
        raise ValueError(f"SIRET doit être 14 chiffres, reçu : {value!r}")
    return cleaned


def _normalize_iban(value: str) -> str:
    return (value or "").replace(" ", "").upper()


class Artisan(Base):
    __tablename__ = "artisan"
    __table_args__ = (UniqueConstraint("siret", name="uq_artisan_siret"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Identité légale
    raison_sociale: Mapped[str] = mapped_column(String(255), nullable=False)
    forme_juridique: Mapped[FormeJuridique] = mapped_column(
        String(10), nullable=False, default=FormeJuridique.EI
    )
    siret: Mapped[str] = mapped_column(String(14), nullable=False)
    numero_tva_intra: Mapped[str] = mapped_column(String(20), nullable=False)
    code_naf: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    # Adresse (BT-35..40)
    adresse_rue: Mapped[str] = mapped_column(String(255), nullable=False)
    adresse_complement: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    adresse_cp: Mapped[str] = mapped_column(String(5), nullable=False)
    adresse_ville: Mapped[str] = mapped_column(String(100), nullable=False)
    adresse_pays: Mapped[str] = mapped_column(String(2), nullable=False, default="FR")

    # Contact (BT-42, BT-43)
    telephone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Banque (BT-84..86)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    bic: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    nom_banque: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Mentions obligatoires BTP
    mentions_assurance_decennale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mentions_garantie_biennale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Assets
    logo_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    signature_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    # Configurable
    delai_grace_jours: Mapped[int] = mapped_column(default=3)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __init__(self, **kwargs):
        if "siret" in kwargs:
            kwargs["siret"] = _validate_siret(kwargs["siret"])
        if "iban" in kwargs:
            kwargs["iban"] = _normalize_iban(kwargs["iban"])
        super().__init__(**kwargs)
