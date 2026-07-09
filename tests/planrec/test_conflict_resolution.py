from types import SimpleNamespace

from src.planrec.conflict_resolution import (
    conflict_choices,
    find_pastille_in_room,
    reindex_labels,
    unresolved_conflicts,
)
from src.segmentation.classes import CLASS_ID, CLASS_NAMES


def _room(rid, type_name, polygon):
    return SimpleNamespace(
        id=rid,
        type=type_name,
        type_id=CLASS_ID[type_name],
        polygon=polygon,
    )


def _record(rid, type_name, ocr_class_name, conflict, polygon=None, ocr_text="bureau"):
    poly = polygon or [[0, 0], [10, 0], [10, 10], [0, 10]]
    return {
        "room": _room(rid, type_name, poly),
        "ocr_hits": [{"text": ocr_text, "room_type": "bureau",
                      "confidence": 0.9, "bbox": [[1, 1], [2, 1], [2, 2], [1, 2]]}],
        "ocr_class_id": CLASS_ID[ocr_class_name],
        "conflict": conflict,
    }


def test_unresolved_conflicts_keeps_only_unresolved_conflicts():
    records = [
        _record("room_001", "Kitchen", "BedRoom", conflict=True),
        _record("room_002", "Bath", "Bath", conflict=False),      # pas de conflit
        _record("room_003", "Garage", "BedRoom", conflict=True),  # résolu
    ]
    resolutions = {"room_003": "Chambre"}
    out = unresolved_conflicts(records, resolutions)
    assert [r["room"].id for r in out] == ["room_001"]


def test_unresolved_conflicts_empty_when_all_resolved():
    records = [_record("room_001", "Kitchen", "BedRoom", conflict=True)]
    assert unresolved_conflicts(records, {"room_001": "Cuisine"}) == []


def test_conflict_choices_extracts_class_names_and_text():
    rec = _record("room_007", "Kitchen", "BedRoom", conflict=True, ocr_text="bureau")
    c = conflict_choices(rec)
    assert c["seg_room_id"] == "room_007"
    assert c["ocr_text"] == "bureau"
    assert c["seg_class_name"] == "Kitchen"
    assert c["seg_class_id"] == CLASS_ID["Kitchen"]
    assert c["ocr_class_name"] == "BedRoom"
    assert c["ocr_class_id"] == CLASS_ID["BedRoom"]


def test_find_pastille_inside_polygon():
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]
    pastilles = [
        {"id": "ocr_001", "x": 50, "y": 50},   # dedans
        {"id": "ocr_002", "x": 500, "y": 500}, # dehors
    ]
    assert find_pastille_in_room(pastilles, poly) == "ocr_001"


def test_find_pastille_outside_returns_none():
    poly = [[0, 0], [10, 0], [10, 10], [0, 10]]
    pastilles = [{"id": "ocr_002", "x": 500, "y": 500}]
    assert find_pastille_in_room(pastilles, poly) is None


def test_find_pastille_multiple_returns_closest_to_centroid():
    poly = [[0, 0], [100, 0], [100, 100], [0, 100]]  # centroïde ~ (50, 50)
    pastilles = [
        {"id": "far", "x": 90, "y": 90},
        {"id": "near", "x": 48, "y": 52},
    ]
    assert find_pastille_in_room(pastilles, poly) == "near"


def test_find_pastille_empty_list_returns_none():
    assert find_pastille_in_room([], [[0, 0], [10, 0], [10, 10], [0, 10]]) is None


def test_reindex_labels_single_instance_bare():
    pastilles = [{"id": "a", "type": "Chambre", "label": "Chambre 3"}]
    reindex_labels(pastilles, {"Chambre"})
    assert pastilles[0]["label"] == "Chambre"


def test_reindex_labels_multiple_numbered_in_order():
    pastilles = [
        {"id": "a", "type": "Chambre", "label": "Chambre"},
        {"id": "b", "type": "Chambre", "label": "Chambre 2"},
    ]
    reindex_labels(pastilles, {"Chambre"})
    assert [p["label"] for p in pastilles] == ["Chambre 1", "Chambre 2"]


def test_reindex_labels_only_touches_given_types():
    pastilles = [
        {"id": "a", "type": "Cuisine", "label": "KEEP"},
        {"id": "b", "type": "Chambre", "label": "Chambre"},
    ]
    reindex_labels(pastilles, {"Chambre"})
    assert pastilles[0]["label"] == "KEEP"
    assert pastilles[1]["label"] == "Chambre"
