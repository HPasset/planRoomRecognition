"""Exporte tous les modèles SQLAlchemy + enums du module facturation.

Les modèles concrets (Artisan, Client, ...) seront ajoutés dans les tasks
suivantes. Ce fichier est l'unique point d'import pour Alembic autogenerate.
"""
from src.facturation.db import Base
from src.facturation.models.artisan import Artisan
from src.facturation.models.client import Client
from src.facturation.models.enums import (
    ActionAudit,
    CategorieTVA,
    DevisStatut,
    FactureStatut,
    FactureType,
    FormeJuridique,
    ModePaiement,
    TypeClient,
    TypeCompteur,
    UniteFacturation,
)

__all__ = [
    "Base",
    "Artisan",
    "Client",
    "ActionAudit",
    "CategorieTVA",
    "DevisStatut",
    "FactureStatut",
    "FactureType",
    "FormeJuridique",
    "ModePaiement",
    "TypeClient",
    "TypeCompteur",
    "UniteFacturation",
]
