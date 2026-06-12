import math
from src.planrec.placement.geometry import (
    Edge, room_edges, polygon_centroid, point_on_edge,
)

# Carré 100x100, sens horaire depuis coin haut-gauche
SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]


def test_room_edges_returns_one_edge_per_side():
    edges = room_edges(SQUARE)
    assert len(edges) == 4
    # 1re arête = côté haut (horizontale)
    top = edges[0]
    assert top.a == (0, 0) and top.b == (100, 0)
    assert top.orientation == "H"


def test_vertical_edge_orientation():
    edges = room_edges(SQUARE)
    right = edges[1]  # (100,0)->(100,100)
    assert right.orientation == "V"


def test_polygon_centroid_of_square_is_center():
    assert polygon_centroid(SQUARE) == (50, 50)


def test_point_on_edge_midpoint_inset_inward():
    edges = room_edges(SQUARE)
    top = edges[0]               # côté haut, y=0
    c = polygon_centroid(SQUARE)  # (50,50), donc "intérieur" = vers le bas
    p = point_on_edge(top, t=0.5, inset=10, centroid=c)
    assert p[0] == 50            # milieu en x
    assert p[1] == 10            # décalé de 10px vers l'intérieur (bas)


def test_edge_length_and_point_at_extremes():
    e = Edge(a=(0, 0), b=(100, 0))
    assert math.isclose(e.length, 100.0)
    assert e.point_at(0.0) == (0.0, 0.0)
    assert e.point_at(1.0) == (100.0, 0.0)
