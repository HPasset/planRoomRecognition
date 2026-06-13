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

    # 2 prises contre le mur du haut, de part et d'autre du lit (x 40..160),
    # flanquant le lit JUSTE AU-DELÀ de ses extrémités (pas sur les coins).
    head_sockets = sorted([p for p in g["Prise"] if p.y < 60], key=lambda p: p.x)
    assert len(head_sockets) == 2
    assert head_sockets[0].x < 40          # au-delà du bord gauche du lit (x=40)
    assert head_sockets[1].x > 160         # au-delà du bord droit du lit (x=160)
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


def test_corner_single_bed_sockets_on_free_side_not_in_blocked_corner():
    # Lit UNE PLACE portrait dans le coin haut-droit : têtière contre le mur du
    # HAUT, grand côté DROIT plaqué au mur de DROITE (inaccessible). Les 2 prises
    # de chevet doivent longer le côté LIBRE (mur de gauche) — une à la tête,
    # une au pied — et AUCUNE ne doit tomber dans le coin bloqué (haut-droite).
    bed_corner = Detection(cls="Bed", bbox=(130, 2, 190, 150), confidence=0.95)
    door = Detection(cls="door", bbox=(20, 195, 50, 200), confidence=0.9)
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[bed_corner], openings=[door])
    placed = place_room(ctx, COUNTS)
    g = _by_key(placed)
    prises = g["Prise"]
    assert len(prises) == 3

    # 2 prises de chevet sur le mur côté LIBRE (gauche, x petit), étalées tête↔pied
    left = sorted([p for p in prises if p.x <= 30], key=lambda p: p.y)
    assert len(left) == 2
    assert left[0].y < 100         # une à la tête (haut)
    assert left[1].y > 90          # une au pied (bas)

    # AUCUNE prise dans le coin bloqué (haut-droite, contre le mur de droite)
    assert all(not (p.x > 150 and p.y < 60) for p in prises)

    # 3e prise sur le mur d'en face (bas), à l'aplomb du lit (pas collée aux 2 autres)
    far = [p for p in prises if p.y >= 175]
    assert len(far) == 1
    assert far[0].x > 60           # étalée vers le lit, pas dans le coin gauche

    # RJ45 accolée à la prise de chevet TÊTE (haut-gauche)
    rj = g["RJ45"][0]
    assert min(((rj.x - s.x) ** 2 + (rj.y - s.y) ** 2) ** 0.5 for s in left) <= 35


def test_missing_bed_declines_so_caller_falls_back_to_perimeter():
    # Sans lit, le moteur chambre décline (retourne []) : l'appelant retombe
    # sur le placement périmétrique propre de la pièce plutôt qu'une
    # dégradation entassée.
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[], openings=[DOOR])
    assert place_room(ctx, COUNTS) == []


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
