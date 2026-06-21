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
