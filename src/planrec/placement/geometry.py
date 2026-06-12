"""Primitives géométriques pures pour le placement. Coordonnées en px.

Convention `t` : paramètre 0..1 le long d'une arête (0 = a, 1 = b).
Convention « intérieur » : vers le barycentre de la pièce.
"""
from __future__ import annotations
import math
from dataclasses import dataclass

Point = tuple[int, int]
FPoint = tuple[float, float]

# Seuil pour classer une arête diagonale vs axis-aligned (px d'écart)
_AXIS_TOL = 8.0


@dataclass(frozen=True)
class Edge:
    a: Point
    b: Point

    @property
    def length(self) -> float:
        return math.hypot(self.b[0] - self.a[0], self.b[1] - self.a[1])

    @property
    def orientation(self) -> str:
        dx = abs(self.b[0] - self.a[0])
        dy = abs(self.b[1] - self.a[1])
        if dy <= _AXIS_TOL and dx > dy:
            return "H"
        if dx <= _AXIS_TOL and dy > dx:
            return "V"
        return "D"

    @property
    def midpoint(self) -> FPoint:
        return ((self.a[0] + self.b[0]) / 2.0, (self.a[1] + self.b[1]) / 2.0)

    def point_at(self, t: float) -> FPoint:
        return (self.a[0] + (self.b[0] - self.a[0]) * t,
                self.a[1] + (self.b[1] - self.a[1]) * t)

    def unit_dir(self) -> FPoint:
        L = self.length or 1.0
        return ((self.b[0] - self.a[0]) / L, (self.b[1] - self.a[1]) / L)

    def inward_normal(self, centroid: Point) -> FPoint:
        """Normale unitaire pointant vers `centroid`."""
        ux, uy = self.unit_dir()
        n1 = (-uy, ux)
        mx, my = self.midpoint
        to_c = (centroid[0] - mx, centroid[1] - my)
        return n1 if (n1[0] * to_c[0] + n1[1] * to_c[1]) >= 0 else (-n1[0], -n1[1])


def room_edges(polygon: list[Point]) -> list[Edge]:
    """Côtés du polygone, dans l'ordre des sommets (boucle fermée)."""
    n = len(polygon)
    return [Edge(a=polygon[i], b=polygon[(i + 1) % n]) for i in range(n)]


def polygon_centroid(polygon: list[Point]) -> Point:
    """Barycentre par aire signée (robuste pour polygones convexes/concaves).

    Repli sur la moyenne des sommets si l'aire est ~nulle (polygone dégénéré).
    """
    n = len(polygon)
    a2 = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a2) < 1e-6:
        mx = sum(p[0] for p in polygon) / n
        my = sum(p[1] for p in polygon) / n
        return (int(round(mx)), int(round(my)))
    area = a2 / 2.0
    return (int(round(cx / (6.0 * area))), int(round(cy / (6.0 * area))))


def point_on_edge(edge: Edge, t: float, inset: int, centroid: Point) -> Point:
    """Point à la fraction `t` de l'arête, décalé `inset` px vers l'intérieur."""
    px, py = edge.point_at(max(0.0, min(1.0, t)))
    nx, ny = edge.inward_normal(centroid)
    return (int(round(px + nx * inset)), int(round(py + ny * inset)))


def _point_seg_dist(p: FPoint, a: Point, b: Point) -> float:
    """Distance d'un point au segment [a,b]."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    projx, projy = ax + t * dx, ay + t * dy
    return math.hypot(p[0] - projx, p[1] - projy)


def _bbox_corners(bbox: tuple[int, int, int, int]) -> list[Point]:
    x1, y1, x2, y2 = bbox
    return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]


def nearest_edge(bbox: tuple[int, int, int, int], edges: list[Edge]) -> Edge:
    """Arête contre laquelle la bbox est plaquée = la plus proche.

    Distance bbox↔arête = min sur les 4 coins de la bbox de la distance
    au segment de l'arête. Sert pour `wall_behind` (lit) et `edge_of` (porte).
    """
    best = edges[0]
    best_d = float("inf")
    corners = _bbox_corners(bbox)
    for e in edges:
        d = min(_point_seg_dist(c, e.a, e.b) for c in corners)
        if d < best_d:
            best_d = d
            best = e
    return best


def opposite_edge(edge: Edge, edges: list[Edge]) -> Edge:
    """Arête ~parallèle la plus éloignée de `edge` (le « mur d'en face »)."""
    ux, uy = edge.unit_dir()
    mx, my = edge.midpoint
    best = None
    best_score = -1.0
    for e in edges:
        if e is edge:
            continue
        ex, ey = e.unit_dir()
        parallelism = abs(ux * ex + uy * ey)   # 1 = parallèle, 0 = perpendiculaire
        dist = math.hypot(e.midpoint[0] - mx, e.midpoint[1] - my)
        score = parallelism * dist
        if score > best_score:
            best_score = score
            best = e
    return best if best is not None else edge


# Alias sémantiques (même implémentation, intentions distinctes)
wall_behind = nearest_edge   # mur tête-de-lit
edge_of = nearest_edge       # mur portant la porte


def bed_head_wall(bbox: tuple[int, int, int, int], edges: list[Edge],
                  flush_tol: float = 30.0) -> Edge:
    """Mur tête-de-lit = mur derrière la tête de lit (côté court du lit).

    Le côté court (têtière) est perpendiculaire au grand axe du lit : pour un
    lit « portrait » (hauteur >= largeur) la têtière est contre un mur
    HORIZONTAL ; pour un lit « paysage » contre un mur VERTICAL. On choisit,
    parmi les murs contre lesquels le lit est plaqué (`flush_tol`) et de la
    bonne orientation, le plus proche. Replis : mur plaqué le plus proche,
    sinon mur le plus proche tout court. Résout l'ambiguïté du lit en coin.
    """
    x1, y1, x2, y2 = bbox
    w, h = x2 - x1, y2 - y1
    head_orient = "H" if h >= w else "V"

    def gap(e: Edge) -> float:
        return min(_point_seg_dist(c, e.a, e.b) for c in _bbox_corners(bbox))

    flush = [e for e in edges if gap(e) <= flush_tol]
    oriented = [e for e in flush if e.orientation == head_orient]
    pool = oriented or flush or list(edges)
    return min(pool, key=gap)


def _project_t(point: Point, edge: Edge) -> float:
    """Paramètre t (non clampé) de la projection de `point` sur l'axe de l'arête."""
    ax, ay = edge.a
    dx = edge.b[0] - ax
    dy = edge.b[1] - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return 0.0
    return ((point[0] - ax) * dx + (point[1] - ay) * dy) / L2


def project_extents(bbox: tuple[int, int, int, int], edge: Edge) -> tuple[float, float]:
    """Empreinte d'une bbox projetée sur l'arête → (t_min, t_max) clampés [0,1]."""
    ts = [_project_t(c, edge) for c in _bbox_corners(bbox)]
    lo = max(0.0, min(ts))
    hi = min(1.0, max(ts))
    return (lo, hi)


def triangle_apex(p1: Point, p2: Point, edge: Edge, inset: int, centroid: Point) -> Point:
    """Point sur `edge` formant un triangle équilibré avec p1,p2.

    = projection du milieu de [p1,p2] sur l'arête, décalée `inset` vers l'intérieur.
    """
    mid = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    t = max(0.0, min(1.0, _project_t((int(mid[0]), int(mid[1])), edge)))
    return point_on_edge(edge, t, inset, centroid)


def beside_door(door_bbox: tuple[int, int, int, int], edge: Edge,
                inset: int, centroid: Point, margin: int = 8) -> Point:
    """Point intérieur à côté de l'ouverture, côté dégagé (vers le centre du mur)."""
    dcx = (door_bbox[0] + door_bbox[2]) / 2.0
    dcy = (door_bbox[1] + door_bbox[3]) / 2.0
    t_door = _project_t((int(dcx), int(dcy)), edge)
    ts = [_project_t(c, edge) for c in _bbox_corners(door_bbox)]
    half = (max(ts) - min(ts)) / 2.0
    L = edge.length or 1.0
    delta = half + margin / L
    # côté dégagé = vers le centre du mur (loin du coin le plus proche)
    side_sign = 1.0 if t_door < 0.5 else -1.0
    t_side = max(0.0, min(1.0, t_door + side_sign * delta))
    return point_on_edge(edge, t_side, inset, centroid)


# ---------------------------------------------------------------------------
# Couche C — Raffinement : snap mur + anti-collision
# ---------------------------------------------------------------------------

def _nearest_point_on_segment(p: Point, seg: tuple[int, int, int, int]) -> FPoint:
    ax, ay, bx, by = seg
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return (float(ax), float(ay))
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return (ax + t * dx, ay + t * dy)


def snap_to_wall(p: Point, wall_lines: list[tuple[int, int, int, int]],
                 max_dist: float, inset: int, centroid: Point) -> tuple[Point, float]:
    """Recale `p` à `inset` px à l'intérieur du mur détecté le plus proche.

    Si aucun mur dans `max_dist`, retourne `p` inchangé (moved=0).
    """
    best_q = None
    best_d = max_dist
    for seg in wall_lines:
        q = _nearest_point_on_segment(p, seg)
        d = math.hypot(p[0] - q[0], p[1] - q[1])
        if d < best_d:
            best_d = d
            best_q = q
    if best_q is None:
        return (p, 0.0)
    # direction vers l'intérieur depuis le mur
    vx, vy = centroid[0] - best_q[0], centroid[1] - best_q[1]
    vlen = math.hypot(vx, vy) or 1.0
    out = (int(round(best_q[0] + vx / vlen * inset)),
           int(round(best_q[1] + vy / vlen * inset)))
    return (out, math.hypot(p[0] - out[0], p[1] - out[1]))


def resolve_collisions(points: list[Point], min_gap: int,
                       iterations: int = 8) -> list[Point]:
    """Écarte itérativement les points plus proches que `min_gap`."""
    pts = [list(map(float, p)) for p in points]
    n = len(pts)
    for _ in range(iterations):
        moved = False
        for i in range(n):
            for j in range(i + 1, n):
                dx = pts[j][0] - pts[i][0]
                dy = pts[j][1] - pts[i][1]
                dist = math.hypot(dx, dy)
                if dist < min_gap:
                    moved = True
                    if dist < 1e-6:
                        dx, dy, dist = 1.0, 0.0, 1.0
                    push = (min_gap - dist) / 2.0
                    ux, uy = dx / dist, dy / dist
                    pts[i][0] -= ux * push
                    pts[i][1] -= uy * push
                    pts[j][0] += ux * push
                    pts[j][1] += uy * push
        if not moved:
            break
    return [(int(round(x)), int(round(y))) for x, y in pts]
