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


def test_parse_points_skips_bad_tokens():
    """Malformed tokens should be skipped, not discard the entire polygon."""
    from src.segmentation.cubicasa_export import _parse_points
    arr = _parse_points("10,10 100,10 abc 100,100 10,100")
    # 4 valid pairs (the 'abc' token is dropped, total 8 floats = 4 points)
    assert arr.shape == (4, 2)


def test_parse_points_skips_nan_inf():
    """NaN/Inf coordinates must not propagate to the rasterizer."""
    from src.segmentation.cubicasa_export import _parse_points
    arr = _parse_points("10,10 nan,inf 100,100 10,100")
    # Only finite pairs survive
    import numpy as np
    assert np.all(np.isfinite(arr))


def test_wall_priority_does_not_steal_room_polygon():
    """A polygon with own class='Kitchen' nested under <g class='Wall'> must remain Kitchen."""
    from src.segmentation.cubicasa_export import _label_to_class_id
    # Direct Kitchen label, ancestor Wall label
    cid = _label_to_class_id(own=["Kitchen"], ancestors=["Wall"])
    assert cid == 2  # Kitchen, not Wall
    # But a polygon with no own labels but ancestor Wall should be Wall
    cid2 = _label_to_class_id(own=[], ancestors=["Wall"])
    assert cid2 == 1  # Wall (fallback)
