from src.planrec.placement.contracts import Detection, RoomContext
from src.planrec.placement.resolver import place_room

# Chambre carrée 200x200. Lit poussé contre le mur du HAUT (y~0), occupant
# x de 40 à 160. Porte sur le mur du BAS (y~200), centrée x=150.
POLY = [(0, 0), (200, 0), (200, 200), (0, 200)]
BED = Detection(cls="Bed", bbox=(40, 2, 160, 90), confidence=0.95)
DOOR = Detection(cls="door", bbox=(135, 195, 165, 200), confidence=0.9)
COUNTS = {"Prise": 3, "RJ45": 1, "Switch": 1, "LightPoint": 1}


def _by_key(placed):
    out = {}
    for p in placed:
        out.setdefault(p.equip_key, []).append(p)
    return out


def test_full_bedroom_layout():
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[BED], openings=[DOOR])
    placed = place_room(ctx, COUNTS)
    g = _by_key(placed)
    assert len(g["Prise"]) == 3
    assert len(g["RJ45"]) == 1
    assert len(g["Switch"]) == 1
    assert len(g["LightPoint"]) == 1

    # 2 prises contre le mur du haut, de part et d'autre du lit (x 40..160)
    head_sockets = sorted([p for p in g["Prise"] if p.y < 60], key=lambda p: p.x)
    assert len(head_sockets) == 2
    assert head_sockets[0].x < 60          # côté gauche du lit
    assert head_sockets[1].x > 140         # côté droit du lit
    for s in head_sockets:
        assert s.y <= 25                   # plaquées au mur du haut (inset)

    # 3e prise sur le mur d'en face (bas), en triangle (x ~ centre des 2)
    far = [p for p in g["Prise"] if p.y > 140]
    assert len(far) == 1
    assert far[0].y >= 175
    assert abs(far[0].x - 100) <= 25

    # RJ45 accolée à une prise tête-de-lit, mais côté EXTÉRIEUR du lit
    # (hors de l'emprise x du lit 40..160, pas sur le matelas).
    rj = g["RJ45"][0]
    dists = [((rj.x - s.x) ** 2 + (rj.y - s.y) ** 2) ** 0.5 for s in head_sockets]
    assert min(dists) <= 30
    assert rj.x < 40 or rj.x > 160

    # interrupteur côté porte (bas, vers x=150)
    sw = g["Switch"][0]
    assert sw.y >= 175
    assert sw.x > 110

    # point lumineux central
    light = g["LightPoint"][0]
    assert abs(light.x - 100) <= 20 and abs(light.y - 100) <= 20

    # le point lumineux, les prises et la RJ45 ne sont pas incertains ;
    # l'interrupteur l'est toujours (sens d'ouverture porte inconnu).
    for p in placed:
        if p.equip_key == "Switch":
            assert p.uncertain is True
        else:
            assert p.uncertain is False


def test_missing_bed_falls_back_and_marks_uncertain():
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[], openings=[DOOR])
    placed = place_room(ctx, COUNTS)
    sockets = [p for p in placed if p.equip_key == "Prise"]
    assert len(sockets) == 3
    # sans lit, les prises tête-de-lit sont incertaines
    assert any(p.uncertain for p in sockets)


def test_missing_door_marks_switch_uncertain():
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[BED], openings=[])
    placed = place_room(ctx, COUNTS)
    sw = next(p for p in placed if p.equip_key == "Switch")
    assert sw.uncertain is True


def test_extra_socket_beyond_spec_is_placed_on_free_wall():
    counts = {"Prise": 4, "RJ45": 1, "Switch": 1, "LightPoint": 1}
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[BED], openings=[DOOR])
    placed = place_room(ctx, counts)
    assert len([p for p in placed if p.equip_key == "Prise"]) == 4


def test_degenerate_polygon_returns_empty():
    # polygone vide et polygone d'aire nulle → pas de placement inventé
    from src.planrec.placement.contracts import RoomContext
    assert place_room(RoomContext(room_type="BedRoom", polygon=[]), COUNTS) == []
    flat = RoomContext(room_type="BedRoom", polygon=[(5, 5), (5, 5), (5, 5), (5, 5)])
    assert place_room(flat, COUNTS) == []


def test_snap_path_pulls_sockets_to_detected_walls():
    # wall_lines non vide (chemin production) : les prises tête-de-lit sont
    # recalées proprement à INSET du mur du haut détecté à y=0.
    walls = [(0, 0, 200, 0), (200, 0, 200, 200), (200, 200, 0, 200), (0, 200, 0, 0)]
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[BED], openings=[DOOR], wall_lines=walls)
    placed = place_room(ctx, COUNTS)
    head = [p for p in placed if p.equip_key == "Prise" and p.y < 60]
    assert len(head) == 2
    for s in head:
        assert s.y <= 25     # collées au mur du haut (inset ~15px)
