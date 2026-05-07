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


# CubiCasa label → C2 class id
_CUBICASA_RAW_MAP: dict[str, str] = {
    "Background": "Background",
    "Outdoor": "Outdoor",
    "Wall": "Wall",
    "Kitchen": "Kitchen",
    "LivingRoom": "LivingRoom",
    "Living Room": "LivingRoom",
    "BedRoom": "BedRoom",
    "Bed Room": "BedRoom",
    "Bath": "Bath",
    "WC": "Bath",
    "Bathroom": "Bath",
    "Hall": "Entry",
    "Entry": "Entry",
    "Storage": "Storage",
    "Closet": "Storage",
    "Pantry": "Storage",
    "Garage": "Garage",
    # Tout le reste (Railing, Undefined, Other, ...) → Background
}


def CUBICASA_TO_C2(cubicasa_label: str) -> int:
    """Map a CubiCasa room label to a C2 class id. Unknown → Background (0)."""
    c2_name = _CUBICASA_RAW_MAP.get(cubicasa_label.strip(), "Background")
    return CLASS_ID[c2_name]
