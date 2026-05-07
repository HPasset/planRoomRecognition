import pytest
from pydantic import ValidationError
from src.segmentation.schema import RoomDetection, WallsOutput, SegmentationOutput


def _valid_room():
    return dict(
        id="room_001", type="Kitchen", type_id=2,
        polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        bbox=[0, 0, 10, 10], area_pixels=100, confidence=0.9,
    )


def test_room_detection_valid():
    r = RoomDetection(**_valid_room())
    assert r.type == "Kitchen"
    assert len(r.polygon) == 4


def test_room_detection_polygon_min_3_points():
    data = _valid_room()
    data["polygon"] = [[0, 0], [10, 10]]
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_room_detection_confidence_range():
    data = _valid_room()
    data["confidence"] = 1.5
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_room_detection_type_must_match_type_id():
    data = _valid_room()
    data["type"] = "Bath"
    data["type_id"] = 2  # mismatch
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_segmentation_output_serializable():
    out = SegmentationOutput(
        plan_id="plan_001.png",
        image_size=[1024, 768],
        model_version="mask2former-swin-s-batia-v0.1",
        inference_time_ms=1500,
        rooms=[RoomDetection(**_valid_room())],
        walls=WallsOutput(mask_rle="abc", mask_path="/tmp/w.png", skeleton_paths_count=12),
        warnings=[],
    )
    json_str = out.model_dump_json()
    restored = SegmentationOutput.model_validate_json(json_str)
    assert restored.plan_id == "plan_001.png"
    assert restored.rooms[0].type == "Kitchen"
