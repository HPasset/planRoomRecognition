from src.planrec.placement.geometry import (
    room_edges, polygon_centroid, project_extents, triangle_apex, beside_door,
)

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]
EDGES = room_edges(SQUARE)
C = polygon_centroid(SQUARE)
TOP = EDGES[0]      # y=0, a=(0,0) b=(100,0)


def test_project_extents_of_bed_on_top_wall():
    # lit occupant x de 20 à 60 contre le mur du haut
    bed = (20, 2, 60, 45)
    t_min, t_max = project_extents(bed, TOP)
    # arête de longueur 100, projection x=20..60 → t=0.2..0.6
    assert abs(t_min - 0.2) < 0.02
    assert abs(t_max - 0.6) < 0.02


def test_triangle_apex_is_symmetric_on_opposite_wall():
    bottom = EDGES[2]   # y=100, a=(100,100) b=(0,100)
    p1 = (25, 10)       # prise gauche
    p2 = (65, 10)       # prise droite
    apex = triangle_apex(p1, p2, bottom, inset=10, centroid=C)
    # apex ~ au milieu en x des deux prises (45), sur le mur du bas (y~90)
    assert abs(apex[0] - 45) <= 3
    assert abs(apex[1] - 90) <= 3


def test_beside_door_offsets_along_wall_inside_span():
    # porte centrée en x=80 sur le mur du bas, largeur 20
    bottom = EDGES[2]
    door = (70, 95, 90, 100)
    p = beside_door(door, bottom, inset=10, centroid=C, margin=8)
    # à côté de la porte (pas dessus), à l'intérieur (y < 100)
    assert p[1] < 100
    assert abs(p[0] - 80) >= 8      # décalé du centre de la porte
    assert 0 <= p[0] <= 100
