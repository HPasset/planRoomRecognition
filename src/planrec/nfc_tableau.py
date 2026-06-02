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


from src.planrec.nfc_rules import DevisGlobal, NFCCategory


def detect_typology(devis: DevisGlobal) -> str:
    """Auto-détecte la typologie du logement à partir du devis.

    Compte les pièces principales (séjour + chambres) :
    - 1 pièce principale (séjour seul, studio) → T1
    - séjour + 1 chambre → T2
    - séjour + 2 chambres → T3
    - séjour + 3 chambres → T4
    - séjour + 4+ chambres → T5 (cap)
    """
    n_main_rooms = sum(
        1 for d in devis.per_room
        if d.nfc_category in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM)
    )
    return f"T{min(n_main_rooms, 5)}"


LIGHTING_MAX_PER_CIRCUIT = 5      # Règle cabinet associé (NFC stricte = 8)
SOCKET_MAX_PER_CIRCUIT = 12       # Règle cabinet associé (NFC stricte = 8)
CONVECTOR_MAX_PER_CIRCUIT = 2     # Règle cabinet associé (2× 2000W max)


def _build_lighting_circuits(
    rooms_with_lights: list[tuple[str, int]],
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leur n_lights → circuits 5/circuit max.

    Trie pièces par n_lights décroissant. Ouvre circuits successifs en y
    ajoutant pièces tant que capacité restante.
    """
    sorted_rooms = sorted(rooms_with_lights, key=lambda x: -x[1])
    circuits: list[Circuit] = []
    current_capacity = 0
    current_rooms: list[str] = []
    current_n = 0

    def _flush():
        nonlocal current_capacity, current_rooms, current_n
        if current_n > 0:
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.LIGHTING,
                label=f"Éclairage {', '.join(current_rooms)}",
                breaker_amps=10,
                cable_section_mm2=1.5,
                rooms_served=list(current_rooms),
                n_devices=current_n,
                requires_type_a=False,
            ))
        current_capacity = 0
        current_rooms = []
        current_n = 0

    for room_name, n_lights in sorted_rooms:
        if n_lights > LIGHTING_MAX_PER_CIRCUIT:
            _flush()
            n_remaining = n_lights
            while n_remaining > 0:
                chunk = min(n_remaining, LIGHTING_MAX_PER_CIRCUIT)
                circuits.append(Circuit(
                    id=generate_circuit_id(),
                    type=CircuitType.LIGHTING,
                    label=f"Éclairage {room_name}",
                    breaker_amps=10,
                    cable_section_mm2=1.5,
                    rooms_served=[room_name],
                    n_devices=chunk,
                ))
                n_remaining -= chunk
        elif current_capacity + n_lights <= LIGHTING_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_capacity += n_lights
            current_n += n_lights
        else:
            _flush()
            current_rooms = [room_name]
            current_capacity = n_lights
            current_n = n_lights

    _flush()
    return circuits


def _build_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leurs n_sockets → circuits 12/circuit
    max. Pièces avec n_sockets ≥ 6 prennent un circuit dédié, les plus petites
    sont packées ensemble."""
    sorted_rooms = sorted(rooms_with_sockets, key=lambda x: -x[1])
    circuits: list[Circuit] = []
    current_rooms: list[str] = []
    current_n = 0

    def _flush():
        nonlocal current_rooms, current_n
        if current_n > 0:
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.SOCKET,
                label=f"Prises {', '.join(current_rooms)}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=list(current_rooms),
                n_devices=current_n,
            ))
        current_rooms = []
        current_n = 0

    for room_name, n_sockets in sorted_rooms:
        if n_sockets > SOCKET_MAX_PER_CIRCUIT:
            _flush()
            n_remaining = n_sockets
            while n_remaining > 0:
                chunk = min(n_remaining, SOCKET_MAX_PER_CIRCUIT)
                circuits.append(Circuit(
                    id=generate_circuit_id(),
                    type=CircuitType.SOCKET,
                    label=f"Prises {room_name}",
                    breaker_amps=20,
                    cable_section_mm2=2.5,
                    rooms_served=[room_name],
                    n_devices=chunk,
                ))
                n_remaining -= chunk
        elif current_n + n_sockets <= SOCKET_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_n += n_sockets
        else:
            _flush()
            current_rooms = [room_name]
            current_n = n_sockets

    _flush()
    return circuits
