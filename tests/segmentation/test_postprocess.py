import numpy as np
from src.segmentation.postprocess import (
    panoptic_to_rooms, walls_mask_to_output, simplify_polygon,
)
from src.segmentation.preprocess import LetterboxInfo


def _info_identity(size=100):
    return LetterboxInfo(orig_h=size, orig_w=size, target_size=size, scale=1.0,
                         pad_top=0, pad_left=0, pad_bottom=0, pad_right=0)


def test_panoptic_to_rooms_basic():
    seg = np.zeros((100, 100), dtype=np.int32)
    seg[10:30, 10:30] = 1  # segment id 1
    seg[50:90, 50:90] = 2  # segment id 2
    segments_info = [
        {"id": 1, "label_id": 2, "score": 0.9},   # Kitchen
        {"id": 2, "label_id": 5, "score": 0.85},  # Bath
    ]
    info = _info_identity()
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(100, 100))
    assert len(rooms) == 2
    types = {r["type"] for r in rooms}
    assert types == {"Kitchen", "Bath"}


def test_panoptic_filters_low_score():
    seg = np.zeros((100, 100), dtype=np.int32)
    seg[10:30, 10:30] = 1
    segments_info = [{"id": 1, "label_id": 2, "score": 0.3}]
    info = _info_identity()
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(100, 100))
    assert rooms == []


def test_panoptic_filters_small_area():
    seg = np.zeros((1000, 1000), dtype=np.int32)
    seg[0:5, 0:5] = 1  # 25 pixels = 0.0025% of 1M
    segments_info = [{"id": 1, "label_id": 2, "score": 0.9}]
    info = LetterboxInfo(1000, 1000, 1000, 1.0, 0, 0, 0, 0)
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(1000, 1000))
    assert rooms == []


def test_walls_mask_output():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[40:60, :] = 1
    info = _info_identity()
    out = walls_mask_to_output(mask, info, plan_id="test", out_dir="/tmp")
    assert out.skeleton_paths_count >= 0
    assert "/tmp/test_walls.png" in out.mask_path


def test_simplify_polygon_reduces_points():
    contour = np.array([[i, 0] for i in range(100)] +
                       [[100, j] for j in range(100)] +
                       [[100 - i, 100] for i in range(100)] +
                       [[0, 100 - j] for j in range(100)], dtype=np.int32)
    simplified = simplify_polygon(contour, epsilon_ratio=0.005)
    assert len(simplified) < 20
    assert len(simplified) >= 4
