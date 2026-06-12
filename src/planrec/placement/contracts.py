"""Dataclasses d'entrée/sortie du moteur de placement. Coordonnées en px."""
from __future__ import annotations
from dataclasses import dataclass, field

BBox = tuple[int, int, int, int]      # (x1, y1, x2, y2)
Point = tuple[int, int]


@dataclass
class Detection:
    """Une détection objet (YOLO) : mobilier ou ouverture."""
    cls: str                # "Bed", "door", "window", "WashBasin"…
    bbox: BBox
    confidence: float


@dataclass
class RoomContext:
    """Tout ce que le moteur a besoin pour placer dans UNE pièce."""
    room_type: str          # ex "BedRoom"
    polygon: list[Point]    # sommets du polygone pièce (segmentation)
    furniture: list[Detection] = field(default_factory=list)   # YOLO brique A
    openings: list[Detection] = field(default_factory=list)    # YOLO doors/windows
    wall_lines: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass
class PlacedEquipment:
    """Un équipement positionné par le moteur."""
    equip_key: str          # clé EQUIP_TYPES : "Prise", "RJ45", "Switch"…
    x: int
    y: int
    confidence: float
    uncertain: bool
    reason: str
