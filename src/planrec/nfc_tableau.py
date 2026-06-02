"""Algo greedy de répartition du tableau électrique selon NFC 15-100 + règles
cabinet associé. Logique métier 100% pure (testable pytest seul, aucune
dépendance Streamlit/React).

Source : docs/superpowers/specs/2026-06-02-tableau-electrique-design.md
"""
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CircuitType(str, Enum):
    LIGHTING        = "lighting"          # 10A — points lumineux
    SOCKET          = "socket"            # 20A — prises courant
    KITCHEN_SPECIAL = "kitchen_special"   # Four / Plaque / LV (20A ou 32A)
    LAUNDRY         = "laundry"           # LL / SL (20A)
    BOILER          = "boiler"            # Chaudière / cumulus (20A)
    HEATING         = "heating"           # Convecteur (20A)
    TOWEL_WARMER    = "towel_warmer"      # Sèche-serviettes SdB (20A)


@dataclass
class Circuit:
    id: str
    type: CircuitType
    label: str
    breaker_amps: int
    cable_section_mm2: float
    rooms_served: list[str] = field(default_factory=list)
    n_devices: int = 0
    requires_type_a: bool = False


def generate_circuit_id() -> str:
    """Génère un ID unique 'circ_<8 hex>'."""
    return f"circ_{secrets.token_hex(4)}"


@dataclass
class RCD:
    """Interrupteur Différentiel."""
    id: str
    rcd_type: str        # "A" (plaque + LL obligatoire) ou "AC"
    amps: int            # 25, 40, 63, 80, 100, 125 (normalisé)
    sensitivity_ma: int  # 30 mA (résidentiel standard)
    circuits: list[Circuit] = field(default_factory=list)


@dataclass
class Tableau:
    typology: str                    # "T3"
    typology_source: str             # "auto" | "user_override"
    surface_m2: Optional[float]
    heating_enabled: bool
    rcds: list[RCD]
    total_modules: int               # somme circuits + RCD + headroom 20%
    n_rails: int                     # ceil(total / 13 modules par rail)
    notes: list[str]
    warnings: list[str]


def generate_rcd_id() -> str:
    """Génère un ID unique 'rcd_<8 hex>'."""
    return f"rcd_{secrets.token_hex(4)}"
