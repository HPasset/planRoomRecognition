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
