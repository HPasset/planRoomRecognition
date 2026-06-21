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


import json
import pandas as pd
from scripts.msd_to_panoptic import write_dataset, split_plan_ids


def test_split_plan_ids_deterministic_and_disjoint():
    ids = [str(i) for i in range(100)]
    s1 = split_plan_ids(ids, seed=42, val_frac=0.1, test_frac=0.1)
    s2 = split_plan_ids(ids, seed=42, val_frac=0.1, test_frac=0.1)
    assert s1 == s2
    allid = set(s1["train"]) | set(s1["val"]) | set(s1["test"])
    assert allid == set(ids)
    assert not (set(s1["train"]) & set(s1["val"]))
    assert len(s1["val"]) == 10 and len(s1["test"]) == 10


def test_write_dataset_smoke(tmp_path):
    room = "POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))"
    wall = "POLYGON ((0 4, 4 4, 4 4.2, 0 4.2, 0 4))"
    df = pd.DataFrame([
        {"plan_id": 1, "entity_type": "area", "roomtype": "Bedroom", "geom": room},
        {"plan_id": 1, "entity_type": "separator", "roomtype": "Structure", "geom": wall},
        {"plan_id": 2, "entity_type": "area", "roomtype": "Kitchen", "geom": room},
    ])
    write_dataset(df, tmp_path, size=64, margin=4, seed=0, val_frac=0.5, test_frac=0.0)

    splits = json.loads((tmp_path / "splits.json").read_text())
    assert set(splits) == {"train", "val", "test"}
    ids = splits["train"] + splits["val"] + splits["test"]
    assert sorted(ids) == ["1", "2"]
    for sid, split in [(i, s) for s in splits for i in splits[s]]:
        for sub in ("images", "semantic", "instance"):
            assert (tmp_path / sub / split / f"{sid}.png").exists()
