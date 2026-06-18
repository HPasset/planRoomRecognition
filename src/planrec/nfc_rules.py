"""Moteur de règles NF C 15-100 simplifié pour génération de devis quantitatif.

Source : règles métier batIA fournies par l'associé électricien (réunion 2026-05-24).
Reconnaissance des pièces (Brique B) + OCR contextuel → devis NFC quantifié sans
placement précis (le placement est V2 via Brique A YOLO meubles).

Architecture :
  - 8 catégories NFC : Chambre, WC, SDB, Cuisine, Cellier, Séjour, Dégagement, Extérieur
  - 5 types d'équipements : prise courant, prise RJ45, point lumineux, interrupteur,
    alimentation spécialisée
  - Mapping classe C2 (Brique B) → catégorie NFC : direct sauf pour Bath qui peut
    être SDB ou WC (déterminé par OCR contextuel)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import math


class NFCCategory(str, Enum):
    """Catégorie NFC dérivée de la classe C2 + contexte OCR."""
    BEDROOM = "Chambre"          # Chambre OU Bureau (mêmes règles)
    WC = "WC"
    BATH = "SalleDeBain"
    KITCHEN = "Cuisine"
    STORAGE = "CellierBuanderie"  # Cellier / Buanderie
    LIVINGROOM = "Sejour"
    ENTRY = "Degagement"          # Dégagement / Circulation
    OUTDOOR = "Exterieur"
    GARAGE = "Garage"             # Pas dans les règles, défaut = règles Cellier
    UNKNOWN = "Inconnu"


class EquipmentType(str, Enum):
    # Anciens types (préservés pour compatibilité)
    SOCKET = "prise_courant"
    RJ45 = "prise_rj45"
    LIGHT_POINT = "point_lumineux"
    SWITCH = "interrupteur"
    SPECIAL_FEED = "alimentation_specialisee"  # legacy, plus généré par compute_devis_for_room
    # NEW V1.2 — éclatement de SPECIAL_FEED en sous-types typés
    OVEN = "four"
    COOKTOP = "plaque_cuisson"
    DISHWASHER = "lave_vaisselle"
    WASHING_MACHINE = "lave_linge"
    DRYER = "seche_linge"
    BOILER = "chaudiere_cumulus"
    # NEW V1.2 — chauffage électrique
    CONVECTOR = "convecteur"
    TOWEL_WARMER = "seche_serviettes"
    # NEW v2 — VMC (auto), PAC + borne véhicule (manuels)
    VMC = "vmc"
    HEAT_PUMP = "pompe_a_chaleur"
    EV_CHARGER = "borne_vehicule"


# Appareils à alimentation dédiée fournis par l'occupant : l'artisan pose
# l'alimentation (prise/circuit), facturée et affichée comme « Alim spé »
# générique. Distinct du chauffage (Convecteur/Sèche-serviettes), qui a ses
# propres pastilles/lignes. Cf. retour métier 2026-06-16.
SPECIAL_FEED_EQUIPMENT_TYPES: frozenset[EquipmentType] = frozenset({
    EquipmentType.OVEN,
    EquipmentType.COOKTOP,
    EquipmentType.DISHWASHER,
    EquipmentType.WASHING_MACHINE,
    EquipmentType.DRYER,
    EquipmentType.BOILER,
})


# Mapping direct C2 → catégorie NFC (cas simple, sans contexte OCR).
# Bath est mappé à BATH par défaut ; un override via OCR peut le passer à WC.
C2_TO_NFC: dict[str, NFCCategory] = {
    "Kitchen": NFCCategory.KITCHEN,
    "LivingRoom": NFCCategory.LIVINGROOM,
    "BedRoom": NFCCategory.BEDROOM,
    "Bath": NFCCategory.BATH,           # par défaut, peut devenir WC via OCR
    "Entry": NFCCategory.ENTRY,
    "Storage": NFCCategory.STORAGE,
    "Garage": NFCCategory.GARAGE,
    "Outdoor": NFCCategory.OUTDOOR,
    # Background, Wall : ignorés (pas de pièce)
}


@dataclass
class Devis:
    """Devis quantitatif pour UNE pièce."""
    room_id: str
    nfc_category: NFCCategory
    surface_m2: float | None
    handicap: bool
    items: dict[EquipmentType, int] = field(default_factory=dict)
    special_feeds_detail: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    attenant: bool = False  # garage accolé à la maison (renseigné par la géométrie)

    @property
    def total_equipment(self) -> int:
        return sum(self.items.values())


def _convector_count(nfc_cat: NFCCategory, surface_m2: float | None) -> int:
    """Nombre de convecteurs pour une pièce chauffée.

    Surface connue → 1 convecteur / 20 m² (≈ 100 W/m², convecteur ~2000 W).
    Surface inconnue → forfait par type : séjour 2, chambre 1.
    """
    if surface_m2 is not None and surface_m2 > 0:
        return max(1, math.ceil(surface_m2 / 20))
    return 2 if nfc_cat == NFCCategory.LIVINGROOM else 1


def compute_devis_for_room(
    room_id: str,
    c2_class: str,
    surface_m2: float | None = None,
    handicap: bool = False,
    ocr_hint: str | None = None,
    heating_enabled: bool = True,    # NEW V1.2
) -> Devis:
    """Calcule le devis NFC pour une pièce.

    Args:
        room_id: identifiant unique de la pièce (ex: "room_001")
        c2_class: classe C2 prédite par Brique B (Kitchen, LivingRoom, ...)
        surface_m2: surface en m² (extrait OCR ou calculé). Optionnel.
        handicap: si True, applique les règles supplémentaires Norme handicap
        ocr_hint: texte OCR trouvé dans la pièce (ex: "WC", "SDB", "Bureau").
                  Utilisé pour désambiguïsation Bath→WC notamment.

    Returns:
        Devis pour la pièce.
    """
    nfc_cat = _resolve_nfc_category(c2_class, ocr_hint)
    devis = Devis(
        room_id=room_id, nfc_category=nfc_cat,
        surface_m2=surface_m2, handicap=handicap,
    )

    if nfc_cat == NFCCategory.BEDROOM:
        # 3 prises + 1 si handicap, 1 RJ45, 1 point lumineux, 1 interrupteur
        devis.items[EquipmentType.SOCKET] = 3 + (1 if handicap else 0)
        devis.items[EquipmentType.RJ45] = 1
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1

    elif nfc_cat == NFCCategory.WC:
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        if handicap:
            devis.items[EquipmentType.SOCKET] = 1

    elif nfc_cat == NFCCategory.BATH:
        # Central + applique au-dessus vasque
        devis.items[EquipmentType.LIGHT_POINT] = 2
        devis.items[EquipmentType.SWITCH] = 1
        devis.items[EquipmentType.SOCKET] = 1 + (1 if handicap else 0)
        if heating_enabled:
            devis.items[EquipmentType.TOWEL_WARMER] = 1
            devis.special_feeds_detail.append("Sèche-serviettes")
        devis.notes.append("⚠ Zone 60 cm autour douche/baignoire interdite")

    elif nfc_cat == NFCCategory.KITCHEN:
        # 6 prises normales (dont 4 au-dessus plan travail) + 3 alimentations
        # spécialisées (Plaque/Four/LV) affichées séparément. Cf. NFC C15-100
        # + retour métier 2026-06-03.
        # Les types OVEN/COOKTOP/DISHWASHER restent comptés à part pour
        # alimenter le tableau électrique (1 circuit dédié chacun) et sont
        # désormais affichés séparément comme alimentations spécialisées.
        devis.items[EquipmentType.SOCKET] = 6
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        # Circuits spécialisés typés (V1.2) — alimentent le tableau (calibres,
        # DDR) et sont facturés/affichés en « Alim spé » générique (2026-06-16).
        devis.items[EquipmentType.OVEN] = 1
        devis.items[EquipmentType.COOKTOP] = 1
        devis.items[EquipmentType.DISHWASHER] = 1
        devis.special_feeds_detail.extend([
            "Plaque de cuisson (32A)", "Four (16A)", "Lave-vaisselle (16A)",
        ])
        devis.notes.append(
            "6 prises normales (dont 4 au-dessus plan de travail) + 3 "
            "alimentations spécialisées (Plaque/Four/LV) affichées séparément"
        )

    elif nfc_cat == NFCCategory.STORAGE:
        # Cellier/Buanderie : 1 lumière + 1 prise + 3 circuits spécialisés typés
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        devis.items[EquipmentType.SOCKET] = 1
        devis.items[EquipmentType.WASHING_MACHINE] = 1
        devis.items[EquipmentType.DRYER] = 1
        devis.items[EquipmentType.BOILER] = 1
        devis.special_feeds_detail.extend([
            "Lave-linge (20A)", "Sèche-linge (16A)", "Cumulus",
        ])

    elif nfc_cat == NFCCategory.LIVINGROOM:
        # Séjour : 1 prise tous les 4 m², minimum 5 au total, DONT max 3
        # derrière TV (les 3 derrière TV font partie des 5 mini, pas en sus).
        # Cf. NFC C15-100 §771.314.2.1 + retour métier 2026-06-03.
        if surface_m2 is not None and surface_m2 > 0:
            n_sockets_total = max(5, int(round(surface_m2 / 4.0)))
            devis.notes.append(
                f"{n_sockets_total} prises au total réparties "
                f"(1 / 4 m² sur {surface_m2:.1f} m²)"
            )
        else:
            n_sockets_total = 5
            devis.notes.append(
                "Surface inconnue → minimum 5 prises (cf. NFC)"
            )
        devis.items[EquipmentType.SOCKET] = n_sockets_total
        devis.items[EquipmentType.RJ45] = 2
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        devis.notes.append(
            f"Dont max 3 derrière TV (incluses dans les {n_sockets_total})"
        )
        devis.notes.append("2 RJ45 derrière TV")

    elif nfc_cat == NFCCategory.ENTRY:
        # Dégagement : 1 lumière, 1 prise, commande à définir
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SOCKET] = 1
        devis.items[EquipmentType.SWITCH] = 1
        devis.notes.append("Quantité interrupteurs/poussoirs à valider (cf. règles)")

    elif nfc_cat == NFCCategory.OUTDOOR:
        # Extérieur : 1 lumière (au-dessus porte) + 1 simple allumage à voyant + 1 prise
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1  # simple allumage à voyant
        devis.items[EquipmentType.SOCKET] = 1
        devis.notes.append("Interrupteur à voyant, prise à côté baie vitrée")

    elif nfc_cat == NFCCategory.GARAGE:
        # Pas explicitement dans les règles → traité comme Cellier minimal
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SOCKET] = 1
        devis.items[EquipmentType.SWITCH] = 1
        devis.notes.append("Règles génériques (Garage non explicité dans le brief)")

    else:  # UNKNOWN
        devis.notes.append("Type de pièce non reconnu, devis vide")

    # Auto-génération chauffage électrique pour pièces principales (V1.2)
    if heating_enabled and nfc_cat in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM):
        devis.items[EquipmentType.CONVECTOR] = _convector_count(nfc_cat, surface_m2)

    return devis


def _resolve_nfc_category(c2_class: str, ocr_hint: str | None) -> NFCCategory:
    """Détermine la catégorie NFC depuis classe C2 + indice OCR.

    Cas spéciaux gérés :
      - Bath + OCR contient 'wc'/'toilette' → WC (règles plus légères)
      - Bath + OCR contient 'sdb'/'salle de bain'/'douche' → BATH (par défaut)
      - Storage + OCR contient 'garage'/'box' → GARAGE
    """
    base = C2_TO_NFC.get(c2_class, NFCCategory.UNKNOWN)
    if not ocr_hint:
        return base

    hint_lower = ocr_hint.lower()
    if base == NFCCategory.BATH:
        if any(w in hint_lower for w in ("wc", "toilette", "water-closet")):
            return NFCCategory.WC
    elif base == NFCCategory.STORAGE:
        if any(w in hint_lower for w in ("garage", "box")):
            return NFCCategory.GARAGE
    return base


@dataclass
class DevisGlobal:
    """Devis agrégé pour un plan complet (toutes pièces)."""
    per_room: list[Devis] = field(default_factory=list)
    handicap: bool = False

    @property
    def totals(self) -> dict[EquipmentType, int]:
        """Total par type d'équipement, agrégé sur toutes les pièces."""
        out: dict[EquipmentType, int] = {}
        for d in self.per_room:
            for eq, qty in d.items.items():
                out[eq] = out.get(eq, 0) + qty
        return out

    @property
    def all_special_feeds(self) -> list[str]:
        out: list[str] = []
        for d in self.per_room:
            for sf in d.special_feeds_detail:
                out.append(f"{d.room_id} ({d.nfc_category.value}): {sf}")
        return out


# Ordre de repli pour rattacher le lave-linge garanti quand aucun cellier
# n'est détecté. STORAGE absent volontairement : s'il existe, il porte déjà
# un lave-linge → garantie satisfaite avant d'arriver ici.
_WASHING_FALLBACK_PRIORITY: tuple[NFCCategory, ...] = (
    NFCCategory.BATH,
    NFCCategory.KITCHEN,
    NFCCategory.GARAGE,
    NFCCategory.ENTRY,
)


def _ensure_washing_machine(out: DevisGlobal) -> None:
    """Garantit au moins un lave-linge 20A par logement (retour métier 2026-06-16).

    - Si une pièce porte déjà un lave-linge (cellier détecté) → ne rien faire.
    - Sinon → rattacher 1 lave-linge à la première pièce de repli trouvée
      selon `_WASHING_FALLBACK_PRIORITY`.
    - Si aucune pièce candidate plausible (ex. logement réduit à un WC ou à des
      chambres) → ne rien faire : pas de lave-linge fantôme (retour métier
      2026-06-17).
    """
    for d in out.per_room:
        if d.items.get(EquipmentType.WASHING_MACHINE, 0) >= 1:
            return  # garantie déjà satisfaite, pas de doublon

    for cat in _WASHING_FALLBACK_PRIORITY:
        for d in out.per_room:
            if d.nfc_category == cat:
                d.items[EquipmentType.WASHING_MACHINE] = 1
                d.special_feeds_detail.append("Lave-linge (20A)")
                return


# Repli de placement de la VMC (auto, 1/logement) : cellier → SDB.
_VMC_FALLBACK_PRIORITY: tuple[NFCCategory, ...] = (
    NFCCategory.STORAGE,
    NFCCategory.BATH,
)


def _ensure_vmc(out: DevisGlobal) -> None:
    """1 VMC par logement (auto). Placement cellier → SDB ; rien sinon."""
    for d in out.per_room:
        if d.items.get(EquipmentType.VMC, 0) >= 1:
            return
    for cat in _VMC_FALLBACK_PRIORITY:
        for d in out.per_room:
            if d.nfc_category == cat:
                d.items[EquipmentType.VMC] = 1
                return


def _ensure_ecs(out: DevisGlobal) -> None:
    """Garantit une alim ECS (cumulus) hors cellier : garage si attenant → SDB.

    Le cellier génère déjà l'ECS via sa propre règle. Ici on couvre le cas sans
    cellier : garage seulement s'il est attenant à la maison, sinon SDB. Rien si
    aucune pièce candidate (cohérent garantie lave-linge, 2026-06-17).
    """
    for d in out.per_room:
        if d.items.get(EquipmentType.BOILER, 0) >= 1:
            return
    for d in out.per_room:
        if d.nfc_category == NFCCategory.GARAGE and d.attenant:
            d.items[EquipmentType.BOILER] = 1
            d.special_feeds_detail.append("Cumulus (ECS)")
            return
    for d in out.per_room:
        if d.nfc_category == NFCCategory.BATH:
            d.items[EquipmentType.BOILER] = 1
            d.special_feeds_detail.append("Cumulus (ECS)")
            return


def compute_devis_global(
    rooms: list[dict],
    handicap: bool = False,
    heating_enabled: bool = True,     # NEW V1.2
) -> DevisGlobal:
    """Calcule le devis global pour une liste de pièces.

    Args:
        rooms: liste de dict avec clés:
            - id (str)
            - c2_class (str): classe C2 Brique B
            - surface_m2 (float | None): optionnel
            - ocr_hint (str | None): texte OCR contextuel
        handicap: applique les règles handicap à toutes les pièces
        heating_enabled: si True, génère CONVECTOR pour séjour/chambres et
                         TOWEL_WARMER pour SdB

    Returns:
        DevisGlobal avec per_room + totaux agrégés
    """
    out = DevisGlobal(handicap=handicap)
    for r in rooms:
        devis = compute_devis_for_room(
            room_id=r["id"],
            c2_class=r["c2_class"],
            surface_m2=r.get("surface_m2"),
            handicap=handicap,
            ocr_hint=r.get("ocr_hint"),
            heating_enabled=heating_enabled,
        )
        devis.attenant = bool(r.get("attenant", False))
        out.per_room.append(devis)
    _ensure_vmc(out)
    _ensure_washing_machine(out)
    _ensure_ecs(out)
    return out
