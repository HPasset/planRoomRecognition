from src.segmentation.classes import MSD_TO_C2, CLASS_ID


def test_msd_mapping_walls_and_rooms():
    assert MSD_TO_C2("Structure") == CLASS_ID["Wall"]
    assert MSD_TO_C2("Bedroom") == CLASS_ID["BedRoom"]
    assert MSD_TO_C2("Livingroom") == CLASS_ID["LivingRoom"]
    assert MSD_TO_C2("Dining") == CLASS_ID["LivingRoom"]
    assert MSD_TO_C2("Kitchen") == CLASS_ID["Kitchen"]
    assert MSD_TO_C2("Bathroom") == CLASS_ID["Bath"]
    assert MSD_TO_C2("Corridor") == CLASS_ID["Entry"]
    assert MSD_TO_C2("Storeroom") == CLASS_ID["Storage"]
    assert MSD_TO_C2("Balcony") == CLASS_ID["Outdoor"]


def test_msd_mapping_openings_and_stairs_to_background():
    for label in ("Door", "Window", "Entrance Door", "Stairs"):
        assert MSD_TO_C2(label) == CLASS_ID["Background"]


def test_msd_mapping_unknown_to_background():
    assert MSD_TO_C2("Patio") == CLASS_ID["Background"]


import numpy as np
from src.segmentation.classes import CLASS_ID
from scripts.msd_to_panoptic import rasterize_plan


def _poly(coords):
    inner = ", ".join(f"{x} {y}" for x, y in coords)
    return f"POLYGON (({inner}))"


def test_rasterize_plan_paints_room_then_walls_and_instances():
    room = _poly([(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)])
    wall_top = _poly([(0, 4), (4, 4), (4, 4.2), (0, 4.2), (0, 4)])
    entities = [
        {"roomtype": "Bedroom", "entity_type": "area", "geom": room},
        {"roomtype": "Structure", "entity_type": "separator", "geom": wall_top},
    ]
    image, semantic, instance = rasterize_plan(entities, size=64, margin=4)

    assert image.shape == (64, 64, 3) and image.dtype == np.uint8
    assert semantic.shape == (64, 64) and semantic.dtype == np.uint8
    assert instance.shape == (64, 64) and instance.dtype == np.uint16

    assert (semantic == CLASS_ID["BedRoom"]).sum() > 0
    assert (semantic == CLASS_ID["Wall"]).sum() > 0
    assert set(np.unique(instance)).issubset({0, 1})
    assert (instance == 1).sum() > 0
    assert instance[(semantic == CLASS_ID["Wall"])].max() == 0
