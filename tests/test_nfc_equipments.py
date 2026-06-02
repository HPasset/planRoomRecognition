"""Tests pour le module nfc_equipments (logique métier équipements électriques)."""
from __future__ import annotations
import math
import re
from collections import Counter

from src.planrec.nfc_equipments import (
    EQUIP_TYPES,
    NFC_TO_EQUIP_TYPE,
    EquipmentInstance,
    generate_equipment_id,
    generate_equipments_from_devis_global,
    reconcile_equipments_for_line,
    smart_placement_fallback_cluster,
    smart_placement_with_polygon,
)
from src.planrec.nfc_rules import EquipmentType, compute_devis_global


def test_equip_types_has_5_entries():
    """Les 5 types NF C 15-100 doivent être présents avec label/color/svg_id."""
    expected_keys = {"Prise", "RJ45", "LightPoint", "Switch", "SpecialFeed"}
    assert set(EQUIP_TYPES.keys()) == expected_keys
    for key, info in EQUIP_TYPES.items():
        assert "label" in info
        assert "color" in info and info["color"].startswith("rgb(")
        assert "svg_id" in info


def test_nfc_to_equip_type_covers_all_enums():
    """Le mapping doit couvrir les 5 valeurs de EquipmentType."""
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SOCKET] == "Prise"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.RJ45] == "RJ45"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.LIGHT_POINT] == "LightPoint"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SWITCH] == "Switch"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SPECIAL_FEED] == "SpecialFeed"
    # Tous les enums sont mappés
    assert len(NFC_TO_EQUIP_TYPE) == 5


def test_generate_equipment_id_format():
    """ID = 'eq_' + 8 hex chars."""
    eid = generate_equipment_id()
    assert re.fullmatch(r"eq_[0-9a-f]{8}", eid)


def test_generate_equipment_id_unique():
    """100 appels successifs → 100 IDs distincts (proba collision négligeable)."""
    ids = {generate_equipment_id() for _ in range(100)}
    assert len(ids) == 100


def test_generate_equipments_from_devis_simple():
    """1 WC seul → 2 instances (1 LightPoint + 1 Switch selon NFC sans handicap)."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Bath", "surface_m2": None,
         "ocr_hint": "WC"},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    # WC NFC : 1 point lumineux + 1 interrupteur (pas de prise sans handicap)
    types = sorted(i["type"] for i in instances)
    assert types == ["LightPoint", "Switch"]
    # Chaque instance a un id unique, room "WC", x=y=0 par défaut
    assert len({i["id"] for i in instances}) == 2
    assert all(i["room"] == "WC" for i in instances)
    assert all(i["x"] == 0 and i["y"] == 0 for i in instances)
    assert all(i["color"] == EQUIP_TYPES[i["type"]]["color"] for i in instances)


def test_generate_equipments_kitchen_qty_explodes():
    """Cuisine NFC : qté élevée (6 prises + 3 alim spé + ...) → autant d'instances."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Kitchen", "surface_m2": None,
         "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    type_counts: dict[str, int] = {}
    for inst in instances:
        type_counts[inst["type"]] = type_counts.get(inst["type"], 0) + 1
    # Au moins 6 prises (NFC cuisine) + 3 alim spé + 1 point lum + 1 inter
    assert type_counts.get("Prise", 0) >= 6
    assert type_counts.get("SpecialFeed", 0) >= 3
    assert type_counts.get("LightPoint", 0) >= 1
    assert type_counts.get("Switch", 0) >= 1


def test_generate_equipments_room_label_with_index():
    """Plusieurs chambres → label = 'Chambre 1', 'Chambre 2'…"""
    rooms_input = [
        {"id": "r1", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
        {"id": "r2", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    room_counts = Counter(inst["room"] for inst in instances)
    assert room_counts["Chambre 1"] > 0
    assert room_counts["Chambre 2"] > 0
    assert room_counts["Chambre 1"] == room_counts["Chambre 2"]


def test_fallback_cluster_inside_image_bbox():
    """Les positions générées sont toutes dans la bbox image."""
    image_w, image_h = 1000, 800
    room_center = (500, 400)
    n_equipments = 10
    positions = smart_placement_fallback_cluster(
        room_center=room_center,
        n_equipments=n_equipments,
        image_size=(image_w, image_h),
        random_seed=42,
    )
    assert len(positions) == n_equipments
    for x, y in positions:
        assert 0 <= x <= image_w
        assert 0 <= y <= image_h


def test_fallback_cluster_is_deterministic_with_seed():
    """Même seed → mêmes positions (reproductibilité tests)."""
    args = {"room_center": (500, 400), "n_equipments": 5,
            "image_size": (1000, 800), "random_seed": 123}
    p1 = smart_placement_fallback_cluster(**args)
    p2 = smart_placement_fallback_cluster(**args)
    assert p1 == p2


def test_fallback_cluster_close_to_room_center():
    """Les positions sont dans un rayon raisonnable autour du centre."""
    room_center = (500, 400)
    positions = smart_placement_fallback_cluster(
        room_center=room_center,
        n_equipments=5,
        image_size=(1000, 800),
        random_seed=42,
    )
    for x, y in positions:
        dist = math.hypot(x - room_center[0], y - room_center[1])
        # Grille 3x3 spacing 30px + drift 5px → max ~50px du centre
        assert dist < 100


# Polygone rectangulaire simple pour tests (cuisine 100×100 à partir de (200, 200))
SIMPLE_RECT = [(200, 200), (300, 200), (300, 300), (200, 300)]


def test_light_point_at_centroid():
    """Le point lumineux est placé au barycentre du polygone."""
    pos = smart_placement_with_polygon(
        equip_type="LightPoint",
        polygon=SIMPLE_RECT,
        room_pastille_pos=(250, 210),
        instance_index=0,
        n_of_type=1,
    )
    assert pos == (250, 250)


def test_sockets_distributed_on_perimeter():
    """Les prises sont placées sur le périmètre du polygone."""
    n = 4
    positions = [
        smart_placement_with_polygon(
            equip_type="Prise",
            polygon=SIMPLE_RECT,
            room_pastille_pos=(250, 210),
            instance_index=i,
            n_of_type=n,
        )
        for i in range(n)
    ]
    for x, y in positions:
        assert 200 - 20 <= x <= 300 + 20
        assert 200 - 20 <= y <= 300 + 20
    assert len(set(positions)) == n


def test_switch_near_pastille():
    """L'interrupteur est placé sur le périmètre, proche du centre pastille."""
    pos = smart_placement_with_polygon(
        equip_type="Switch",
        polygon=SIMPLE_RECT,
        room_pastille_pos=(250, 195),
        instance_index=0,
        n_of_type=1,
    )
    assert pos[1] < 250


def _make_inst(id_suffix: str, type_: str, room: str) -> EquipmentInstance:
    return {
        "id": f"eq_{id_suffix}",
        "type": type_, "room": room, "x": 0, "y": 0,
        "color": EQUIP_TYPES[type_]["color"],
    }


def test_reconcile_add_when_qty_increases():
    """Qté 2 → 5 : 3 nouvelles instances ajoutées avec smart_placer."""
    current = [
        _make_inst("aaa", "Prise", "Cuisine"),
        _make_inst("bbb", "Prise", "Cuisine"),
    ]
    placer_calls = []
    def fake_placer(typ, room, idx, n):
        placer_calls.append((typ, room, idx, n))
        return (idx * 10, idx * 10)

    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=5,
        smart_placer=fake_placer,
    )
    line_instances = [i for i in new_state if i["room"] == "Cuisine" and i["type"] == "Prise"]
    assert len(line_instances) == 5
    assert len(line_ids) == 5
    assert len(placer_calls) == 3


def test_reconcile_remove_when_qty_decreases():
    """Qté 5 → 2 : 3 instances retirées (les dernières)."""
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Cuisine"),
        _make_inst("c", "Prise", "Cuisine"),
        _make_inst("d", "Prise", "Cuisine"),
        _make_inst("e", "Prise", "Cuisine"),
    ]
    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=2,
        smart_placer=lambda *args: (0, 0),
    )
    line_instances = [i for i in new_state if i["room"] == "Cuisine" and i["type"] == "Prise"]
    assert len(line_instances) == 2
    assert {i["id"] for i in line_instances} == {"eq_a", "eq_b"}


def test_reconcile_preserves_other_lines():
    """La reconciliation ne touche pas les autres lignes (autre room ou autre type)."""
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Chambre 1"),
        _make_inst("c", "LightPoint", "Cuisine"),
    ]
    new_state, _ = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=3,
        smart_placer=lambda *args: (0, 0),
    )
    assert any(i["id"] == "eq_b" for i in new_state)
    assert any(i["id"] == "eq_c" for i in new_state)


def test_reconcile_qty_zero_removes_all():
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Cuisine"),
    ]
    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=0,
        smart_placer=lambda *args: (0, 0),
    )
    assert all(not (i["room"] == "Cuisine" and i["type"] == "Prise") for i in new_state)
    assert line_ids == []


def test_equipment_type_has_all_v2_subtypes():
    """Les 6 sous-types spécialisés + 2 chauffage doivent être présents."""
    from src.planrec.nfc_rules import EquipmentType
    assert EquipmentType.OVEN.value == "four"
    assert EquipmentType.COOKTOP.value == "plaque_cuisson"
    assert EquipmentType.DISHWASHER.value == "lave_vaisselle"
    assert EquipmentType.WASHING_MACHINE.value == "lave_linge"
    assert EquipmentType.DRYER.value == "seche_linge"
    assert EquipmentType.BOILER.value == "chaudiere_cumulus"
    assert EquipmentType.CONVECTOR.value == "convecteur"
    assert EquipmentType.TOWEL_WARMER.value == "seche_serviettes"


def test_pricing_covers_all_new_types():
    """DEFAULT_PRICES_HT et EQUIPMENT_LABELS_FR couvrent les 8 nouveaux types."""
    from src.planrec.nfc_rules import EquipmentType
    from src.planrec.nfc_pricing import DEFAULT_PRICES_HT, EQUIPMENT_LABELS_FR

    new_types = [
        EquipmentType.OVEN, EquipmentType.COOKTOP, EquipmentType.DISHWASHER,
        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER, EquipmentType.BOILER,
        EquipmentType.CONVECTOR, EquipmentType.TOWEL_WARMER,
    ]
    for t in new_types:
        assert t in DEFAULT_PRICES_HT, f"prix manquant pour {t.value}"
        assert DEFAULT_PRICES_HT[t] > 0
        assert t in EQUIPMENT_LABELS_FR, f"label manquant pour {t.value}"
        assert len(EQUIPMENT_LABELS_FR[t]) > 0


def test_kitchen_generates_typed_special_feeds():
    """Cuisine génère 1 Four + 1 Plaque + 1 LV (au lieu de 3× SPECIAL_FEED)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("k1", "Kitchen")
    assert devis.items.get(EquipmentType.OVEN) == 1
    assert devis.items.get(EquipmentType.COOKTOP) == 1
    assert devis.items.get(EquipmentType.DISHWASHER) == 1
    # plus de SPECIAL_FEED générique en cuisine
    assert EquipmentType.SPECIAL_FEED not in devis.items


def test_storage_generates_typed_special_feeds():
    """Cellier/Buanderie : LL + SL + Chaudière (au lieu de 3× SPECIAL_FEED)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("s1", "Storage")
    assert devis.items.get(EquipmentType.WASHING_MACHINE) == 1
    assert devis.items.get(EquipmentType.DRYER) == 1
    assert devis.items.get(EquipmentType.BOILER) == 1
    assert EquipmentType.SPECIAL_FEED not in devis.items


def test_bath_generates_towel_warmer_not_special_feed():
    """SdB génère 1 TOWEL_WARMER (sèche-serviettes, chauffage)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("b1", "Bath")
    assert devis.items.get(EquipmentType.TOWEL_WARMER) == 1
    assert EquipmentType.SPECIAL_FEED not in devis.items


def test_heating_enabled_adds_convector_to_living_and_bedroom():
    """Avec heating_enabled=True (défaut), séjour et chambres reçoivent 1 CONVECTOR."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    living = compute_devis_for_room("L1", "LivingRoom", surface_m2=20.0)
    bedroom = compute_devis_for_room("B1", "BedRoom")
    assert living.items.get(EquipmentType.CONVECTOR) == 1
    assert bedroom.items.get(EquipmentType.CONVECTOR) == 1


def test_heating_disabled_no_convector():
    """heating_enabled=False supprime convecteur + sèche-serviettes."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    living = compute_devis_for_room("L1", "LivingRoom", surface_m2=20.0,
                                     heating_enabled=False)
    bath = compute_devis_for_room("B1", "Bath", heating_enabled=False)
    assert EquipmentType.CONVECTOR not in living.items
    assert EquipmentType.TOWEL_WARMER not in bath.items


def test_heating_no_convector_in_secondary_rooms():
    """Convecteur uniquement en pièces principales (séjour, chambres). Pas en
    cuisine/WC/SdB/cellier/entrée."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    for c2 in ("Kitchen", "Bath", "Storage", "Entry"):
        d = compute_devis_for_room("x", c2, heating_enabled=True)
        assert EquipmentType.CONVECTOR not in d.items, (
            f"Convecteur indu pour {c2}"
        )
