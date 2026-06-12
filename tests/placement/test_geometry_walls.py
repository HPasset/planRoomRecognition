from src.planrec.placement.geometry import (
    room_edges, nearest_edge, opposite_edge, bed_head_wall,
)

SQUARE = [(0, 0), (100, 0), (100, 100), (0, 100)]
EDGES = room_edges(SQUARE)
# EDGES[0]=haut(y=0), [1]=droite(x=100), [2]=bas(y=100), [3]=gauche(x=0)


def test_nearest_edge_picks_wall_a_bbox_is_pushed_against():
    # bbox plaqué en haut (y proche de 0)
    bed = (20, 2, 80, 40)
    e = nearest_edge(bed, EDGES)
    assert e is EDGES[0]  # côté haut


def test_nearest_edge_left_wall():
    bed = (2, 30, 40, 90)
    e = nearest_edge(bed, EDGES)
    assert e is EDGES[3]  # côté gauche


def test_opposite_edge_of_top_is_bottom():
    opp = opposite_edge(EDGES[0], EDGES)
    assert opp is EDGES[2]  # bas en face du haut


def test_opposite_edge_of_left_is_right():
    opp = opposite_edge(EDGES[3], EDGES)
    assert opp is EDGES[1]


def test_bed_head_wall_corner_portrait_bed_picks_horizontal_wall():
    # pièce 200x200, lit PORTRAIT (h>w) dans le coin haut-droit, plaqué
    # contre le mur du HAUT (têtière) ET le mur de DROITE (grand côté).
    square = [(0, 0), (200, 0), (200, 200), (0, 200)]
    edges = room_edges(square)  # [0]=haut(H), [1]=droite(V), [2]=bas(H), [3]=gauche(V)
    bed = (130, 2, 190, 120)    # w=60, h=118 → portrait → têtière sur mur H
    assert bed_head_wall(bed, edges) is edges[0]   # mur du haut


def test_bed_head_wall_only_one_flush_wall():
    square = [(0, 0), (200, 0), (200, 200), (0, 200)]
    edges = room_edges(square)
    bed = (40, 2, 160, 90)      # paysage, plaqué seulement en haut (intérieur en x)
    assert bed_head_wall(bed, edges) is edges[0]   # mur du haut (seul plaqué)
