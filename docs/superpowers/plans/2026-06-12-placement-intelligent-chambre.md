# Placement intelligent des équipements (pilote chambre) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Placer les équipements électriques d'une chambre selon la logique métier (prises de part et d'autre du lit, RJ45 accolée, 3ᵉ prise en triangle sur le mur d'en face, interrupteur côté porte, point lumineux central) au lieu du tas actuel autour de la pastille.

**Architecture:** Un moteur d'« ancres » déclaratif et **pur** (`src/planrec/placement/`) transforme des détections (polygone pièce, bbox lit, bbox porte, lignes murs) en positions via des primitives géométriques, puis une couche de raffinement (snap mur + anti-collision). Branché dans Streamlit uniquement pour les chambres ; toutes les autres pièces gardent le placement actuel (zéro régression). Le modèle YOLO portes/fenêtres existant (`runs/train/v3_doors_windows`) est câblé dans l'app.

**Tech Stack:** Python 3.11 (dataclasses, math — pas de torch/Streamlit dans le moteur), pytest, OpenCV (déjà présent, côté app seulement), Ultralytics YOLO (déjà présent), React/TS/Vite (custom component).

**Conventions de test :** `.venv/bin/pytest`, racine injectée par `conftest.py`, imports `from src.planrec...`. Le moteur est pur → tests rapides, hors marker `slow`.

---

## Phase 1 — Moteur pur : contrats + primitives géométriques

### Task 1: Contrats d'entrée/sortie

**Files:**
- Create: `src/planrec/placement/__init__.py`
- Create: `src/planrec/placement/contracts.py`
- Test: `tests/placement/test_contracts.py`

- [ ] **Step 1: Créer le package**

`src/planrec/placement/__init__.py` :

```python
"""Moteur de placement intelligent des équipements électriques.

PUR : aucun import Streamlit/torch/cv2. Testable en pytest seul.
Toutes les coordonnées sont en pixels image originale.
"""
```

- [ ] **Step 2: Écrire le test des contrats**

`tests/placement/test_contracts.py` :

```python
from src.planrec.placement.contracts import Detection, RoomContext, PlacedEquipment


def test_detection_holds_bbox_and_conf():
    d = Detection(cls="Bed", bbox=(10, 20, 110, 220), confidence=0.97)
    assert d.cls == "Bed"
    assert d.bbox == (10, 20, 110, 220)
    assert d.confidence == 0.97


def test_room_context_defaults_to_empty_lists():
    ctx = RoomContext(room_type="BedRoom", polygon=[(0, 0), (100, 0), (100, 100), (0, 100)])
    assert ctx.furniture == []
    assert ctx.openings == []
    assert ctx.wall_lines == []


def test_placed_equipment_carries_uncertainty():
    pe = PlacedEquipment(equip_key="Prise", x=50, y=12, confidence=0.8,
                         uncertain=True, reason="lit absent")
    assert pe.uncertain is True
    assert pe.reason == "lit absent"
```

- [ ] **Step 3: Lancer le test (échoue)**

Run: `.venv/bin/pytest tests/placement/test_contracts.py -q`
Expected: FAIL — `ModuleNotFoundError: src.planrec.placement.contracts`

- [ ] **Step 4: Implémenter les contrats**

`src/planrec/placement/contracts.py` :

```python
"""Dataclasses d'entrée/sortie du moteur de placement. Coordonnées en px."""
from __future__ import annotations
from dataclasses import dataclass, field

BBox = tuple[int, int, int, int]      # (x1, y1, x2, y2)
Point = tuple[int, int]


@dataclass
class Detection:
    """Une détection objet (YOLO) : mobilier ou ouverture."""
    cls: str                # "Bed", "door", "window", "WashBasin"…
    bbox: BBox
    confidence: float


@dataclass
class RoomContext:
    """Tout ce que le moteur a besoin pour placer dans UNE pièce."""
    room_type: str          # ex "BedRoom"
    polygon: list[Point]    # sommets du polygone pièce (segmentation)
    furniture: list[Detection] = field(default_factory=list)   # YOLO brique A
    openings: list[Detection] = field(default_factory=list)    # YOLO doors/windows
    wall_lines: list[tuple[int, int, int, int]] = field(default_factory=list)


@dataclass
class PlacedEquipment:
    """Un équipement positionné par le moteur."""
    equip_key: str          # clé EQUIP_TYPES : "Prise", "RJ45", "Switch"…
    x: int
    y: int
    confidence: float
    uncertain: bool
    reason: str
```

- [ ] **Step 5: Lancer le test (passe) + commit**

Run: `.venv/bin/pytest tests/placement/test_contracts.py -q`
Expected: PASS (3 passed)

```bash
git add src/planrec/placement/__init__.py src/planrec/placement/contracts.py tests/placement/test_contracts.py
git commit -m "feat(placement): contrats d'entrée/sortie du moteur (pur)"
```

---

### Task 2: Modèle d'arête + côtés du polygone + barycentre

**Files:**
- Create: `src/planrec/placement/geometry.py`
- Test: `tests/placement/test_geometry_edges.py`

- [ ] **Step 1: Écrire le test**

`tests/placement/test_geometry_edges.py` :

```python
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_geometry_edges.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implémenter Edge + room_edges + centroïde + point_on_edge**

`src/planrec/placement/geometry.py` :

```python
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
```

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/placement/test_geometry_edges.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/planrec/placement/geometry.py tests/placement/test_geometry_edges.py
git commit -m "feat(placement): Edge, room_edges, centroïde aire, point_on_edge"
```

---

### Task 3: Sélection de murs (nearest_edge / opposite_edge)

**Files:**
- Modify: `src/planrec/placement/geometry.py`
- Test: `tests/placement/test_geometry_walls.py`

- [ ] **Step 1: Écrire le test**

`tests/placement/test_geometry_walls.py` :

```python
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_geometry_walls.py -q`
Expected: FAIL — `ImportError: nearest_edge`

- [ ] **Step 3: Implémenter (ajouter à `geometry.py`)**

```python
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
```

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/placement/test_geometry_walls.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/planrec/placement/geometry.py tests/placement/test_geometry_walls.py
git commit -m "feat(placement): nearest_edge/wall_behind/edge_of + opposite_edge"
```

---

### Task 4: Ancres complexes (extents lit, triangle, à-côté-de-porte)

**Files:**
- Modify: `src/planrec/placement/geometry.py`
- Test: `tests/placement/test_geometry_anchors.py`

- [ ] **Step 1: Écrire le test**

`tests/placement/test_geometry_anchors.py` :

```python
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_geometry_anchors.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implémenter (ajouter à `geometry.py`)**

```python
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
    """Point intérieur juste à côté de l'ouverture de porte, sur le mur `edge`."""
    dcx = (door_bbox[0] + door_bbox[2]) / 2.0
    dcy = (door_bbox[1] + door_bbox[3]) / 2.0
    t_door = _project_t((int(dcx), int(dcy)), edge)
    # demi-largeur de la porte projetée sur l'arête
    ts = [_project_t(c, edge) for c in _bbox_corners(door_bbox)]
    half = (max(ts) - min(ts)) / 2.0
    L = edge.length or 1.0
    delta = half + margin / L
    t_side = t_door + delta if (t_door + delta) <= 1.0 else t_door - delta
    return point_on_edge(edge, t_side, inset, centroid)
```

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/placement/test_geometry_anchors.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/planrec/placement/geometry.py tests/placement/test_geometry_anchors.py
git commit -m "feat(placement): project_extents, triangle_apex, beside_door"
```

---

### Task 5: Couche de raffinement (snap mur + anti-collision)

**Files:**
- Modify: `src/planrec/placement/geometry.py`
- Test: `tests/placement/test_geometry_refine.py`

- [ ] **Step 1: Écrire le test**

`tests/placement/test_geometry_refine.py` :

```python
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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_geometry_refine.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implémenter (ajouter à `geometry.py`)**

```python
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
```

- [ ] **Step 4: Lancer (passe) + suite complète géométrie**

Run: `.venv/bin/pytest tests/placement/ -q`
Expected: PASS (toutes les tâches 1-5)

- [ ] **Step 5: Commit**

```bash
git add src/planrec/placement/geometry.py tests/placement/test_geometry_refine.py
git commit -m "feat(placement): couche raffinement snap_to_wall + resolve_collisions"
```

---

## Phase 2 — Spec chambre + résolveur

### Task 6: Spec déclarative chambre

**Files:**
- Create: `src/planrec/placement/spec.py`
- Test: `tests/placement/test_spec.py`

- [ ] **Step 1: Écrire le test**

`tests/placement/test_spec.py` :

```python
from src.planrec.placement.spec import BEDROOM_SPEC, SPEC_BY_ROOM_TYPE


def test_bedroom_spec_has_six_rules_in_order():
    keys = [r.equip_key for r in BEDROOM_SPEC]
    assert keys == ["Prise", "Prise", "RJ45", "Prise", "Switch", "LightPoint"]


def test_each_rule_has_unique_id():
    ids = [r.rule_id for r in BEDROOM_SPEC]
    assert len(ids) == len(set(ids))


def test_rj45_anchors_to_first_socket():
    rj45 = next(r for r in BEDROOM_SPEC if r.equip_key == "RJ45")
    assert rj45.anchor.kind == "adjacent"
    assert rj45.anchor.ref == "prise_1"


def test_bedroom_registered_for_bedroom_room_type():
    assert SPEC_BY_ROOM_TYPE["BedRoom"] is BEDROOM_SPEC
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_spec.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implémenter la spec**

`src/planrec/placement/spec.py` :

```python
"""Specs de placement déclaratives par type de pièce. Pilote : chambre.

Une Rule = un équipement + une stratégie d'ancrage. Le résolveur place les
règles dans l'ordre ; les règles peuvent référencer un résultat précédent
par `rule_id` (ex : la RJ45 ancrée à la 1re prise).
"""
from __future__ import annotations
from dataclasses import dataclass

LEFT = "left"
RIGHT = "right"


@dataclass(frozen=True)
class Anchor:
    """Stratégie d'ancrage d'un équipement.

    kind :
      - "bed_side"     : côté `side` du lit, sur le mur tête-de-lit
      - "adjacent"     : accolé au résultat `ref` (autre règle)
      - "triangle"     : sur le mur d'en face, triangle avec `refs`
      - "beside_door"  : à côté de la porte, sur son mur
      - "centroid"     : barycentre de la pièce
    """
    kind: str
    side: str | None = None
    ref: str | None = None
    refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    equip_key: str
    anchor: Anchor


BEDROOM_SPEC: list[Rule] = [
    Rule("prise_1", "Prise",      Anchor(kind="bed_side", side=LEFT)),
    Rule("prise_2", "Prise",      Anchor(kind="bed_side", side=RIGHT)),
    Rule("rj45_1",  "RJ45",       Anchor(kind="adjacent", ref="prise_1")),
    Rule("prise_3", "Prise",      Anchor(kind="triangle", refs=("prise_1", "prise_2"))),
    Rule("switch_1", "Switch",    Anchor(kind="beside_door")),
    Rule("light_1", "LightPoint", Anchor(kind="centroid")),
]


SPEC_BY_ROOM_TYPE: dict[str, list[Rule]] = {
    "BedRoom": BEDROOM_SPEC,
}
```

- [ ] **Step 4: Lancer (passe) + commit**

Run: `.venv/bin/pytest tests/placement/test_spec.py -q`
Expected: PASS (4 passed)

```bash
git add src/planrec/placement/spec.py tests/placement/test_spec.py
git commit -m "feat(placement): spec déclarative chambre (6 règles ordonnées)"
```

---

### Task 7: Résolveur — placement holistique chambre + dégradation

**Files:**
- Create: `src/planrec/placement/resolver.py`
- Test: `tests/placement/test_resolver_bedroom.py`

Le résolveur prend un `RoomContext` + un dict `{equip_key: count}` (les quantités viennent des règles NFC en amont) et rend `list[PlacedEquipment]`. Constantes de placement : `INSET=15`, `MIN_GAP=22`, `ACCOLE_GAP=22`, `SNAP_MAX=20`, seuil incertitude `UNCERTAIN_MOVE=18`.

- [ ] **Step 1: Écrire le test golden + dégradation**

`tests/placement/test_resolver_bedroom.py` :

```python
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

    # RJ45 accolée à une prise tête-de-lit
    rj = g["RJ45"][0]
    dists = [((rj.x - s.x) ** 2 + (rj.y - s.y) ** 2) ** 0.5 for s in head_sockets]
    assert min(dists) <= 30

    # interrupteur côté porte (bas, vers x=150)
    sw = g["Switch"][0]
    assert sw.y >= 175
    assert sw.x > 110

    # point lumineux central
    light = g["LightPoint"][0]
    assert abs(light.x - 100) <= 20 and abs(light.y - 100) <= 20

    assert all(not p.uncertain for p in placed)


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
```

- [ ] **Step 2: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_resolver_bedroom.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implémenter le résolveur**

`src/planrec/placement/resolver.py` :

```python
"""Résolveur : RoomContext + counts → équipements positionnés.

Place les règles de la spec dans l'ordre, en résolvant chaque ancre via les
primitives géométriques, puis applique la couche de raffinement (snap mur +
anti-collision). Marque `uncertain` quand une ancre repose sur une détection
absente ou quand le raffinement a dû déplacer un point au-delà du seuil.
"""
from __future__ import annotations

from src.planrec.placement.contracts import Detection, RoomContext, PlacedEquipment
from src.planrec.placement.spec import SPEC_BY_ROOM_TYPE, Rule, LEFT, RIGHT
from src.planrec.placement import geometry as g

INSET = 15
MIN_GAP = 22
ACCOLE_GAP = 22
SNAP_MAX = 20
UNCERTAIN_MOVE = 18


def _find(dets: list[Detection], classes: set[str]) -> Detection | None:
    """Détection de plus haute confiance parmi `classes` (None si aucune)."""
    cands = [d for d in dets if d.cls in classes]
    return max(cands, key=lambda d: d.confidence) if cands else None


def place_room(ctx: RoomContext, counts: dict[str, int]) -> list[PlacedEquipment]:
    spec = SPEC_BY_ROOM_TYPE.get(ctx.room_type)
    if spec is None:
        return []

    edges = g.room_edges(ctx.polygon)
    centroid = g.polygon_centroid(ctx.polygon)
    bed = _find(ctx.furniture, {"Bed", "Double Bed", "Single Bed"})
    door = _find(ctx.openings, {"door", "Door", "Single Door", "Double Door"})

    head_wall = g.wall_behind(bed.bbox, edges) if bed else None
    door_wall = g.edge_of(door.bbox, edges) if door else None

    # consommation des quantités NFC par type, dans l'ordre de la spec
    remaining = dict(counts)
    by_id: dict[str, PlacedEquipment] = {}
    placed: list[PlacedEquipment] = []
    extra_sockets_t = 0.15   # répartition des prises hors-spec sur murs libres

    def take(equip_key: str) -> bool:
        if remaining.get(equip_key, 0) <= 0:
            return False
        remaining[equip_key] -= 1
        return True

    for rule in spec:
        if not take(rule.equip_key):
            continue
        x, y, uncertain, reason = _resolve_rule(
            rule, ctx, edges, centroid, bed, door, head_wall, door_wall, by_id,
        )
        pe = PlacedEquipment(equip_key=rule.equip_key, x=x, y=y,
                             confidence=0.9 if not uncertain else 0.5,
                             uncertain=uncertain, reason=reason)
        by_id[rule.rule_id] = pe
        placed.append(pe)

    # Équipements excédentaires (au-delà de ce que la spec consomme) :
    # répartition uniforme sur le périmètre, marqués incertains.
    for equip_key, n in remaining.items():
        for _ in range(max(0, n)):
            t = extra_sockets_t % 1.0
            edge = edges[int(t * len(edges)) % len(edges)]
            px, py = g.point_on_edge(edge, (t * len(edges)) % 1.0, INSET, centroid)
            placed.append(PlacedEquipment(equip_key=equip_key, x=px, y=py,
                                          confidence=0.5, uncertain=True,
                                          reason="hors spec : répartition mur libre"))
            extra_sockets_t += 0.21

    _refine(placed, ctx, centroid)
    return placed


def _resolve_rule(rule: Rule, ctx, edges, centroid, bed, door,
                  head_wall, door_wall, by_id):
    a = rule.anchor
    uncertain = False
    reason = ""

    if a.kind == "bed_side":
        if bed and head_wall is not None:
            t_min, t_max = g.project_extents(bed.bbox, head_wall)
            t = t_min if a.side == LEFT else t_max
            x, y = g.point_on_edge(head_wall, t, INSET, centroid)
            reason = f"prise côté {a.side} du lit"
        else:
            # pas de lit : répartition sur le 1er mur, marquée incertaine
            t = 0.25 if a.side == LEFT else 0.75
            x, y = g.point_on_edge(edges[0], t, INSET, centroid)
            uncertain = True
            reason = "lit absent : prise répartie"
        return x, y, uncertain, reason

    if a.kind == "adjacent":
        ref = by_id.get(a.ref)
        if ref is not None:
            x = ref.x + ACCOLE_GAP
            y = ref.y
            return x, y, ref.uncertain, "RJ45 accolée à la prise"
        x, y = g.point_on_edge(edges[0], 0.1, INSET, centroid)
        return x, y, True, "prise de référence absente"

    if a.kind == "triangle":
        p1 = by_id.get(a.refs[0])
        p2 = by_id.get(a.refs[1])
        if p1 and p2 and head_wall is not None:
            opp = g.opposite_edge(head_wall, edges)
            x, y = g.triangle_apex((p1.x, p1.y), (p2.x, p2.y), opp, INSET, centroid)
            return x, y, (p1.uncertain or p2.uncertain), "prise en triangle, mur d'en face"
        opp = g.opposite_edge(edges[0], edges)
        x, y = g.point_on_edge(opp, 0.5, INSET, centroid)
        return x, y, True, "triangle dégradé"

    if a.kind == "beside_door":
        if door and door_wall is not None:
            x, y = g.beside_door(door.bbox, door_wall, INSET, centroid)
            return x, y, False, "interrupteur à côté de la porte"
        # pas de porte : mur le plus proche du barycentre, incertain
        x, y = g.point_on_edge(edges[0], 0.5, INSET, centroid)
        return x, y, True, "porte absente : interrupteur approximatif"

    if a.kind == "centroid":
        return centroid[0], centroid[1], False, "point lumineux central"

    return centroid[0], centroid[1], True, "ancre inconnue"


def _refine(placed: list[PlacedEquipment], ctx: RoomContext, centroid) -> None:
    """Snap mur (sauf point lumineux) puis anti-collision. Mute en place."""
    for pe in placed:
        if pe.equip_key == "LightPoint":
            continue
        (nx, ny), moved = g.snap_to_wall(
            (pe.x, pe.y), ctx.wall_lines, SNAP_MAX, INSET, centroid,
        )
        pe.x, pe.y = nx, ny
        if moved > UNCERTAIN_MOVE:
            pe.uncertain = True

    movable = [pe for pe in placed if pe.equip_key != "LightPoint"]
    pts = g.resolve_collisions([(pe.x, pe.y) for pe in movable], MIN_GAP)
    for pe, (x, y) in zip(movable, pts):
        pe.x, pe.y = x, y
```

- [ ] **Step 4: Lancer (passe)**

Run: `.venv/bin/pytest tests/placement/test_resolver_bedroom.py -q`
Expected: PASS (4 passed)

Si le golden échoue sur une tolérance, ajuster les constantes (`INSET`, `ACCOLE_GAP`) — PAS les assertions, qui encodent la logique métier.

- [ ] **Step 5: Suite complète moteur + commit**

Run: `.venv/bin/pytest tests/placement/ -q`
Expected: PASS (toutes phases 1-2)

```bash
git add src/planrec/placement/resolver.py tests/placement/test_resolver_bedroom.py
git commit -m "feat(placement): résolveur chambre holistique + dégradation incertaine"
```

---

## Phase 3 — Câblage du modèle YOLO portes/fenêtres

### Task 8: Loader + inférence portes dans Streamlit

**Files:**
- Modify: `app/streamlit_app.py` (à côté de `load_yolo_brique_a_model` ~ligne 198-229)

Pas de test automatisé (dépend d'un modèle `.pt` lourd et de Streamlit). Vérification manuelle en fin de tâche.

- [ ] **Step 1: Ajouter la constante checkpoint**

Sous `YOLO_BRIQUE_A_CHECKPOINT = "runs/detect/runs/detect/brique_a_v1/weights/best.pt"` (ligne 160), ajouter :

```python
YOLO_DOORS_CHECKPOINT = "runs/train/v3_doors_windows/weights/best.pt"
```

- [ ] **Step 2: Ajouter loader + runner** (après `run_yolo_brique_a`, ~ligne 229)

```python
@st.cache_resource(show_spinner=False)
def load_yolo_doors_model(checkpoint_path: str):
    """Lazy-load YOLO portes/fenêtres (classes {0: door, 1: window})."""
    from ultralytics import YOLO
    return YOLO(checkpoint_path)


@st.cache_data(show_spinner=False)
def run_yolo_doors(image_bytes: bytes, conf_threshold: float) -> list[dict]:
    """Inférence YOLO portes/fenêtres. Même format de sortie que brique A."""
    model = load_yolo_doors_model(YOLO_DOORS_CHECKPOINT)
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    results = model.predict(source=img, conf=conf_threshold, verbose=False)
    out: list[dict] = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls.item())
            cls_name = model.names[cls_id]   # "door" | "window"
            conf_score = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].cpu().numpy()]
            out.append({
                "class_name": cls_name,
                "confidence": conf_score,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            })
    return out
```

- [ ] **Step 3: Appeler l'inférence là où `run_yolo_brique_a` est appelé** (~ligne 1500)

Repérer le bloc :

```python
            raw_boxes = run_yolo_brique_a(img_bytes, yolo_conf_threshold)
            yolo_boxes = [
```

Juste avant la construction de `yolo_boxes`, ajouter la détection portes et la stocker pour réutilisation par le placement (les bboxes portes vont aussi servir d'overlay visuel comme le mobilier) :

```python
            raw_doors = run_yolo_doors(img_bytes, yolo_conf_threshold)
            st.session_state[f"doors_{img_hash}"] = raw_doors
```

(Le nom de variable du hash image est `img_hash` — vérifier en contexte ; sinon utiliser la clé hash déjà employée pour `pastille_to_devis_room_{img_hash}` ligne 1647.)

- [ ] **Step 4: Vérification manuelle**

Run: `.venv/bin/streamlit run app/streamlit_app.py`
- Uploader un plan avec une chambre, activer YOLO + segmentation.
- Vérifier dans les logs/console l'absence d'erreur de chargement du checkpoint portes.
- Confirmer (ajout temporaire d'un `st.write(st.session_state.get(f"doors_{img_hash}"))`) que des bboxes `door`/`window` sont retournées.

- [ ] **Step 5: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(placement): câble le modèle YOLO portes/fenêtres (v3_doors_windows)"
```

---

## Phase 4 — Intégration : moteur dans le flux Streamlit + halo incertain

### Task 9: Adapter `_make_smart_placer` pour les chambres

**Files:**
- Modify: `src/planrec/nfc_equipments.py` (`EquipmentInstance` + propagation `uncertain`)
- Modify: `app/streamlit_app.py` (`_make_smart_placer` ~ligne 552, call site ~ligne 1651)
- Test: `tests/placement/test_integration_adapter.py`

L'adaptateur précalcule un layout chambre holistique et l'expose au callback per-instance existant via un index `{(room, equip_type, idx): PlacedEquipment}`.

- [ ] **Step 1: Étendre `EquipmentInstance` avec `uncertain`**

Dans `src/planrec/nfc_equipments.py`, ajouter le champ au TypedDict (ligne 18-26) :

```python
class EquipmentInstance(TypedDict):
    """Une unité physique d'équipement placée sur le plan."""
    id: str        # "eq_<8 hex>"
    type: str      # clé EQUIP_TYPES
    room: str      # nom pièce devis (ex "Cuisine", "Chambre 2")
    x: int         # px image originale
    y: int
    color: str     # CSS color
    uncertain: bool  # placement auto à re-vérifier (halo orange)
```

Puis dans les 2 endroits qui créent des instances (`generate_equipments_from_devis_global` ~ligne 121 et `reconcile_equipments_for_line` ~ligne 292), ajouter `"uncertain": False,` au dict créé.

- [ ] **Step 2: Écrire le test de l'adaptateur**

`tests/placement/test_integration_adapter.py` :

```python
from src.planrec.placement.adapter import build_room_layout_index
from src.planrec.placement.contracts import Detection, RoomContext


def test_index_maps_room_type_idx_to_position():
    ctx = RoomContext(
        room_type="BedRoom",
        polygon=[(0, 0), (200, 0), (200, 200), (0, 200)],
        furniture=[Detection("Bed", (40, 2, 160, 90), 0.95)],
        openings=[Detection("door", (135, 195, 165, 200), 0.9)],
    )
    counts = {"Prise": 3, "RJ45": 1, "Switch": 1, "LightPoint": 1}
    index = build_room_layout_index("Chambre 1", ctx, counts)

    # 3 prises indexées 0,1,2
    assert ("Chambre 1", "Prise", 0) in index
    assert ("Chambre 1", "Prise", 2) in index
    assert ("Chambre 1", "Switch", 0) in index
    pe = index[("Chambre 1", "Prise", 0)]
    assert hasattr(pe, "x") and hasattr(pe, "uncertain")


def test_non_bedroom_returns_empty_index():
    ctx = RoomContext(room_type="Kitchen", polygon=[(0, 0), (10, 0), (10, 10), (0, 10)])
    assert build_room_layout_index("Cuisine", ctx, {"Prise": 6}) == {}
```

- [ ] **Step 3: Lancer (échoue)**

Run: `.venv/bin/pytest tests/placement/test_integration_adapter.py -q`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implémenter l'adaptateur**

`src/planrec/placement/adapter.py` :

```python
"""Pont entre le moteur de placement (holistique, par pièce) et le callback
per-instance `smart_placer(equip_type, room, idx, n_of_type)` de Streamlit.

`build_room_layout_index` appelle le résolveur une fois par pièce et range les
résultats par (room_label, equip_key, index_dans_le_type) pour lookup O(1).
"""
from __future__ import annotations

from src.planrec.placement.contracts import RoomContext, PlacedEquipment
from src.planrec.placement.resolver import place_room
from src.planrec.placement.spec import SPEC_BY_ROOM_TYPE

LayoutIndex = dict[tuple[str, str, int], PlacedEquipment]


def build_room_layout_index(
    room_label: str, ctx: RoomContext, counts: dict[str, int],
) -> LayoutIndex:
    """Layout holistique d'une pièce → index (room, type, idx) → PlacedEquipment.

    Retourne {} si le type de pièce n'a pas de spec (→ caller garde l'ancien
    placement).
    """
    if ctx.room_type not in SPEC_BY_ROOM_TYPE:
        return {}
    placed = place_room(ctx, counts)
    index: LayoutIndex = {}
    per_type_count: dict[str, int] = {}
    for pe in placed:
        idx = per_type_count.get(pe.equip_key, 0)
        index[(room_label, pe.equip_key, idx)] = pe
        per_type_count[pe.equip_key] = idx + 1
    return index
```

- [ ] **Step 5: Lancer (passe) + commit moteur**

Run: `.venv/bin/pytest tests/placement/test_integration_adapter.py -q`
Expected: PASS (2 passed)

```bash
git add src/planrec/nfc_equipments.py src/planrec/placement/adapter.py tests/placement/test_integration_adapter.py
git commit -m "feat(placement): adaptateur layout chambre ↔ callback per-instance + champ uncertain"
```

- [ ] **Step 6: Brancher l'adaptateur dans `_make_smart_placer`**

Dans `app/streamlit_app.py`, modifier la signature de `_make_smart_placer` (ligne 552) pour accepter le contexte de placement intelligent :

```python
def _make_smart_placer(
    seg_result,
    image_size: tuple[int, int],
    pastilles_by_room: dict[str, tuple[int, int]],
    bedroom_layout_index: dict | None = None,
):
```

Au début de la closure `placer` (ligne 589), consulter l'index AVANT toute autre logique :

```python
    layout_index = bedroom_layout_index or {}

    def placer(equip_type: str, room: str, idx: int, n_of_type: int):
        pe = layout_index.get((room, equip_type, idx))
        if pe is not None:
            return (pe.x, pe.y)
        polygon = poly_by_room.get(room)
        ...  # (logique existante inchangée à partir d'ici)
```

(Le champ `uncertain` est propagé séparément en Step 7 ; ici on ne renvoie que x,y pour rester compatible avec la signature `(x, y)` attendue par `reconcile_equipments_for_line`.)

- [ ] **Step 7: Construire l'index au call site et propager `uncertain`**

Au call site (~ligne 1651), AVANT `_placer = _make_smart_placer(...)`, construire l'index pour les chambres. Le mapping room_label→polygone/type est déjà calculé via `poly_by_room` interne à `_make_smart_placer` ; pour l'index il faut le `RoomContext` par chambre. Insérer :

```python
            from src.planrec.placement.contracts import Detection, RoomContext
            from src.planrec.placement.adapter import build_room_layout_index
            # _DEVIS_LABEL_TO_EQUIP_TYPE est déjà défini au niveau module de
            # streamlit_app.py (utilisé plus bas ligne ~1672) → pas d'import.

            _doors = st.session_state.get(f"doors_{img_hash}", [])
            _bedroom_index: dict = {}
            if enable_segmentation and result is not None:
                # counts par (room_label, equip_key) dérivés du devis courant
                _counts_by_room: dict[str, dict[str, int]] = {}
                for _li in _df_devis.index:
                    _r = str(_df_devis.at[_li, "Pièce"])
                    _lbl = str(_df_devis.at[_li, "Équipement"])
                    _t = _DEVIS_LABEL_TO_EQUIP_TYPE.get(_lbl)
                    if _t is None:
                        continue
                    _q = int(_df_devis.at[_li, "Qté"])
                    _counts_by_room.setdefault(_r, {})[_t] = _q
                # construit un RoomContext par chambre détectée
                for _room_label, _center in _pastilles_by_room.items():
                    _seg_room = _match_seg_room(result, _center)   # helper ci-dessous
                    if _seg_room is None or _seg_room.type != "BedRoom":
                        continue
                    _poly = [(int(p[0]), int(p[1])) for p in _seg_room.polygon]
                    _furn = [Detection(b["class_name"],
                                       (int(b["x1"]), int(b["y1"]), int(b["x2"]), int(b["y2"])),
                                       b["confidence"])
                             for b in (yolo_boxes or [])]
                    _open = [Detection(d["class_name"],
                                       (int(d["x1"]), int(d["y1"]), int(d["x2"]), int(d["y2"])),
                                       d["confidence"])
                             for d in _doors]
                    _ctx = RoomContext(room_type="BedRoom", polygon=_poly,
                                       furniture=_furn, openings=_open, wall_lines=[])
                    _bedroom_index.update(build_room_layout_index(
                        _room_label, _ctx, _counts_by_room.get(_room_label, {}),
                    ))

            _placer = _make_smart_placer(
                seg_result=result if enable_segmentation else None,
                image_size=(image_w, image_h),
                pastilles_by_room=_pastilles_by_room,
                bedroom_layout_index=_bedroom_index,
            )
```

Ajouter le helper `_match_seg_room` près de `_make_smart_placer` (réutilise le point-in-polygon déjà utilisé ligne 581-587) :

```python
def _match_seg_room(seg_result, center: tuple[int, int]):
    """Retourne la RoomDetection dont le polygone contient `center`, sinon None."""
    import numpy as _np
    import cv2 as _cv2
    if seg_result is None or not getattr(seg_result, "rooms", None):
        return None
    for sr in seg_result.rooms:
        poly = [(int(p[0]), int(p[1])) for p in sr.polygon]
        if len(poly) < 3:
            continue
        if _cv2.pointPolygonTest(_np.array(poly, _np.int32),
                                 (float(center[0]), float(center[1])), False) >= 0:
            return sr
    return None
```

Après la boucle de réconciliation (après ligne 1691), propager `uncertain` depuis l'index vers les instances :

```python
            # propage `uncertain` depuis l'index layout, par position de
            # l'instance dans son couple (room, type).
            _seen: dict[tuple[str, str], int] = {}
            for _e in _current_eq:
                _key2 = (_e["room"], _e["type"])
                _i2 = _seen.get(_key2, 0)
                _seen[_key2] = _i2 + 1
                _pe = _bedroom_index.get((_e["room"], _e["type"], _i2))
                _e["uncertain"] = bool(_pe.uncertain) if _pe is not None else False
```

Vérifier le nom exact `_DEVIS_LABEL_TO_EQUIP_TYPE` (déjà importé/utilisé ligne 1672) et `img_hash` en contexte.

- [ ] **Step 8: Vérification — non-régression suite complète**

Run: `.venv/bin/pytest -m "not slow" --tb=short -q`
Expected: PASS (aucune régression ; les tests AppTest devis passent toujours)

- [ ] **Step 9: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(placement): branche le moteur chambre dans _make_smart_placer (zéro régression hors chambre)"
```

---

### Task 10: Halo « incertain » dans le canvas React

**Files:**
- Modify: `app/components/pastille_canvas/__init__.py` (passer `uncertain` dans `equipments`)
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` (rendu halo)
- Build: `app/components/pastille_canvas/frontend/dist/` (commit du bundle)

- [ ] **Step 1: Vérifier que `uncertain` transite déjà**

`equipments` est passé tel quel au composant (ligne 116 `equipments=equipments or []`). Comme chaque `EquipmentInstance` porte maintenant `uncertain`, la prop traverse sans changement Python. Confirmer dans la docstring de `pastille_canvas` (ligne 82-84) en ajoutant la mention du champ :

```python
        equipments: optionnel, liste de dicts {id, type, room, x, y, color,
            uncertain} où x/y sont en coordonnées image originale. `uncertain`
            (bool) → halo orange « à vérifier » autour de l'icône.
```

- [ ] **Step 2: Localiser le rendu des équipements dans le TSX**

Run: `grep -n "equipments\|equip" app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx | head -30`
Repérer le `.map(...)` qui rend chaque icône équipement (là où `e.x`, `e.y`, `e.color` sont utilisés).

- [ ] **Step 3: Ajouter le halo conditionnel**

Sur l'élément racine de chaque icône équipement, ajouter une classe/style conditionnels quand `e.uncertain` est vrai. Exemple (adapter au JSX existant) :

```tsx
<div
  className="equip-icon"
  style={{
    left: `${toPct(e.x, imgW)}%`,
    top: `${toPct(e.y, imgH)}%`,
    boxShadow: e.uncertain ? "0 0 0 3px rgba(255,152,0,0.85)" : "none",
    borderRadius: "50%",
  }}
  title={e.uncertain ? "Placement auto à vérifier" : undefined}
>
  {/* contenu icône existant */}
</div>
```

Mettre à jour l'interface TS de l'équipement pour inclure `uncertain?: boolean`.

- [ ] **Step 4: Builder le bundle**

Run: `cd app/components/pastille_canvas/frontend && npm run build`
Expected: build OK, `dist/assets/index-*.js` régénéré.

- [ ] **Step 5: Vérification manuelle + commit**

Run: `.venv/bin/streamlit run app/streamlit_app.py`
- Uploader un plan avec chambre, masquer le lit (ou tester un plan sans lit détecté) → vérifier le halo orange sur les prises incertaines, et son absence quand tout est détecté.

```bash
git add app/components/pastille_canvas/__init__.py \
        app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx \
        app/components/pastille_canvas/frontend/dist
git commit -m "feat(placement): halo orange 'à vérifier' sur les équipements incertains"
```

---

## Mise à jour journal

- [ ] Mettre à jour `docs/journal/2026-06-12.md` : résumé de l'implémentation du placement intelligent chambre (moteur pur + câblage portes + intégration + halo incertain), et prochaines étapes (étendre cuisine/SDB en réutilisant le moteur).

---

## Récapitulatif fichiers

| Fichier | Responsabilité |
|---------|----------------|
| `src/planrec/placement/contracts.py` | Dataclasses I/O (RoomContext, Detection, PlacedEquipment) |
| `src/planrec/placement/geometry.py` | Primitives géométriques pures (Edge, murs, ancres, raffinement) |
| `src/planrec/placement/spec.py` | Spec déclarative chambre (règles ordonnées) |
| `src/planrec/placement/resolver.py` | Placement holistique + dégradation incertaine |
| `src/planrec/placement/adapter.py` | Pont layout pièce ↔ callback per-instance Streamlit |
| `app/streamlit_app.py` | Câblage YOLO portes + construction RoomContext + branchement placer |
| `src/planrec/nfc_equipments.py` | Champ `uncertain` sur EquipmentInstance |
| `PastilleCanvas.tsx` + `dist/` | Halo orange « à vérifier » |

## Hors périmètre (rappel spec)

Autres pièces (cuisine/salon/SDB), contraintes de hauteur NFC, ré-entraînement des modèles, routage des circuits. Le moteur est conçu pour étendre par ajout d'une spec dans `SPEC_BY_ROOM_TYPE`.
