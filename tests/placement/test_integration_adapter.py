from src.planrec.placement.adapter import build_room_layout_index
from src.planrec.placement.contracts import Detection, RoomContext


def test_index_maps_room_type_idx_to_position():
    ctx = RoomContext(
        room_type="BedRoom",
        polygon=[(0, 0), (200, 0), (200, 200), (0, 200)],
        furniture=[Detection("Bed", (40, 2, 160, 90), 0.95)],
        openings=[Detection("door", (135, 195, 165, 200), 0.9)],
    )
    counts = {"Prise": 3, "RJ45": 1, "Switch": 1, "LightPoint": 1}
    index = build_room_layout_index("Chambre 1", ctx, counts)
    assert ("Chambre 1", "Prise", 0) in index
    assert ("Chambre 1", "Prise", 2) in index
    assert ("Chambre 1", "Switch", 0) in index
    pe = index[("Chambre 1", "Prise", 0)]
    assert hasattr(pe, "x") and hasattr(pe, "uncertain")


def test_non_bedroom_returns_empty_index():
    ctx = RoomContext(room_type="Kitchen", polygon=[(0, 0), (10, 0), (10, 10), (0, 10)])
    assert build_room_layout_index("Cuisine", ctx, {"Prise": 6}) == {}
