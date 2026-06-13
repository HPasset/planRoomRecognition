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


def test_corner_single_bed_L_layout_along_the_two_walls_it_touches():
    # Lit UNE PLACE portrait dans le coin haut-droit : têtière (côté COURT)
    # contre le mur du HAUT, grand côté DROIT (côté LONG) plaqué au mur de
    # DROITE (inaccessible). Placement attendu en L :
    #   - prise chevet TÊTE sur le mur du HAUT, côté LIBRE (gauche du lit) ;
    #   - prise 2 dans la CONTINUITÉ du grand côté : mur de DROITE, au-delà du
    #     PIED (bas) du lit ;
    #   - 3e prise sur le mur LIBRE d'en face (gauche), à l'aplomb du lit.
    # AUCUNE prise ne tombe dans le coin coincé (haut-droite).
    bed_corner = Detection(cls="Bed", bbox=(130, 2, 190, 150), confidence=0.95)
    door = Detection(cls="door", bbox=(20, 195, 50, 200), confidence=0.9)
    ctx = RoomContext(room_type="BedRoom", polygon=POLY,
                      furniture=[bed_corner], openings=[door])
    placed = place_room(ctx, COUNTS)
    g = _by_key(placed)
    prises = g["Prise"]
    assert len(prises) == 3

    # prise chevet TÊTE : mur du haut (y petit), côté LIBRE (à gauche du lit x<130)
    head_socket = [p for p in prises if p.y <= 30]
    assert len(head_socket) == 1
    assert head_socket[0].x < 130

    # prise CONTINUITÉ grand côté : mur de droite (x grand), au-delà du pied (bas)
    long_socket = [p for p in prises if p.x >= 175 and p.y > 150]
    assert len(long_socket) == 1

    # 3e prise : mur LIBRE d'en face (gauche, x petit), à mi-hauteur du lit
    free_socket = [p for p in prises if p.x <= 30 and 40 < p.y < 150]
    assert len(free_socket) == 1

    # AUCUNE prise dans le coin bloqué (haut-droite, tête × côté bloqué)
    assert all(not (p.x > 150 and p.y < 60) for p in prises)

    # RJ45 accolée à la prise de chevet TÊTE, côté libre (gauche)
    rj = g["RJ45"][0]
    hs = head_socket[0]
    assert ((rj.x - hs.x) ** 2 + (rj.y - hs.y) ** 2) ** 0.5 <= 35
    assert rj.x < 130


def test_corner_bed_with_jagged_polygon_corner_uses_corner_branch_not_alcove():
    # Régression Chambre 3 : un coin de polygone dentelé ne doit PAS faire
    # basculer en « alcôve ». Lit paysage dans le coin haut-gauche, têtière
    # (côté court) contre le mur GAUCHE, grand côté HAUT contre le mur du haut.
    # Attendu : branche « lit en coin », rien d'incertain, prise chevet tête
    # sur le mur gauche côté LIBRE (bas, sous le lit), continuité sur le mur du
    # haut au-delà du pied (droite).
    poly = [(190, 0), (20, 1), (10, 5), (3, 140), (190, 140)]
    bed = Detection(cls="Bed", bbox=(7, 3, 120, 54), confidence=0.95)
    door = Detection(cls="door", bbox=(150, 135, 180, 140), confidence=0.9)
    ctx = RoomContext(room_type="BedRoom", polygon=poly,
                      furniture=[bed], openings=[door])
    placed = place_room(ctx, COUNTS)
    g = _by_key(placed)
    prises = g["Prise"]
    assert len(prises) == 3

    # aucune pastille « alcôve » (la branche ratée) ni prise incertaine
    assert not any("alcôve" in p.reason for p in placed)
    assert all(not p.uncertain for p in prises)

    # prise chevet tête : mur GAUCHE (x petit), côté LIBRE = sous le lit (y > 54)
    head_socket = [p for p in prises if p.x <= 30 and p.y > 54]
    assert len(head_socket) == 1

    # prise continuité du grand côté : mur du HAUT (y petit), au-delà du pied (x > 120)
    long_socket = [p for p in prises if p.y <= 30 and p.x > 120]
    assert len(long_socket) == 1

    # RJ45 accolée à la prise de tête (mur gauche), contre le mur (x petit)
    rj = g["RJ45"][0]
    hs = head_socket[0]
    assert ((rj.x - hs.x) ** 2 + (rj.y - hs.y) ** 2) ** 0.5 <= 35
    assert rj.x <= 35


def test_rj45_slides_along_wall_when_head_socket_at_wall_end():
    # Régression Chambre 2 : la prise de tête est flanquée PILE à l'extrémité du
    # mur tête (lit en coin, têtière au mur gauche, grand côté bas bloqué). La
    # RJ45 doit longer le MUR (décalage parallèle au mur tête = vertical ici),
    # pas filer perpendiculairement dans la pièce (continuité du lit).
    poly = [(0, 0), (200, 0), (200, 150), (0, 150)]
    bed = Detection(cls="Bed", bbox=(2, 90, 115, 145), confidence=0.95)   # paysage, coin bas-gauche
    door = Detection(cls="door", bbox=(150, 145, 180, 150), confidence=0.9)
    ctx = RoomContext(room_type="BedRoom", polygon=poly,
                      furniture=[bed], openings=[door])
    placed = place_room(ctx, COUNTS)
    g = _by_key(placed)
    rj = g["RJ45"][0]
    # prise de tête = celle sur le mur gauche (x petit), la plus proche de la RJ45
    head = min((p for p in g["Prise"] if p.x <= 30),
               key=lambda p: (p.x - rj.x) ** 2 + (p.y - rj.y) ** 2)
    dx, dy = abs(rj.x - head.x), abs(rj.y - head.y)
    # mur tête vertical → décalage RJ45 dominé par l'axe VERTICAL (le long du mur)
    assert dy > dx
    # et la RJ45 reste plaquée au mur gauche, pas repoussée dans la pièce
    assert rj.x <= 30


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
