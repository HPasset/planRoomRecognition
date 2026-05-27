"""Prix unitaires HT par équipement + taux de TVA pour génération du devis.

Valeurs indicatives marché France 2025 (matériel Legrand/Schneider standard +
main d'œuvre électricien ~50 €/h, fourniture+pose). À ajuster par l'utilisateur
selon sa grille tarifaire réelle.
"""
from __future__ import annotations

from src.planrec.nfc_rules import EquipmentType


# Prix unitaires HT par défaut (€) — fourniture + pose
DEFAULT_PRICES_HT: dict[EquipmentType, float] = {
    EquipmentType.SOCKET: 25.0,            # prise courant 16A standard
    EquipmentType.RJ45: 40.0,              # prise RJ45 cat 6
    EquipmentType.LIGHT_POINT: 50.0,       # point lumineux simple + LED
    EquipmentType.SWITCH: 18.0,            # va-et-vient ou simple allumage
    EquipmentType.SPECIAL_FEED: 70.0,      # alimentation spécialisée (16A ou 32A)
}


# Libellés FR pour l'UI (selectbox équipement dans le devis)
EQUIPMENT_LABELS_FR: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise de courant",
    EquipmentType.RJ45: "Prise RJ45",
    EquipmentType.LIGHT_POINT: "Point lumineux",
    EquipmentType.SWITCH: "Interrupteur",
    EquipmentType.SPECIAL_FEED: "Alimentation spécialisée",
}

# Mapping inverse (label FR → enum)
LABEL_FR_TO_EQUIPMENT: dict[str, EquipmentType] = {
    v: k for k, v in EQUIPMENT_LABELS_FR.items()
}

EQUIPMENT_LABELS_LIST = list(LABEL_FR_TO_EQUIPMENT.keys())


# Taux de TVA disponibles
TVA_OPTIONS: dict[str, float] = {
    "Neuf 20%": 0.20,
    "Rénovation > 2 ans 10%": 0.10,
    "Rénovation énergie 5.5%": 0.055,
}
TVA_DEFAULT = "Neuf 20%"


def compute_ttc(price_ht: float, tva_rate: float) -> float:
    """Prix TTC depuis HT et taux TVA (décimal, ex 0.20)."""
    return round(price_ht * (1.0 + tva_rate), 2)
