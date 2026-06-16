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
    SOCKET          = "socket"            # 16A — prises courant (1,5 mm²)
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


from src.planrec.nfc_rules import DevisGlobal, EquipmentType, NFCCategory


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
SOCKET_MAX_PER_CIRCUIT = 5        # NFC 15-100 : 16A / 1,5 mm² → 5 prises max
CONVECTOR_MAX_PER_CIRCUIT = 2     # Règle cabinet associé (2× 2000W max)


def _compact_rooms_label(prefix: str, rooms: list[str]) -> str:
    """Label compact pour les modules SVG : prefix + room(s) qui tient
    en 2-3 lignes max dans 60 px de large. Si >1 pièce, agrégé en '×N'.
    La liste complète des pièces reste dans Circuit.rooms_served pour
    le rendu HTML/PDF."""
    if not rooms:
        return prefix
    if len(rooms) == 1:
        return f"{prefix} {rooms[0]}"
    return f"{prefix} ×{len(rooms)}"


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
                label=_compact_rooms_label("Éclairage", current_rooms),
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


def _build_heating_circuits(
    rooms_with_convectors: list[tuple[str, int]],
    n_towel_warmers: int,
) -> list[Circuit]:
    """Génère les circuits chauffage : convecteurs packés 2/circuit + 1 circuit
    par sèche-serviettes."""
    circuits: list[Circuit] = []

    # Convecteurs : pack 2 par circuit
    all_convectors: list[str] = []
    for room, n in rooms_with_convectors:
        all_convectors.extend([room] * n)

    while all_convectors:
        chunk = all_convectors[:CONVECTOR_MAX_PER_CIRCUIT]
        all_convectors = all_convectors[CONVECTOR_MAX_PER_CIRCUIT:]
        circuits.append(Circuit(
            id=generate_circuit_id(),
            type=CircuitType.HEATING,
            label=_compact_rooms_label("Chauffage", chunk),
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=list(chunk),
            n_devices=len(chunk),
        ))

    # Sèche-serviettes : 1 circuit dédié par instance
    for i in range(n_towel_warmers):
        circuits.append(Circuit(
            id=generate_circuit_id(),
            type=CircuitType.TOWEL_WARMER,
            label=f"Sèche-serviettes {i+1}",
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=[],
            n_devices=1,
        ))

    return circuits


def _build_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leurs n_sockets → circuits de
    SOCKET_MAX_PER_CIRCUIT (5) prises max. Pièces dépassant la limite prennent
    un/des circuit(s) dédié(s) découpés, les plus petites sont packées ensemble."""
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
                label=_compact_rooms_label("Prises", current_rooms),
                breaker_amps=16,
                cable_section_mm2=1.5,
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
                    breaker_amps=16,
                    cable_section_mm2=1.5,
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


_SPECIALIZED_SPECS: dict[EquipmentType, tuple[int, float, str, bool, CircuitType]] = {
    # (breaker_amps, cable_section_mm2, label, requires_type_a, circuit_type)
    EquipmentType.OVEN:            (20, 2.5, "Four",           False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.COOKTOP:         (32, 6.0, "Plaque cuisson", True,  CircuitType.KITCHEN_SPECIAL),
    EquipmentType.DISHWASHER:      (20, 2.5, "Lave-vaisselle", False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.WASHING_MACHINE: (20, 2.5, "Lave-linge",     True,  CircuitType.LAUNDRY),
    EquipmentType.DRYER:           (20, 2.5, "Sèche-linge",    False, CircuitType.LAUNDRY),
    EquipmentType.BOILER:          (20, 2.5, "Chaudière",      False, CircuitType.BOILER),
}


def _build_specialized_circuits(
    counts: dict[EquipmentType, int],
) -> list[Circuit]:
    """Génère 1 circuit par instance d'appareil spécialisé."""
    circuits: list[Circuit] = []
    for eq_type, n in counts.items():
        if eq_type not in _SPECIALIZED_SPECS or n <= 0:
            continue
        amps, section, label, type_a, ctype = _SPECIALIZED_SPECS[eq_type]
        for i in range(n):
            suffix = f" {i+1}" if n > 1 else ""
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=ctype,
                label=f"{label}{suffix}",
                breaker_amps=amps,
                cable_section_mm2=section,
                rooms_served=[],
                n_devices=1,
                requires_type_a=type_a,
            ))
    return circuits


_TYPO_RCD_RULE = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 4}
MAX_BREAKERS_PER_RCD = 8


def _compute_min_rcds(
    typology: str,
    surface_m2: Optional[float],
    n_breakers: int,
) -> int:
    """Max des 3 contraintes : règle typo, règle surface NFC, ceil(N/8)."""
    n_typo = _TYPO_RCD_RULE.get(typology, 1)

    if surface_m2 is None:
        n_surface = 1
    elif surface_m2 <= 35:
        n_surface = 1
    elif surface_m2 <= 100:
        n_surface = 2
    else:
        n_surface = 3

    n_packing = math.ceil(n_breakers / MAX_BREAKERS_PER_RCD)

    return max(n_typo, n_surface, n_packing)


_NORMALIZED_RCD_AMPS = [25, 40, 63, 80, 100, 125]


def _ceil_to_normalized(x: float) -> int:
    """Arrondi au calibre normalisé supérieur dans {25, 40, 63, 80, 100, 125}."""
    for cap in _NORMALIZED_RCD_AMPS:
        if x <= cap:
            return cap
    return _NORMALIZED_RCD_AMPS[-1]


def _compute_rcd_amps(circuits: list[Circuit]) -> int:
    """Calibre RCD = (Σ non-chauffage)/2 + Σ chauffage, arrondi normalisé."""
    non_heat = [c for c in circuits if c.type not in
                (CircuitType.HEATING, CircuitType.TOWEL_WARMER)]
    heat = [c for c in circuits if c.type in
            (CircuitType.HEATING, CircuitType.TOWEL_WARMER)]
    raw = sum(c.breaker_amps for c in non_heat) / 2 + sum(c.breaker_amps for c in heat)
    return _ceil_to_normalized(raw)


def generate_tableau(
    devis_global: DevisGlobal,
    heating_enabled: bool = True,
    typology_override: Optional[str] = None,
) -> Tableau:
    """Orchestre les 7 phases pour produire un Tableau complet."""

    # Phase 0 : typologie + surface
    typology = typology_override or detect_typology(devis_global)
    typology_source = "user_override" if typology_override else "auto"
    surfaces = [d.surface_m2 for d in devis_global.per_room if d.surface_m2]
    surface_m2 = sum(surfaces) if surfaces else None

    notes: list[str] = []
    warnings: list[str] = []

    # Phase 1 : RJ45 hors tableau
    n_rj45 = sum(
        d.items.get(EquipmentType.RJ45, 0) for d in devis_global.per_room
    )
    if n_rj45 > 0:
        notes.append(f"{n_rj45} prises RJ45 → coffret VDI séparé (hors V1 batIA)")

    # Construire les listes par catégorie pour les phases 2/3/4
    rooms_with_lights: list[tuple[str, int]] = []
    rooms_with_sockets: list[tuple[str, int]] = []
    rooms_with_convectors: list[tuple[str, int]] = []
    n_towel_warmers = 0
    spec_counts: dict[EquipmentType, int] = {}

    cat_seen: dict[str, int] = {}
    cat_total: dict[str, int] = {}
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat

        n_light = d.items.get(EquipmentType.LIGHT_POINT, 0)
        if n_light > 0:
            rooms_with_lights.append((room_label, n_light))

        n_sock = d.items.get(EquipmentType.SOCKET, 0)
        if n_sock > 0:
            rooms_with_sockets.append((room_label, n_sock))

        n_conv = d.items.get(EquipmentType.CONVECTOR, 0)
        if n_conv > 0:
            rooms_with_convectors.append((room_label, n_conv))

        n_tw = d.items.get(EquipmentType.TOWEL_WARMER, 0)
        n_towel_warmers += n_tw

        for eq_type in (EquipmentType.OVEN, EquipmentType.COOKTOP,
                        EquipmentType.DISHWASHER,
                        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER,
                        EquipmentType.BOILER):
            n_eq = d.items.get(eq_type, 0)
            if n_eq > 0:
                spec_counts[eq_type] = spec_counts.get(eq_type, 0) + n_eq

    # Phase 2-5 : générer circuits
    circuits: list[Circuit] = []
    circuits.extend(_build_lighting_circuits(rooms_with_lights))
    circuits.extend(_build_socket_circuits(rooms_with_sockets))
    if heating_enabled:
        circuits.extend(_build_heating_circuits(rooms_with_convectors,
                                                 n_towel_warmers))
    circuits.extend(_build_specialized_circuits(spec_counts))

    # Phase 6 : nombre min de RCD
    n_rcds = _compute_min_rcds(typology, surface_m2, len(circuits))

    # Phase 7 : répartition sur RCD + calcul calibres
    rcds = _distribute_circuits_to_rcds(circuits, n_rcds)

    # Compteurs visuels
    total_modules = (
        len(circuits)
        + sum(4 for _ in rcds)
    )
    n_rails = math.ceil(total_modules / 13) if total_modules > 0 else 0

    return Tableau(
        typology=typology,
        typology_source=typology_source,
        surface_m2=surface_m2,
        heating_enabled=heating_enabled,
        rcds=rcds,
        total_modules=total_modules,
        n_rails=n_rails,
        notes=notes,
        warnings=warnings,
    )


def _distribute_circuits_to_rcds(
    circuits: list[Circuit],
    n_rcds: int,
) -> list[RCD]:
    """Bin-packing greedy :
    1. RCD1 = Type A → reçoit les circuits requires_type_a (Plaque + LL)
    2. RCD2..N = Type AC → reçoivent le reste
    3. Tri restant par amps décroissant, placement greedy au RCD le moins chargé
    4. Calcul calibre par formule (Σ hors-chauf)/2 + Σ chauf, normalisé
    """
    rcds: list[RCD] = []
    rcds.append(RCD(id=generate_rcd_id(), rcd_type="A", amps=40,
                    sensitivity_ma=30, circuits=[]))
    for _ in range(max(0, n_rcds - 1)):
        rcds.append(RCD(id=generate_rcd_id(), rcd_type="AC", amps=40,
                        sensitivity_ma=30, circuits=[]))

    # Type A obligatoire → RCD1
    type_a_circuits = [c for c in circuits if c.requires_type_a]
    other_circuits = [c for c in circuits if not c.requires_type_a]
    for c in type_a_circuits:
        rcds[0].circuits.append(c)

    # Trier autres par amps décroissant, bin-packing greedy
    sorted_others = sorted(other_circuits, key=lambda c: -c.breaker_amps)
    for c in sorted_others:
        # Choisir le RCD le moins chargé (en nombre de circuits, cap 8)
        candidates = [r for r in rcds if len(r.circuits) < MAX_BREAKERS_PER_RCD]
        if not candidates:
            # Si tous saturés, ajouter un RCD AC supplémentaire
            new_rcd = RCD(id=generate_rcd_id(), rcd_type="AC", amps=40,
                          sensitivity_ma=30, circuits=[])
            rcds.append(new_rcd)
            candidates = [new_rcd]
        target = min(candidates, key=lambda r: len(r.circuits))
        target.circuits.append(c)

    # Recalculer calibre de chaque RCD
    for rcd in rcds:
        rcd.amps = _compute_rcd_amps(rcd.circuits)

    return rcds
