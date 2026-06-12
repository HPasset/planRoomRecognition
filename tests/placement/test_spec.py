from src.planrec.placement.spec import BEDROOM_SPEC, SPEC_BY_ROOM_TYPE


def test_bedroom_spec_has_six_rules_in_order():
    keys = [r.equip_key for r in BEDROOM_SPEC]
    assert keys == ["Prise", "Prise", "RJ45", "Prise", "Switch", "LightPoint"]


def test_each_rule_has_unique_id():
    ids = [r.rule_id for r in BEDROOM_SPEC]
    assert len(ids) == len(set(ids))


def test_rj45_anchors_to_first_socket():
    rj45 = next(r for r in BEDROOM_SPEC if r.equip_key == "RJ45")
    assert rj45.anchor.kind == "adjacent"
    assert rj45.anchor.ref == "prise_1"


def test_bedroom_registered_for_bedroom_room_type():
    assert SPEC_BY_ROOM_TYPE["BedRoom"] is BEDROOM_SPEC
