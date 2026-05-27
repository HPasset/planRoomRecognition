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


def test_cubicasa_real_labels_validated():
    """Real CubiCasa SVG labels (audited from 500 plans, 2026-05-07)."""
    # Critical fix: Bedroom (one word) — was previously missing
    assert CUBICASA_TO_C2("Bedroom") == 4  # BedRoom
    # Entry variants
    assert CUBICASA_TO_C2("Lobby") == 6
    assert CUBICASA_TO_C2("DraughtLobby") == 6
    assert CUBICASA_TO_C2("Corridor") == 6
    # Outdoor variants
    assert CUBICASA_TO_C2("Balcony") == 9
    assert CUBICASA_TO_C2("Terrace") == 9
    assert CUBICASA_TO_C2("CoveredArea") == 9
    # Storage variants
    assert CUBICASA_TO_C2("WalkIn") == 7
    assert CUBICASA_TO_C2("CoatCloset") == 7
    assert CUBICASA_TO_C2("Utility") == 7
    assert CUBICASA_TO_C2("Laundry") == 7
    assert CUBICASA_TO_C2("DressingRoom") == 7
    assert CUBICASA_TO_C2("TechnicalRoom") == 7
    assert CUBICASA_TO_C2("Boiler") == 7
    assert CUBICASA_TO_C2("Attic") == 7
    assert CUBICASA_TO_C2("Basement") == 7
    # Bath variants
    assert CUBICASA_TO_C2("Shower") == 5
    # LivingRoom variants
    assert CUBICASA_TO_C2("Dining") == 3
    assert CUBICASA_TO_C2("Den") == 3
    # Kitchen variants
    assert CUBICASA_TO_C2("Kitchenette") == 2
    # Garage variants
    assert CUBICASA_TO_C2("CarPort") == 8
    # Ambiguous labels stay Background (intentional)
    assert CUBICASA_TO_C2("Room") == 0
    assert CUBICASA_TO_C2("UserDefined") == 0
    assert CUBICASA_TO_C2("Office") == 0  # too ambiguous: study or workplace?


def test_room_class_ids_excludes_background_and_wall():
    assert 0 not in ROOM_CLASS_IDS
    assert 1 not in ROOM_CLASS_IDS
    assert ROOM_CLASS_IDS == [2, 3, 4, 5, 6, 7, 8, 9]


def test_structural_class_ids():
    assert STRUCTURAL_CLASS_IDS == [1]  # walls only
