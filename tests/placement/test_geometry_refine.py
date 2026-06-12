from src.planrec.placement.geometry import snap_to_wall, resolve_collisions

CENTROID = (50, 50)


def test_snap_pulls_point_onto_nearby_wall_keeping_inset():
    # mur horizontal détecté à y=0 ; point un peu trop bas (y=18)
    walls = [(0, 0, 100, 0)]
    p = (50, 18)
    out, moved = snap_to_wall(p, walls, max_dist=25, inset=10, centroid=CENTROID)
    assert out[1] == 10          # re-inset à 10px du mur, vers l'intérieur
    assert moved > 0


def test_snap_noop_when_no_wall_within_max_dist():
    walls = [(0, 0, 100, 0)]
    p = (50, 60)
    out, moved = snap_to_wall(p, walls, max_dist=25, inset=10, centroid=CENTROID)
    assert out == (50, 60)
    assert moved == 0.0


def test_snap_noop_when_no_walls():
    out, moved = snap_to_wall((30, 30), [], max_dist=25, inset=10, centroid=CENTROID)
    assert out == (30, 30)
    assert moved == 0.0


def test_resolve_collisions_pushes_apart_overlapping_points():
    pts = [(50, 50), (52, 50)]   # quasi confondus
    out = resolve_collisions(pts, min_gap=20)
    dx = out[0][0] - out[1][0]
    dy = out[0][1] - out[1][1]
    assert (dx * dx + dy * dy) ** 0.5 >= 19.0   # ~écartés à min_gap


def test_resolve_collisions_leaves_distant_points_untouched():
    pts = [(0, 0), (100, 0)]
    out = resolve_collisions(pts, min_gap=20)
    assert out == [(0, 0), (100, 0)]
