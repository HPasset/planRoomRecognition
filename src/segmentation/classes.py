"""10-class taxonomy (C2) for room segmentation, with CubiCasa mapping."""
from typing import Final


CLASS_NAMES: Final[tuple[str, ...]] = (
    "Background",   # 0
    "Wall",         # 1
    "Kitchen",      # 2
    "LivingRoom",   # 3
    "BedRoom",      # 4
    "Bath",         # 5  (WC fusionné)
    "Entry",        # 6  (Hall + Entry)
    "Storage",      # 7  (Closet + Pantry + Storage)
    "Garage",       # 8
    "Outdoor",      # 9
)

NUM_CLASSES: Final[int] = len(CLASS_NAMES)

CLASS_ID: Final[dict[str, int]] = {name: i for i, name in enumerate(CLASS_NAMES)}

# Pixels qui appartiennent à des "rooms" (instances séparables)
ROOM_CLASS_IDS: Final[list[int]] = [CLASS_ID[n] for n in (
    "Kitchen", "LivingRoom", "BedRoom", "Bath",
    "Entry", "Storage", "Garage", "Outdoor",
)]

# Pixels structurels (pas des rooms instanciables)
STRUCTURAL_CLASS_IDS: Final[list[int]] = [CLASS_ID["Wall"]]


# CubiCasa label → C2 class id.
# Real CubiCasa SVG labels validated by inspection of 500 plans (2026-05-07).
_CUBICASA_RAW_MAP: dict[str, str] = {
    "Background": "Background",
    "Wall": "Wall",
    # Kitchen
    "Kitchen": "Kitchen",
    "Kitchenette": "Kitchen",
    # LivingRoom (séjour, salon, salle à manger, den)
    "LivingRoom": "LivingRoom",
    "Living Room": "LivingRoom",
    "Dining": "LivingRoom",
    "Den": "LivingRoom",
    # BedRoom (chambre, bureau privatif)
    "Bedroom": "BedRoom",      # ← real CubiCasa label
    "BedRoom": "BedRoom",       # legacy alias
    "Bed Room": "BedRoom",      # legacy alias
    # Bath (sdb + WC + douche)
    "Bath": "Bath",
    "Bathroom": "Bath",
    "WC": "Bath",
    "Shower": "Bath",
    # Entry (entrée, hall, couloir, vestibule)
    "Entry": "Entry",
    "Hall": "Entry",
    "Lobby": "Entry",
    "DraughtLobby": "Entry",
    "Corridor": "Entry",
    # Storage (rangement, dressing, cellier, buanderie, technique)
    "Storage": "Storage",
    "Closet": "Storage",
    "CoatCloset": "Storage",
    "WalkIn": "Storage",
    "DressingRoom": "Storage",
    "Pantry": "Storage",
    "Utility": "Storage",
    "Laundry": "Storage",
    "TechnicalRoom": "Storage",
    "Boiler": "Storage",
    "Attic": "Storage",
    "Basement": "Storage",
    # Garage
    "Garage": "Garage",
    "CarPort": "Garage",
    # Outdoor (balcon, terrasse, jardin attenant)
    "Outdoor": "Outdoor",
    "Balcony": "Outdoor",
    "Terrace": "Outdoor",
    "CoveredArea": "Outdoor",
    # Everything else (Railing, Undefined, Room, UserDefined, Office, Sauna, ...) → Background
}


def CUBICASA_TO_C2(cubicasa_label: str) -> int:
    """Map a CubiCasa room label to a C2 class id. Unknown → Background (0)."""
    c2_name = _CUBICASA_RAW_MAP.get(cubicasa_label.strip(), "Background")
    return CLASS_ID[c2_name]


# MSD (Modified Swiss Dwellings) roomtype → C2 class id.
# Murs = "Structure" ; ouvertures (Door/Window/Entrance Door) gérées par YOLO
# en aval → Background ; "Stairs" absent de la taxo C2 → Background.
_MSD_RAW_MAP: dict[str, str] = {
    "Structure": "Wall",
    "Kitchen": "Kitchen",
    "Livingroom": "LivingRoom",
    "Dining": "LivingRoom",
    "Bedroom": "BedRoom",
    "Bathroom": "Bath",
    "Corridor": "Entry",
    "Storeroom": "Storage",
    "Balcony": "Outdoor",
    "Door": "Background",
    "Window": "Background",
    "Entrance Door": "Background",
    "Stairs": "Background",
}


def MSD_TO_C2(msd_roomtype: str) -> int:
    """Map un `roomtype` MSD vers un id de classe C2. Inconnu → Background (0)."""
    c2_name = _MSD_RAW_MAP.get(msd_roomtype.strip(), "Background")
    return CLASS_ID[c2_name]
