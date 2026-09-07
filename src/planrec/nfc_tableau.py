"""Algo greedy de répartition du tableau électrique selon NFC 15-100 + règles
cabinet associé. Logique métier 100% pure (testable pytest seul, aucune
dépendance Streamlit/React).

Source : docs/superpowers/specs/2026-06-02-tableau-electrique-design.md
"""
from __future__ import annotations

import bisect
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
    KITCHEN_SOCKET  = "kitchen_socket"    # Prises cuisine (20A / 2,5 mm²)
    VMC             = "vmc"               # VMC (16A — Type A)
    HEAT_PUMP       = "heat_pump"         # Pompe à chaleur (32A — Type F)
    EV_CHARGER      = "ev_charger"        # Borne véhicule (32A — Type F)


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
    requires_type_f: bool = False


def generate_circuit_id() -> str:
    """Génère un ID unique 'circ_<8 hex>'."""
    return f"circ_{secrets.token_hex(4)}"


@dataclass
class RCD:
    """Interrupteur Différentiel."""
    id: str
    rcd_type: str        # "A" | "AC" | "F"
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
SOCKET_MAX_PER_CIRCUIT = 8        # NFC 15-100 : 16A / 1,5 mm² → 8 prises max
KITCHEN_SOCKET_MAX_PER_CIRCUIT = 6  # NFC : prises cuisine 20A / 2,5 mm²
CONVECTOR_MAX_PER_CIRCUIT = 2     # Règle cabinet associé (2× 2000W max)



def _compact_rooms_label(prefix: str, rooms: list[str],
                         codes: dict[str, str] | None = None) -> str:
    """Label court pour étiquettes/schéma : prefix + codes des pièces
    (« Écl. CH2 CH3 DGT »). `codes` mappe label pièce → code court ; à défaut
    le label complet. La liste complète reste dans Circuit.rooms_served."""
    if not rooms:
        return prefix
    codes = codes or {}
    seen = dict.fromkeys(codes.get(r, r) for r in rooms)  # dédoublonne, ordre gardé
    return f"{prefix} " + " ".join(seen)


def _build_lighting_circuits(
    rooms_with_lights: list[tuple[str, int]],
    codes: dict[str, str] | None = None,
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leur n_lights → circuits 5/circuit max.

    Une pièce qui dépasse 5 points (salon 6 spots + 1 PL) garde un circuit
    dédié entier, sans découpage (règle cabinet 2026-09-07). Les autres sont
    packées ensemble par ordre décroissant. Aucun flag type A : la
    répartition choisit un seul circuit éclairage pour l'ID type A.
    """
    sorted_rooms = sorted(rooms_with_lights, key=lambda x: -x[1])
    circuits: list[Circuit] = []
    current_rooms: list[str] = []
    current_n = 0

    def _make(rooms: list[str], n: int) -> Circuit:
        return Circuit(
            id=generate_circuit_id(),
            type=CircuitType.LIGHTING,
            label=_compact_rooms_label("Écl.", rooms, codes),
            breaker_amps=10,
            cable_section_mm2=1.5,
            rooms_served=list(rooms),
            n_devices=n,
        )

    def _flush():
        nonlocal current_rooms, current_n
        if current_n > 0:
            circuits.append(_make(current_rooms, current_n))
        current_rooms = []
        current_n = 0

    for room_name, n_lights in sorted_rooms:
        if n_lights > LIGHTING_MAX_PER_CIRCUIT:
            # ponytail: pas de plafond haut ; en ajouter un si le cabinet
            # remonte des pièces à 12+ spots sur un seul 10 A.
            circuits.append(_make([room_name], n_lights))
        elif current_n + n_lights <= LIGHTING_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_n += n_lights
        else:
            _flush()
            current_rooms = [room_name]
            current_n = n_lights

    _flush()
    return circuits

def _build_heating_circuits(
    rooms_with_convectors: list[tuple[str, int]],
    towel_warmer_rooms: list[str],
    codes: dict[str, str] | None = None,
) -> list[Circuit]:
    """Génère les circuits chauffage : convecteurs packés 2/circuit + 1 circuit
    par sèche-serviettes (1 SDB = 1 circuit dédié)."""
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
            label=_compact_rooms_label("Chauf.", chunk, codes),
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=list(chunk),
            n_devices=len(chunk),
        ))

    # Sèche-serviettes : 1 circuit dédié par instance, libellé indexé si
    # plusieurs SDB (le room_label inclut déjà l'index "SDB 1"/"SDB 2"…
    # propagé par generate_tableau).
    n_tw = len(towel_warmer_rooms)
    for i, room in enumerate(towel_warmer_rooms):
        suffix = f" {i+1}" if n_tw > 1 else ""
        circuits.append(Circuit(
            id=generate_circuit_id(),
            type=CircuitType.TOWEL_WARMER,
            label=f"Sèche-serviettes{suffix}",
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=[room],
            n_devices=1,
        ))

    return circuits


def _build_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
    codes: dict[str, str] | None = None,
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leurs n_sockets → circuits de
    SOCKET_MAX_PER_CIRCUIT (8) prises max. Pièces dépassant la limite prennent
    un/des circuit(s) dédié(s) découpés, les plus petites sont packées ensemble."""
    circuits: list[Circuit] = []

    def _make(rooms: list[str], n: int) -> Circuit:
        return Circuit(
            id=generate_circuit_id(),
            type=CircuitType.SOCKET,
            label=_compact_rooms_label("PC", rooms, codes),
            breaker_amps=16,
            cable_section_mm2=1.5,
            rooms_served=list(rooms),
            n_devices=n,
        )

    # Pièces > 8 prises : circuits pleins dédiés ; le reliquat (< 8) retourne
    # dans le pool et se packe avec les autres pièces (salon 10 → 8 dédiées,
    # 2 avec les chambres) au lieu d'un circuit quasi vide.
    pool: list[tuple[str, int]] = []
    for room_name, n_sockets in rooms_with_sockets:
        while n_sockets > SOCKET_MAX_PER_CIRCUIT:
            circuits.append(_make([room_name], SOCKET_MAX_PER_CIRCUIT))
            n_sockets -= SOCKET_MAX_PER_CIRCUIT
        if n_sockets > 0:
            pool.append((room_name, n_sockets))

    sorted_rooms = sorted(pool, key=lambda x: -x[1])
    current_rooms: list[str] = []
    current_n = 0

    def _flush():
        nonlocal current_rooms, current_n
        if current_n > 0:
            circuits.append(_make(current_rooms, current_n))
        current_rooms = []
        current_n = 0

    for room_name, n_sockets in sorted_rooms:
        if current_n + n_sockets <= SOCKET_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_n += n_sockets
        else:
            _flush()
            current_rooms = [room_name]
            current_n = n_sockets

    _flush()
    return circuits


def _build_kitchen_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
) -> list[Circuit]:
    """Prises de cuisine : circuit dédié 20A / 2,5 mm², 6 prises max."""
    circuits: list[Circuit] = []
    for room_name, n_sockets in rooms_with_sockets:
        n_remaining = n_sockets
        while n_remaining > 0:
            chunk = min(n_remaining, KITCHEN_SOCKET_MAX_PER_CIRCUIT)
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.KITCHEN_SOCKET,
                label=f"Prises cuisine ×{chunk}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=[room_name],
                n_devices=chunk,
            ))
            n_remaining -= chunk
    return circuits


_SPECIALIZED_SPECS: dict[EquipmentType, tuple[int, float, str, bool, bool, CircuitType]] = {
    # (breaker_amps, cable_section_mm2, label, requires_type_a, requires_type_f, circuit_type)
    EquipmentType.OVEN:            (20, 2.5, "Four",           False, False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.COOKTOP:         (32, 6.0, "Plaque cuisson", True,  False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.DISHWASHER:      (20, 2.5, "Lave-vaisselle", False, False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.WASHING_MACHINE: (20, 2.5, "Lave-linge",     True,  False, CircuitType.LAUNDRY),
    EquipmentType.DRYER:           (20, 2.5, "Sèche-linge",    False, False, CircuitType.LAUNDRY),
    EquipmentType.BOILER:          (20, 2.5, "Cumulus (ECS)", False, False, CircuitType.BOILER),
    EquipmentType.VMC:             (16, 1.5, "VMC",            True,  False, CircuitType.VMC),
    EquipmentType.HEAT_PUMP:       (32, 6.0, "Pompe à chaleur", False, True, CircuitType.HEAT_PUMP),
    EquipmentType.EV_CHARGER:      (32, 6.0, "Borne véhicule", False, True, CircuitType.EV_CHARGER),
}


def _build_specialized_circuits(
    rooms_by_type: dict[EquipmentType, list[str]],
) -> list[Circuit]:
    """Génère 1 circuit par instance d'appareil spécialisé.

    rooms_by_type[eq] = liste des pièces où l'appareil est installé (1 entrée
    par instance, dans l'ordre où elles ont été rencontrées dans le devis).
    """
    circuits: list[Circuit] = []
    for eq_type, rooms in rooms_by_type.items():
        if eq_type not in _SPECIALIZED_SPECS or not rooms:
            continue
        amps, section, label, type_a, type_f, ctype = _SPECIALIZED_SPECS[eq_type]
        n = len(rooms)
        for i, room in enumerate(rooms):
            suffix = f" {i+1}" if n > 1 else ""
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=ctype,
                label=f"{label}{suffix}",
                breaker_amps=amps,
                cable_section_mm2=section,
                rooms_served=[room],
                n_devices=1,
                requires_type_a=type_a,
                requires_type_f=type_f,
            ))
    return circuits


# Min 2 DDR par installation domestique (NFC C15-100 tableau 10-1G), même
# en T1 studio. Au-delà, on suit la règle cabinet pour les typologies plus
# grandes (besoin de séparer en zones indépendantes).
_TYPO_RCD_RULE = {"T1": 2, "T2": 2, "T3": 3, "T4": 4, "T5": 4}
MAX_BREAKERS_PER_RCD = 8
MAX_RCD_AMPS = 63  # calibre max d'un interrupteur différentiel (règle cabinet 2026-09-07)


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

# Codes pièces courts pour les libellés d'étiquettes (catégorie NFC → code).
_CATEGORY_CODES: dict[str, str] = {
    NFCCategory.LIVINGROOM.value: "SEJ",
    NFCCategory.KITCHEN.value: "CUIS",
    NFCCategory.BEDROOM.value: "CH",
    NFCCategory.BATH.value: "BAIN",
    NFCCategory.WC.value: "WC",
    NFCCategory.STORAGE.value: "CEL",
    NFCCategory.ENTRY.value: "DGT",
    NFCCategory.OUTDOOR.value: "EXT",
    NFCCategory.GARAGE.value: "GAR",
    NFCCategory.UNKNOWN.value: "DIV",
}


def _room_codes(rooms: list[tuple[str, NFCCategory]]) -> dict[str, str]:
    """label pièce → code court (« CH2 », « BUR », « BAIN »). Index ajouté
    seulement quand plusieurs pièces partagent le même code. « Bureau » est
    rangé en Chambre par le devis mais garde son code propre."""
    base: list[tuple[str, str]] = []
    for label, cat in rooms:
        code = "BUR" if "bureau" in label.lower() else _CATEGORY_CODES.get(cat.value, "DIV")
        base.append((label, code))
    totals: dict[str, int] = {}
    for _, code in base:
        totals[code] = totals.get(code, 0) + 1
    seen: dict[str, int] = {}
    out: dict[str, str] = {}
    for label, code in base:
        seen[code] = seen.get(code, 0) + 1
        out[label] = f"{code}{seen[code]}" if totals[code] > 1 else code
    return out


def _gtl_sockets_circuit() -> Circuit:
    """Prises GTL ×2 : fournies avec le lot tableau, absentes du catalogue,
    mais toujours sur le schéma et l'ID type A (règle cabinet 2026-09-07)."""
    return Circuit(
        id=generate_circuit_id(),
        type=CircuitType.SOCKET,
        label="Prises GTL ×2",
        breaker_amps=16,
        cable_section_mm2=1.5,
        rooms_served=[],
        n_devices=2,
        requires_type_a=True,
    )


def _ceil_to_normalized(x: float) -> int:
    """Arrondi au calibre normalisé supérieur dans {25, 40, 63, 80, 100, 125}."""
    idx = bisect.bisect_left(_NORMALIZED_RCD_AMPS, x)
    if idx >= len(_NORMALIZED_RCD_AMPS):
        return _NORMALIZED_RCD_AMPS[-1]
    return _NORMALIZED_RCD_AMPS[idx]


def _compute_rcd_amps(circuits: list[Circuit]) -> int:
    """Calibre RCD = Σ(chauffage + ECS) + (Σ autres usages) / 2, arrondi normalisé.

    NFC C15-100 tableau 10-1G : tout ce qui chauffe est compté plein pot
    (fonctionne en continu) — convecteurs, sèche-serviettes, ET le cumulus
    (ECS = eau chaude sanitaire, type BOILER chez nous). Les autres usages
    (prises, éclairage, électroménager non-chauffant) prennent un coefficient
    de simultanéité 0.5.
    """
    return _ceil_to_normalized(_raw_rcd_amps(circuits))


_HEAT_CIRCUIT_TYPES = (
    CircuitType.HEATING,
    CircuitType.TOWEL_WARMER,
    CircuitType.BOILER,
    CircuitType.HEAT_PUMP,
)


def _raw_rcd_amps(circuits: list[Circuit]) -> float:
    heat = sum(c.breaker_amps for c in circuits if c.type in _HEAT_CIRCUIT_TYPES)
    non_heat = sum(c.breaker_amps for c in circuits if c.type not in _HEAT_CIRCUIT_TYPES)
    return non_heat / 2 + heat


def generate_tableau(
    devis_global: DevisGlobal,
    heating_enabled: bool = True,
    typology_override: Optional[str] = None,
    room_labels: Optional[dict[str, str]] = None,
) -> Tableau:
    """Orchestre les 7 phases pour produire un Tableau complet.

    room_labels : mapping optionnel `room_id → label affiché`. Si fourni,
    on utilise ces labels (préserve la numérotation pastille même après
    suppression d'une pièce intermédiaire — sinon `cat_seen` ré-indexerait
    "Chambre 3" en "Chambre 2" après drag-out de "Chambre 2"). Si absent
    ou ne contient pas un room_id, fallback sur la numérotation `cat_seen`.
    """

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
    rooms_with_kitchen_sockets: list[tuple[str, int]] = []
    rooms_with_convectors: list[tuple[str, int]] = []
    towel_warmer_rooms: list[str] = []
    spec_rooms: dict[EquipmentType, list[str]] = {}

    room_cats: list[tuple[str, NFCCategory]] = []
    cat_seen: dict[str, int] = {}
    cat_total: dict[str, int] = {}
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = (
            (room_labels or {}).get(d.room_id)
            or (f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat)
        )
        room_cats.append((room_label, d.nfc_category))

        n_light = d.items.get(EquipmentType.LIGHT_POINT, 0)
        if n_light > 0:
            rooms_with_lights.append((room_label, n_light))

        n_sock = d.items.get(EquipmentType.SOCKET, 0)
        if n_sock > 0:
            if d.nfc_category == NFCCategory.KITCHEN:
                rooms_with_kitchen_sockets.append((room_label, n_sock))
            else:
                rooms_with_sockets.append((room_label, n_sock))

        n_conv = d.items.get(EquipmentType.CONVECTOR, 0)
        if n_conv > 0:
            rooms_with_convectors.append((room_label, n_conv))

        n_tw = d.items.get(EquipmentType.TOWEL_WARMER, 0)
        for _ in range(n_tw):
            towel_warmer_rooms.append(room_label)

        for eq_type in (EquipmentType.OVEN, EquipmentType.COOKTOP,
                        EquipmentType.DISHWASHER,
                        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER,
                        EquipmentType.BOILER, EquipmentType.VMC,
                        EquipmentType.HEAT_PUMP, EquipmentType.EV_CHARGER):
            n_eq = d.items.get(eq_type, 0)
            if n_eq > 0:
                spec_rooms.setdefault(eq_type, []).extend(
                    [room_label] * n_eq
                )

    # Phase 2-5 : générer circuits
    codes = _room_codes(room_cats)
    circuits: list[Circuit] = []
    circuits.extend(_build_lighting_circuits(rooms_with_lights, codes))
    circuits.extend(_build_socket_circuits(rooms_with_sockets, codes))
    circuits.append(_gtl_sockets_circuit())
    circuits.extend(_build_kitchen_socket_circuits(rooms_with_kitchen_sockets))
    if heating_enabled:
        circuits.extend(_build_heating_circuits(rooms_with_convectors,
                                                 towel_warmer_rooms, codes))
    circuits.extend(_build_specialized_circuits(spec_rooms))

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
    """Répartit les circuits par famille de différentiel (A / F / AC).

    - Type A : circuits requires_type_a (plaque, lave-linge, VMC, prises GTL)
      + UN seul circuit éclairage (le plus chargé).
    - Type F : circuits requires_type_f (pompe à chaleur, borne véhicule).
    - Type AC : le reste ; les autres éclairages y sont posés en premier, un
      par ID, pour qu'un ID qui saute n'éteigne pas tout le logement.
    Chaque circuit va sur l'ID le moins chargé de sa famille qui tient les deux
    contraintes : MAX_BREAKERS_PER_RCD (8) et calibre ≤ MAX_RCD_AMPS (63 A) ;
    sinon un nouvel ID de la même famille est ouvert. Le total est complété
    par des ID AC vides jusqu'à n_rcds (min typologie/surface). 30 mA.
    """
    a_circuits = [c for c in circuits if c.requires_type_a]
    f_circuits = [c for c in circuits
                  if c.requires_type_f and not c.requires_type_a]
    rest = [c for c in circuits
            if not c.requires_type_a and not c.requires_type_f]
    lights = sorted((c for c in rest if c.type == CircuitType.LIGHTING),
                    key=lambda c: -c.n_devices)
    ac_circuits = [c for c in rest if c.type != CircuitType.LIGHTING]
    if lights:
        a_circuits.append(lights.pop(0))

    def _new_rcd(rcd_type: str) -> RCD:
        return RCD(id=generate_rcd_id(), rcd_type=rcd_type, amps=40,
                   sensitivity_ma=30, circuits=[])

    def _pack(items: list[Circuit], rcd_type: str, n_min: int) -> list[RCD]:
        rcds = [_new_rcd(rcd_type) for _ in range(n_min)]
        for c in items:
            fits = [r for r in rcds
                    if len(r.circuits) < MAX_BREAKERS_PER_RCD
                    and _raw_rcd_amps(r.circuits + [c]) <= MAX_RCD_AMPS]
            if not fits:
                rcds.append(_new_rcd(rcd_type))
                fits = [rcds[-1]]
            target = min(fits, key=lambda r: (_raw_rcd_amps(r.circuits), len(r.circuits)))
            target.circuits.append(c)
        return rcds

    by_amps = lambda cs: sorted(cs, key=lambda c: -c.breaker_amps)
    n_a = math.ceil(len(a_circuits) / MAX_BREAKERS_PER_RCD)
    n_f = math.ceil(len(f_circuits) / MAX_BREAKERS_PER_RCD)
    n_ac_min = math.ceil((len(ac_circuits) + len(lights)) / MAX_BREAKERS_PER_RCD)
    n_ac = max(n_ac_min, n_rcds - n_a - n_f, 0)

    rcds: list[RCD] = []
    rcds.extend(_pack(by_amps(a_circuits), "A", n_a))
    rcds.extend(_pack(by_amps(f_circuits), "F", n_f))
    # Éclairages d'abord (un par ID AC), puis le reste par ampérage décroissant.
    rcds.extend(_pack(lights + by_amps(ac_circuits), "AC", n_ac))

    while len(rcds) < n_rcds:
        rcds.append(_new_rcd("AC"))

    for rcd in rcds:
        rcd.amps = _compute_rcd_amps(rcd.circuits)
    return rcds

