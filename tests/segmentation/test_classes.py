from src.segmentation.classes import (
    NUM_CLASSES, CLASS_NAMES, CLASS_ID,
    CUBICASA_TO_C2, ROOM_CLASS_IDS, STRUCTURAL_CLASS_IDS,
)


def test_num_classes_is_ten():
    assert NUM_CLASSES == 10


def test_class_names_ordered():
    assert CLASS_NAMES[0] == "Background"
    assert CLASS_NAMES[1] == "Wall"
    assert CLASS_NAMES[2] == "Kitchen"
    assert CLASS_NAMES[9] == "Outdoor"


def test_class_id_mapping():
    assert CLASS_ID["Kitchen"] == 2
    assert CLASS_ID["Outdoor"] == 9


def test_cubicasa_mapping_handles_synonyms():
    assert CUBICASA_TO_C2("Kitchen") == 2
    assert CUBICASA_TO_C2("Hall") == 6  # Entry
    assert CUBICASA_TO_C2("Closet") == 7  # Storage
    assert CUBICASA_TO_C2("Pantry") == 7
    assert CUBICASA_TO_C2("Railing") == 0  # ignored → Background
    assert CUBICASA_TO_C2("Undefined") == 0
    assert CUBICASA_TO_C2("Unknown_label_xyz") == 0  # default fallback


def test_room_class_ids_excludes_background_and_wall():
    assert 0 not in ROOM_CLASS_IDS
    assert 1 not in ROOM_CLASS_IDS
    assert ROOM_CLASS_IDS == [2, 3, 4, 5, 6, 7, 8, 9]


def test_structural_class_ids():
    assert STRUCTURAL_CLASS_IDS == [1]  # walls only
