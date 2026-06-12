from src.planrec.placement.geometry import room_edges, nearest_edge, opposite_edge

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
