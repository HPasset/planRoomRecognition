from src.planrec.placement.contracts import Detection, RoomContext, PlacedEquipment


def test_detection_holds_bbox_and_conf():
    d = Detection(cls="Bed", bbox=(10, 20, 110, 220), confidence=0.97)
    assert d.cls == "Bed"
    assert d.bbox == (10, 20, 110, 220)
    assert d.confidence == 0.97


def test_room_context_defaults_to_empty_lists():
    ctx = RoomContext(room_type="BedRoom", polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])
    assert ctx.furniture == []
    assert ctx.openings == []
    assert ctx.wall_lines == []


def test_placed_equipment_carries_uncertainty():
    pe = PlacedEquipment(equip_key="Prise", x=50, y=12, confidence=0.8,
                         uncertain=True, reason="lit absent")
    assert pe.uncertain is True
    assert pe.reason == "lit absent"
