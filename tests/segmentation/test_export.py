# tests/segmentation/test_export.py
from pathlib import Path
import numpy as np
from src.segmentation.cubicasa_export import (
    extract_room_polygons, rasterize_panoptic, RoomPolygon,
)


def test_extract_room_polygons(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    types = {p.class_id for p in polygons}
    # Walls (1), Kitchen (2), BedRoom (4), Bath (5), LivingRoom (3)
    assert {1, 2, 3, 4, 5}.issubset(types)


def test_rasterize_panoptic_shapes(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    sem, inst = rasterize_panoptic(polygons, image_size=(200, 200))
    assert sem.shape == (200, 200)
    assert sem.dtype == np.uint8
    assert inst.shape == (200, 200)
    assert inst.dtype == np.int32
    # Au moins 4 instances de pièces (excluant Wall)
    unique_inst = set(np.unique(inst).tolist()) - {0}  # 0 = unassigned
    assert len(unique_inst) >= 4


def test_rasterize_kitchen_pixels_present(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    sem, _ = rasterize_panoptic(polygons, image_size=(200, 200))
    assert (sem == 2).sum() > 1000  # Kitchen pixels
    assert (sem == 1).sum() > 0  # Wall pixels
