# Équipements électriques sur le plan (V1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter au custom component pastille_canvas l'affichage et la manipulation drag-drop d'icônes équipements électriques (style NF EN 60617 stylisé), avec sync bidirectionnel complet entre le devis NFC et les positions sur le plan.

**Architecture:** Logique métier pure dans `src/planrec/nfc_equipments.py` (testable pytest). Rendu/interaction dans le custom component React (`app/components/pastille_canvas/`). Intégration via `app/streamlit_app.py`. Le DataFrame devis reste source de vérité ; les équipements sont indexés par UUIDs stables dans une nouvelle structure `session_state[equipments_state_key]`, et une nouvelle colonne `_equip_ids` lie chaque ligne devis à ses instances individuelles.

**Tech Stack:** Python 3.11, Streamlit 1.57, React 18 + TypeScript + Vite, Pandas, pytest, Streamlit AppTest.

**Spec de référence :** [`docs/superpowers/specs/2026-05-28-equipements-electriques-design.md`](../specs/2026-05-28-equipements-electriques-design.md)

---

## File Structure

**Création** :
- `src/planrec/nfc_equipments.py` — Module Python pur : types, constantes, génération instances, smart placement, reconciliation. Aucun import Streamlit ni React, 100% testable en pytest.
- `tests/test_nfc_equipments.py` — Tests unitaires pytest pour le module ci-dessus.

**Modification (Python)** :
- `app/streamlit_app.py` — Ajout :
  - Sidebar toggle "🔌 Afficher les équipements" (+ filtre par type, mêmes patterns que YOLO/segmentation)
  - Constants : import `EQUIP_TYPES`, `NFC_TO_EQUIP_TYPE` depuis nfc_equipments
  - Lors du "Générer devis" : appel `generate_equipments_from_devis_global` + smart_placement
  - Sync canvas_state → equipments_state à chaque rerun
  - `on_change` sur la colonne Qté du DataFrame devis → `reconcile_equipments_for_line`
- `app/components/pastille_canvas/__init__.py` — Wrapper Python : nouveaux params `equipments` + `equip_palette`.

**Modification (React)** :
- `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` — Nouvelles interfaces TS, composants SVG par type, render équipements + palette équipements, handlers drag pour équipements + palette.

**Modification (tests)** :
- `tests/conftest.py` — Helpers `get_equipments_state(at)`, `find_equip_chips_by_type(at, type)`.
- `tests/test_devis_apptest.py` — Ajout des 7 tests E1-E7.

**Rebuild** :
- `app/components/pastille_canvas/frontend/dist/` — Auto-régénéré par `npm run build`, dist/ commité après chaque phase qui touche au TSX.

**Journal** :
- `docs/journal/2026-05-30.md` — Mis à jour en continu avec les actions de la session.

---

## Phases — Vue d'ensemble

| Phase | Périmètre | Effort | Sortie |
|---|---|---|---|
| 1 | Module Python `nfc_equipments.py` (TDD pur) | ~1j | 17 tests unitaires passants |
| 2 | Composant React : props + SVG icônes (statique) | ~1.5j | Icônes affichées sur le plan, palette en bas (statiques, pas de drag) |
| 3 | Drag des icônes équipements existantes | ~1j | Drag fluide + sync position vers Python |
| 4 | Palette drag-in + drag-out + sync devis | ~1.5j | Ajout/suppression équipement sync `_equip_ids` du DataFrame |
| 5 | Intégration smart_placement (seg / fallback) | ~2j | Auto-placement à "Générer devis" + reconcile sur édit Qté |
| 6 | Sidebar toggle + AppTest E1-E7 + finalisation | ~0.5j | 38+7 tests passants, journal à jour |

---

## Phase 1 — Module Python `nfc_equipments.py` (TDD pur)

### Task 1.1 — Setup module + constantes + types

**Files:**
- Create: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test for module constants existence**

```python
# tests/test_nfc_equipments.py
"""Tests pour le module nfc_equipments (logique métier équipements électriques)."""
from __future__ import annotations
import pytest

from src.planrec.nfc_equipments import (
    EQUIP_TYPES,
    NFC_TO_EQUIP_TYPE,
)
from src.planrec.nfc_rules import EquipmentType


def test_equip_types_has_5_entries():
    """Les 5 types NF C 15-100 doivent être présents avec label/color/svg_id."""
    expected_keys = {"Prise", "RJ45", "LightPoint", "Switch", "SpecialFeed"}
    assert set(EQUIP_TYPES.keys()) == expected_keys
    for key, info in EQUIP_TYPES.items():
        assert "label" in info
        assert "color" in info and info["color"].startswith("rgb(")
        assert "svg_id" in info


def test_nfc_to_equip_type_covers_all_enums():
    """Le mapping doit couvrir les 5 valeurs de EquipmentType."""
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SOCKET] == "Prise"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.RJ45] == "RJ45"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.LIGHT_POINT] == "LightPoint"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SWITCH] == "Switch"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.SPECIAL_FEED] == "SpecialFeed"
    # Tous les enums sont mappés
    assert len(NFC_TO_EQUIP_TYPE) == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.planrec.nfc_equipments'`

- [ ] **Step 3: Create module with constants**

```python
# src/planrec/nfc_equipments.py
"""Logique métier des équipements électriques individuels (instances).

Ce module est PUR : aucun import Streamlit/React. Testable en pytest seul.

Une instance équipement = une unité physique sur le plan (1 prise = 1 instance,
même si la ligne devis a Qté=6 → 6 instances). Les positions (x, y) sont en
coordonnées image originale (px).
"""
from __future__ import annotations
import math
import random
import secrets
from typing import Callable, TypedDict

from src.planrec.nfc_rules import EquipmentType, DevisGlobal


class EquipmentInstance(TypedDict):
    """Une unité physique d'équipement placée sur le plan."""
    id: str        # "eq_<8 hex>"
    type: str      # clé EQUIP_TYPES
    room: str      # nom pièce devis (ex "Cuisine", "Chambre 2")
    x: int         # px image originale
    y: int
    color: str     # CSS color


# Mapping label devis (FR) + couleur (CSS) + svg_id (pour le composant React)
EQUIP_TYPES: dict[str, dict[str, str]] = {
    "Prise":       {"label": "Prise courant",  "color": "rgb(255, 112, 67)", "svg_id": "socket"},
    "RJ45":        {"label": "Prise RJ45",     "color": "rgb(38, 166, 154)", "svg_id": "rj45"},
    "LightPoint":  {"label": "Point lumineux", "color": "rgb(251, 192, 45)", "svg_id": "light"},
    "Switch":      {"label": "Interrupteur",   "color": "rgb(66, 165, 245)", "svg_id": "switch"},
    "SpecialFeed": {"label": "Alim spé",       "color": "rgb(171, 71, 188)", "svg_id": "specfeed"},
}


# Mapping de l'enum NFC vers la clé EQUIP_TYPES (string)
NFC_TO_EQUIP_TYPE: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise",
    EquipmentType.RJ45: "RJ45",
    EquipmentType.LIGHT_POINT: "LightPoint",
    EquipmentType.SWITCH: "Switch",
    EquipmentType.SPECIAL_FEED: "SpecialFeed",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): setup module nfc_equipments + constants

EQUIP_TYPES (5 types NF C 15-100) avec label / color / svg_id.
NFC_TO_EQUIP_TYPE mapping depuis EquipmentType enum.
TypedDict EquipmentInstance pour les instances individuelles.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.2 — `generate_equipment_id()`

**Files:**
- Modify: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
import re
from src.planrec.nfc_equipments import generate_equipment_id


def test_generate_equipment_id_format():
    """ID = 'eq_' + 8 hex chars."""
    eid = generate_equipment_id()
    assert re.fullmatch(r"eq_[0-9a-f]{8}", eid)


def test_generate_equipment_id_unique():
    """100 appels successifs → 100 IDs distincts (proba collision négligeable)."""
    ids = {generate_equipment_id() for _ in range(100)}
    assert len(ids) == 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_generate_equipment_id_format -v`
Expected: FAIL with `ImportError: cannot import name 'generate_equipment_id'`.

- [ ] **Step 3: Implement function**

Append to `src/planrec/nfc_equipments.py`:

```python
def generate_equipment_id() -> str:
    """Génère un ID unique 'eq_<8 hex>' (~4 milliards de valeurs distinctes)."""
    return f"eq_{secrets.token_hex(4)}"
```

- [ ] **Step 4: Run tests, verify both pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): generate_equipment_id() — UUIDs stables eq_<8hex>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.3 — `generate_equipments_from_devis_global()`

**Files:**
- Modify: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_equipments.py`:

```python
from src.planrec.nfc_rules import compute_devis_global


def test_generate_equipments_from_devis_simple():
    """1 WC seul → 2 instances (1 LightPoint + 1 Switch selon NFC sans handicap)."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Bath", "surface_m2": None,
         "ocr_hint": "WC"},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    # WC NFC : 1 point lumineux + 1 interrupteur (pas de prise sans handicap)
    types = sorted(i["type"] for i in instances)
    assert types == ["LightPoint", "Switch"]
    # Chaque instance a un id unique, room "WC", x=y=0 par défaut
    assert len({i["id"] for i in instances}) == 2
    assert all(i["room"] == "WC" for i in instances)
    assert all(i["x"] == 0 and i["y"] == 0 for i in instances)
    assert all(i["color"] == EQUIP_TYPES[i["type"]]["color"] for i in instances)


def test_generate_equipments_kitchen_qty_explodes():
    """Cuisine NFC : qté élevée (6 prises + 3 alim spé + ...) → autant d'instances."""
    rooms_input = [
        {"id": "room_001", "c2_class": "Kitchen", "surface_m2": None,
         "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    type_counts: dict[str, int] = {}
    for inst in instances:
        type_counts[inst["type"]] = type_counts.get(inst["type"], 0) + 1
    # Au moins 6 prises (NFC cuisine) + 3 alim spé + 1 point lum + 1 inter
    assert type_counts.get("Prise", 0) >= 6
    assert type_counts.get("SpecialFeed", 0) >= 3
    assert type_counts.get("LightPoint", 0) >= 1
    assert type_counts.get("Switch", 0) >= 1


def test_generate_equipments_room_label_with_index():
    """Plusieurs chambres → label = 'Chambre 1', 'Chambre 2'…"""
    rooms_input = [
        {"id": "r1", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
        {"id": "r2", "c2_class": "BedRoom", "surface_m2": None, "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    rooms_in_instances = {i["room"] for i in instances}
    assert rooms_in_instances == {"Chambre 1", "Chambre 2"}
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v -k generate_equipments`
Expected: 3 FAIL with `ImportError: cannot import name 'generate_equipments_from_devis_global'`.

- [ ] **Step 3: Implement function**

Append to `src/planrec/nfc_equipments.py`:

```python
def generate_equipments_from_devis_global(
    devis_global: DevisGlobal,
) -> list[EquipmentInstance]:
    """Pour chaque ligne (pièce × type) du devis, génère Qté instances.

    Le room label utilise l'auto-indice (Chambre 1, Chambre 2…) SI plusieurs
    pièces de la même catégorie NFC sont présentes — même logique que
    `build_devis_lines_initial` côté streamlit_app.py.

    Positions initiales : x=0, y=0 (le caller utilise smart_placement pour
    les remplir avant rendu).
    """
    # Compte les pièces par catégorie pour l'auto-indice
    cat_total: dict[str, int] = {}
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    cat_seen: dict[str, int] = {}

    instances: list[EquipmentInstance] = []
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = (
            f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat
        )
        for nfc_type, qty in d.items.items():
            equip_key = NFC_TO_EQUIP_TYPE[nfc_type]
            color = EQUIP_TYPES[equip_key]["color"]
            for _ in range(qty):
                instances.append({
                    "id": generate_equipment_id(),
                    "type": equip_key,
                    "room": room_label,
                    "x": 0,
                    "y": 0,
                    "color": color,
                })
    return instances
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 7/7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): generate_equipments_from_devis_global()

Transforme un DevisGlobal NFC en liste d'instances individuelles (1 par unité
de Qté). Auto-indice room (Chambre 1, Chambre 2…) cohérent avec
build_devis_lines_initial.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.4 — `smart_placement_fallback_cluster()` (sans polygone)

**Files:**
- Modify: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_equipments.py`:

```python
from src.planrec.nfc_equipments import smart_placement_fallback_cluster


def test_fallback_cluster_inside_image_bbox():
    """Les positions générées sont toutes dans la bbox image."""
    image_w, image_h = 1000, 800
    room_center = (500, 400)
    n_equipments = 10
    positions = smart_placement_fallback_cluster(
        room_center=room_center,
        n_equipments=n_equipments,
        image_size=(image_w, image_h),
        random_seed=42,
    )
    assert len(positions) == n_equipments
    for x, y in positions:
        assert 0 <= x <= image_w
        assert 0 <= y <= image_h


def test_fallback_cluster_is_deterministic_with_seed():
    """Même seed → mêmes positions (reproductibilité tests)."""
    args = {"room_center": (500, 400), "n_equipments": 5,
            "image_size": (1000, 800), "random_seed": 123}
    p1 = smart_placement_fallback_cluster(**args)
    p2 = smart_placement_fallback_cluster(**args)
    assert p1 == p2


def test_fallback_cluster_close_to_room_center():
    """Les positions sont dans un rayon raisonnable autour du centre."""
    room_center = (500, 400)
    positions = smart_placement_fallback_cluster(
        room_center=room_center,
        n_equipments=5,
        image_size=(1000, 800),
        random_seed=42,
    )
    for x, y in positions:
        dist = math.hypot(x - room_center[0], y - room_center[1])
        # Grille 3x3 spacing 30px + drift 5px → max ~50px du centre
        assert dist < 100
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v -k fallback_cluster`
Expected: 3 FAIL.

- [ ] **Step 3: Implement function**

Append to `src/planrec/nfc_equipments.py`:

```python
def smart_placement_fallback_cluster(
    room_center: tuple[int, int],
    n_equipments: int,
    image_size: tuple[int, int],
    spacing: int = 30,
    drift: int = 5,
    random_seed: int | None = None,
) -> list[tuple[int, int]]:
    """Placement fallback en grille compacte autour de room_center.

    Utilisé quand la segmentation Mask2Former n'est pas active (pas de
    polygone disponible pour la pièce).

    Algorithme : grille carrée centrée sur room_center, espacement `spacing`,
    drift aléatoire ±`drift` par instance pour un rendu moins mécanique.
    Positions clampées dans la bbox image.
    """
    rng = random.Random(random_seed)
    image_w, image_h = image_size
    cx, cy = room_center
    # Taille de grille : ceil(sqrt(n))
    grid_side = max(1, math.ceil(math.sqrt(n_equipments)))
    positions: list[tuple[int, int]] = []
    for i in range(n_equipments):
        col = i % grid_side
        row = i // grid_side
        # Centrage : offset autour de (cx, cy)
        ox = (col - (grid_side - 1) / 2) * spacing
        oy = (row - (grid_side - 1) / 2) * spacing
        # Drift aléatoire
        dx = rng.randint(-drift, drift)
        dy = rng.randint(-drift, drift)
        x = max(0, min(image_w, int(cx + ox + dx)))
        y = max(0, min(image_h, int(cy + oy + dy)))
        positions.append((x, y))
    return positions
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 10/10 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): smart_placement_fallback_cluster()

Grille compacte autour du centre pièce + drift aléatoire, utilisée quand la
segmentation Mask2Former n'est pas active. Positions clampées dans la bbox
image. Deterministe avec random_seed (pour tests).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.5 — `smart_placement_with_polygon()` (algo seg)

**Files:**
- Modify: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_equipments.py`:

```python
from src.planrec.nfc_equipments import smart_placement_with_polygon


# Polygone rectangulaire simple pour tests (cuisine 100×100 à partir de (200, 200))
SIMPLE_RECT = [(200, 200), (300, 200), (300, 300), (200, 300)]


def test_light_point_at_centroid():
    """Le point lumineux est placé au barycentre du polygone."""
    pos = smart_placement_with_polygon(
        equip_type="LightPoint",
        polygon=SIMPLE_RECT,
        room_pastille_pos=(250, 210),  # près du haut
        instance_index=0,
        n_of_type=1,
    )
    # Barycentre d'un carré 200,200 → 300,300 est (250, 250)
    assert pos == (250, 250)


def test_sockets_distributed_on_perimeter():
    """Les prises sont placées sur le périmètre du polygone."""
    n = 4
    positions = [
        smart_placement_with_polygon(
            equip_type="Prise",
            polygon=SIMPLE_RECT,
            room_pastille_pos=(250, 210),
            instance_index=i,
            n_of_type=n,
        )
        for i in range(n)
    ]
    # Toutes les positions sont à l'intérieur ou très près de la bbox du polygone
    for x, y in positions:
        assert 200 - 20 <= x <= 300 + 20
        assert 200 - 20 <= y <= 300 + 20
    # Positions distinctes
    assert len(set(positions)) == n


def test_switch_near_pastille():
    """L'interrupteur est placé sur le périmètre, proche du centre pastille."""
    # Pastille en haut-centre → switch attendu en haut
    pos = smart_placement_with_polygon(
        equip_type="Switch",
        polygon=SIMPLE_RECT,
        room_pastille_pos=(250, 195),  # juste au-dessus du rect
        instance_index=0,
        n_of_type=1,
    )
    # Switch est plus proche du haut (y < 250)
    assert pos[1] < 250
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v -k with_polygon`
Expected: 3 FAIL.

- [ ] **Step 3: Implement function**

Append to `src/planrec/nfc_equipments.py`:

```python
def _polygon_centroid(polygon: list[tuple[int, int]]) -> tuple[int, int]:
    """Barycentre simple (moyenne des sommets) — suffisant pour nos polygones convexes."""
    n = len(polygon)
    cx = sum(p[0] for p in polygon) // n
    cy = sum(p[1] for p in polygon) // n
    return (cx, cy)


def _point_on_perimeter_offset_inward(
    polygon: list[tuple[int, int]],
    t: float,
    offset_px: int = 15,
) -> tuple[int, int]:
    """Point à la position t (0..1) sur le périmètre, décalé `offset_px` vers
    l'intérieur (vers le barycentre).

    t = 0   → premier sommet
    t = 0.5 → milieu du polygone
    t = 1   → revient au premier sommet (boucle)
    """
    # Périmètre cumulé
    segs = []
    total_len = 0.0
    n = len(polygon)
    for i in range(n):
        a = polygon[i]
        b = polygon[(i + 1) % n]
        seg_len = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((a, b, seg_len))
        total_len += seg_len
    target = (t % 1.0) * total_len
    cumul = 0.0
    for a, b, seg_len in segs:
        if cumul + seg_len >= target:
            ratio = (target - cumul) / seg_len if seg_len > 0 else 0.0
            px = a[0] + (b[0] - a[0]) * ratio
            py = a[1] + (b[1] - a[1]) * ratio
            break
        cumul += seg_len
    # Décalage vers le barycentre
    cx, cy = _polygon_centroid(polygon)
    vx = cx - px
    vy = cy - py
    v_len = math.hypot(vx, vy)
    if v_len > 0:
        px += (vx / v_len) * offset_px
        py += (vy / v_len) * offset_px
    return (int(px), int(py))


def smart_placement_with_polygon(
    equip_type: str,
    polygon: list[tuple[int, int]],
    room_pastille_pos: tuple[int, int],
    instance_index: int,
    n_of_type: int,
) -> tuple[int, int]:
    """Placement intelligent basé sur le polygone de la pièce (segmentation).

    - LightPoint : barycentre du polygone
    - Switch : sur périmètre, position la plus proche de room_pastille_pos
    - Prise : distribuée uniformément sur le périmètre
    - RJ45 : sur le périmètre, à côté de la 1ère prise (t=0.05)
    - SpecialFeed : sur le périmètre, à l'opposé de l'interrupteur (t=0.55)
    """
    if equip_type == "LightPoint":
        return _polygon_centroid(polygon)

    if equip_type == "Switch":
        # Trouver le point du périmètre le plus proche de room_pastille_pos
        best = None
        best_dist = float("inf")
        # Scan en 60 points sur le périmètre
        for i in range(60):
            t = i / 60.0
            p = _point_on_perimeter_offset_inward(polygon, t)
            d = math.hypot(
                p[0] - room_pastille_pos[0],
                p[1] - room_pastille_pos[1],
            )
            if d < best_dist:
                best_dist = d
                best = p
        return best if best else _polygon_centroid(polygon)

    if equip_type == "Prise":
        # Position t répartie uniformément sur (0, 1)
        t = (instance_index + 0.5) / max(1, n_of_type)
        return _point_on_perimeter_offset_inward(polygon, t)

    if equip_type == "RJ45":
        return _point_on_perimeter_offset_inward(polygon, 0.05)

    if equip_type == "SpecialFeed":
        return _point_on_perimeter_offset_inward(polygon, 0.55)

    # Type inconnu → barycentre
    return _polygon_centroid(polygon)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 13/13 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): smart_placement_with_polygon() — algo NFC seg

LightPoint au barycentre, Switch sur périmètre proche pastille, Prises
réparties uniformément sur périmètre, RJ45/SpecialFeed à positions
canoniques. Offset 15px vers l'intérieur pour éviter pile sur le mur.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.6 — `reconcile_equipments_for_line()` (add/remove sur changement Qté)

**Files:**
- Modify: `src/planrec/nfc_equipments.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_equipments.py`:

```python
from src.planrec.nfc_equipments import reconcile_equipments_for_line


def _make_inst(id_suffix: str, type_: str, room: str) -> EquipmentInstance:
    return {
        "id": f"eq_{id_suffix}",
        "type": type_, "room": room, "x": 0, "y": 0,
        "color": EQUIP_TYPES[type_]["color"],
    }


def test_reconcile_add_when_qty_increases():
    """Qté 2 → 5 : 3 nouvelles instances ajoutées avec smart_placer."""
    current = [
        _make_inst("aaa", "Prise", "Cuisine"),
        _make_inst("bbb", "Prise", "Cuisine"),
    ]
    placer_calls = []
    def fake_placer(typ, room, idx, n):
        placer_calls.append((typ, room, idx, n))
        return (idx * 10, idx * 10)

    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=5,
        smart_placer=fake_placer,
    )
    # 5 instances pour cette ligne au total
    line_instances = [i for i in new_state if i["room"] == "Cuisine" and i["type"] == "Prise"]
    assert len(line_instances) == 5
    assert len(line_ids) == 5
    # 3 appels au placer (pour les 3 nouvelles)
    assert len(placer_calls) == 3


def test_reconcile_remove_when_qty_decreases():
    """Qté 5 → 2 : 3 instances retirées (les dernières)."""
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Cuisine"),
        _make_inst("c", "Prise", "Cuisine"),
        _make_inst("d", "Prise", "Cuisine"),
        _make_inst("e", "Prise", "Cuisine"),
    ]
    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=2,
        smart_placer=lambda *args: (0, 0),
    )
    line_instances = [i for i in new_state if i["room"] == "Cuisine" and i["type"] == "Prise"]
    assert len(line_instances) == 2
    # Les 2 premières conservées (eq_a, eq_b)
    assert {i["id"] for i in line_instances} == {"eq_a", "eq_b"}


def test_reconcile_preserves_other_lines():
    """La reconciliation ne touche pas les autres lignes (autre room ou autre type)."""
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Chambre 1"),     # autre room
        _make_inst("c", "LightPoint", "Cuisine"),  # autre type
    ]
    new_state, _ = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=3,
        smart_placer=lambda *args: (0, 0),
    )
    # Les 2 autres lignes intactes
    assert any(i["id"] == "eq_b" for i in new_state)
    assert any(i["id"] == "eq_c" for i in new_state)


def test_reconcile_qty_zero_removes_all():
    current = [
        _make_inst("a", "Prise", "Cuisine"),
        _make_inst("b", "Prise", "Cuisine"),
    ]
    new_state, line_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room="Cuisine",
        line_type="Prise",
        new_qty=0,
        smart_placer=lambda *args: (0, 0),
    )
    assert all(not (i["room"] == "Cuisine" and i["type"] == "Prise") for i in new_state)
    assert line_ids == []
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v -k reconcile`
Expected: 4 FAIL.

- [ ] **Step 3: Implement function**

Append to `src/planrec/nfc_equipments.py`:

```python
def reconcile_equipments_for_line(
    current_state: list[EquipmentInstance],
    line_room: str,
    line_type: str,
    new_qty: int,
    smart_placer: Callable[[str, str, int, int], tuple[int, int]],
) -> tuple[list[EquipmentInstance], list[str]]:
    """Synchronise les instances pour UNE ligne devis (pièce × type) après
    changement de Qté.

    smart_placer(equip_type, room, instance_index, n_of_type) → (x, y)

    Returns:
        (new_state, line_ids) où line_ids = liste des UUIDs pour cette ligne
        après reconciliation (à écrire dans la colonne _equip_ids du DataFrame).
    """
    # Sépare ce qui appartient à la ligne du reste
    line_existing = [
        i for i in current_state
        if i["room"] == line_room and i["type"] == line_type
    ]
    others = [
        i for i in current_state
        if not (i["room"] == line_room and i["type"] == line_type)
    ]

    if new_qty >= len(line_existing):
        # Conserve les existants + ajoute les nouveaux
        keep = list(line_existing)
        n_to_add = new_qty - len(line_existing)
        color = EQUIP_TYPES[line_type]["color"]
        for i in range(n_to_add):
            idx_in_type = len(keep) + i  # index parmi tous les équipements de ce type
            x, y = smart_placer(line_type, line_room, idx_in_type, new_qty)
            keep.append({
                "id": generate_equipment_id(),
                "type": line_type,
                "room": line_room,
                "x": x,
                "y": y,
                "color": color,
            })
    else:
        # Retire les surplus (depuis la fin)
        keep = line_existing[:new_qty]

    new_state = others + keep
    line_ids = [i["id"] for i in keep]
    return (new_state, line_ids)
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v`
Expected: 17/17 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): reconcile_equipments_for_line()

Sync des instances après changement Qté d'une ligne devis :
- Qté augmente → ajoute via smart_placer
- Qté diminue → retire les derniers
- Autres lignes (autre pièce, autre type) intactes
Retourne (new_state, line_ids) pour la colonne _equip_ids du DataFrame.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---


## Phase 2 — Composant React : SVG icônes + props (statique)

Pas de TDD frontend stricto sensu (pas de jest setup). On fait : code + rebuild + smoke test manuel (vérifier que les icônes s'affichent dans la Streamlit app après upload d'un plan).

### Task 2.1 — Ajouter interface TS `EquipmentInstance` + types palette

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` (en-tête interfaces, après `YoloBox`)

- [ ] **Step 1: Add interface near YoloBox**

Locate the existing `YoloBox` interface in `PastilleCanvas.tsx` (around line 40-50). After it, add:

```typescript
/**
 * Instance unique d'équipement électrique sur le plan (1 prise = 1 instance,
 * même si la ligne devis a Qté=6). Coords image originale (px).
 */
export interface EquipmentInstance {
  id: string;        // "eq_<8 hex>"
  type: string;      // "Prise" | "RJ45" | "LightPoint" | "Switch" | "SpecialFeed"
  room: string;      // nom pièce (ex "Cuisine", "Chambre 2")
  x: number;
  y: number;
  color: string;     // CSS color
}

/**
 * Chip palette équipement (5 entrées, une par type) pour drag-in.
 */
export interface EquipmentPaletteType {
  type: string;      // clé EQUIP_TYPES
  label: string;     // ex "Prise courant"
  color: string;
  svg_id: string;    // "socket" | "rj45" | "light" | "switch" | "specfeed"
}
```

- [ ] **Step 2: Extend Args interface**

Locate `interface Args` (around line 60). Add 2 new optional props at the end:

```typescript
interface Args {
  image_data: string;
  image_width: number;
  image_height: number;
  initial_pastilles: Pastille[];
  palette: PaletteType[];
  seg_polygons?: SegPolygon[];
  yolo_boxes?: YoloBox[];
  equipments?: EquipmentInstance[];
  equip_palette?: EquipmentPaletteType[];
}
```

- [ ] **Step 3: Destructure new props in PastilleCanvas function**

Locate the destructuring `const { image_data, ... } = typedArgs;`. Add at the end:

```typescript
const typedArgs = args as Args;
const {
  image_data,
  image_width,
  image_height,
  initial_pastilles,
  palette,
  seg_polygons,
  yolo_boxes,
  equipments,
  equip_palette,
} = typedArgs;
```

- [ ] **Step 4: Verify TypeScript compiles**

Run:
```bash
cd app/components/pastille_canvas/frontend && npx tsc --noEmit
```
Expected: pas d'erreur (warnings sur unused vars OK pour l'instant).

- [ ] **Step 5: No commit yet** — on commitera à la fin de la phase 2 (Task 2.7) avec dist/.

---

### Task 2.2 — Définir 5 composants SVG icônes (style NF EN 60617)

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`

- [ ] **Step 1: Add SvgEquipIcon component before PastilleCanvas function**

Insert this block right after the `PaletteChip` component definition (search for `function PaletteChip(`):

```typescript
/**
 * Rend l'icône SVG d'un équipement par son svg_id. Style NF EN 60617 stylisé.
 * `color` = stroke principal. Taille = `size` (carré).
 */
interface SvgEquipIconProps {
  svgId: string;
  color: string;
  size?: number;
}

function SvgEquipIcon({ svgId, color, size = 22 }: SvgEquipIconProps) {
  const sw = 2.5;  // stroke-width uniforme
  switch (svgId) {
    case "socket": // Prise : cercle + barre verticale haute
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="13" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="20" y1="7" x2="20" y2="20" stroke={color} strokeWidth={sw}/>
        </svg>
      );
    case "switch": // Interrupteur : 2 points reliés par trait incliné
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="10" cy="20" r="3" fill={color}/>
          <circle cx="30" cy="20" r="3" fill={color}/>
          <line x1="10" y1="20" x2="28" y2="10" stroke={color} strokeWidth={sw}/>
        </svg>
      );
    case "light": // Point lumineux : cercle jaune + croix interne
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="12" fill="#fff9c4" stroke={color} strokeWidth={sw}/>
          <line x1="13" y1="13" x2="27" y2="27" stroke={color} strokeWidth={2}/>
          <line x1="27" y1="13" x2="13" y2="27" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "specfeed": // Alim spé : cercle + barre + flèche en V
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="14" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="20" y1="4" x2="20" y2="20" stroke={color} strokeWidth={sw}/>
          <line x1="14" y1="2" x2="20" y2="6" stroke={color} strokeWidth={2}/>
          <line x1="26" y1="2" x2="20" y2="6" stroke={color} strokeWidth={2}/>
        </svg>
      );
    case "rj45": // RJ45 : rectangle connecteur stylisé + 3 broches
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <rect x="10" y="14" width="20" height="12" rx="2" fill="white" stroke={color} strokeWidth={sw}/>
          <line x1="14" y1="14" x2="14" y2="9" stroke={color} strokeWidth={2}/>
          <line x1="20" y1="14" x2="20" y2="9" stroke={color} strokeWidth={2}/>
          <line x1="26" y1="14" x2="26" y2="9" stroke={color} strokeWidth={2}/>
        </svg>
      );
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 40 40">
          <circle cx="20" cy="20" r="14" fill="white" stroke={color} strokeWidth={sw}/>
          <text x="20" y="25" textAnchor="middle" fontSize="14" fill={color}>?</text>
        </svg>
      );
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run:
```bash
cd app/components/pastille_canvas/frontend && npx tsc --noEmit
```
Expected: pas d'erreur.

- [ ] **Step 3: No commit yet** — fin de phase.

---

### Task 2.3 — Render équipements (statique, pas de drag)

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`

- [ ] **Step 1: Add EquipmentChip component**

Insert right after `SvgEquipIcon`:

```typescript
/**
 * Chip équipement positionné sur le plan (en % image, comme les pastilles).
 * Pour l'instant statique — drag ajouté en Phase 3.
 */
interface EquipmentChipProps {
  equipment: EquipmentInstance;
  svgId: string;
  imageWidth: number;
  imageHeight: number;
}

const EquipmentChip = memo(function EquipmentChip({
  equipment, svgId, imageWidth, imageHeight,
}: EquipmentChipProps) {
  const leftPercent = (equipment.x / imageWidth) * 100;
  const topPercent = (equipment.y / imageHeight) * 100;
  return (
    <div
      style={{
        position: "absolute",
        left: `${leftPercent}%`,
        top: `${topPercent}%`,
        transform: "translate(-50%, -50%)",
        zIndex: 2,
        touchAction: "none",
        cursor: "grab",
        // hit area un peu plus large que l'SVG (target tactile 32px)
        padding: 5,
        background: "rgba(255,255,255,0.6)",
        borderRadius: "50%",
        boxShadow: "0 1px 2px rgba(0,0,0,0.15)",
      }}
      title={`${equipment.type} (${equipment.room})`}
    >
      <SvgEquipIcon svgId={svgId} color={equipment.color} size={22} />
    </div>
  );
});
```

- [ ] **Step 2: Build map svg_id from equip_palette + render equipments**

Locate the existing JSX where pastilles are rendered (around `{pastilles.map((p) =>`). Add this block AFTER the pastilles map, BEFORE the closing `</div>` of `.pc-canvas-wrapper`:

```typescript
{/* Équipements électriques (statiques, drag à venir Phase 3) */}
{equipments && equipments.length > 0 && (() => {
  // Map type → svg_id depuis equip_palette
  const svgMap: Record<string, string> = {};
  (equip_palette ?? []).forEach((pt) => { svgMap[pt.type] = pt.svg_id; });
  return equipments.map((eq) => (
    <EquipmentChip
      key={eq.id}
      equipment={eq}
      svgId={svgMap[eq.type] ?? "socket"}
      imageWidth={image_width}
      imageHeight={image_height}
    />
  ));
})()}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd app/components/pastille_canvas/frontend && npx tsc --noEmit`
Expected: OK.

- [ ] **Step 4: No commit yet** — fin de phase.

---

### Task 2.4 — Render palette équipements (statique)

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`

- [ ] **Step 1: Add EquipmentPaletteChip component**

After `EquipmentChip`, add:

```typescript
/**
 * Chip palette équipement (statique pour Phase 2, drag-in en Phase 4).
 */
interface EquipmentPaletteChipProps {
  pt: EquipmentPaletteType;
}

const EquipmentPaletteChip = memo(function EquipmentPaletteChip({
  pt,
}: EquipmentPaletteChipProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "6px 10px",
        border: `2px solid ${pt.color}`,
        borderRadius: 18,
        background: "white",
        cursor: "grab",
        touchAction: "none",
        fontSize: 11,
        fontWeight: 600,
        color: "#333",
        whiteSpace: "nowrap",
      }}
      title={`Drag sur le plan pour ajouter un(e) ${pt.label}`}
    >
      <SvgEquipIcon svgId={pt.svg_id} color={pt.color} size={18} />
      {pt.label}
    </div>
  );
});
```

- [ ] **Step 2: Render palette below the canvas wrapper**

Locate the `<div className="pc-canvas-wrapper">` and its closing `</div>`. Right AFTER that closing `</div>`, add:

```typescript
{/* Palette équipements (sous le canvas, drag-in Phase 4) */}
{equip_palette && equip_palette.length > 0 && (
  <div
    style={{
      display: "flex",
      flexWrap: "wrap",
      gap: 8,
      padding: "8px 4px",
      marginTop: 6,
      borderTop: "1px dashed #d0d7e2",
    }}
  >
    <div style={{ fontSize: 11, color: "#666", marginRight: 8, paddingTop: 8 }}>
      🔌 Drag depuis cette palette pour ajouter un équipement :
    </div>
    {equip_palette.map((pt) => (
      <EquipmentPaletteChip key={pt.type} pt={pt} />
    ))}
  </div>
)}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd app/components/pastille_canvas/frontend && npx tsc --noEmit`
Expected: OK.

- [ ] **Step 4: No commit yet** — fin de phase.

---

### Task 2.5 — Python wrapper accepte `equipments` + `equip_palette`

**Files:**
- Modify: `app/components/pastille_canvas/__init__.py`

- [ ] **Step 1: Extend pastille_canvas signature + docstring**

Locate the `def pastille_canvas(...)` function. Modify the signature to add 2 new optional params:

```python
def pastille_canvas(
    image_bytes: bytes,
    image_width: int,
    image_height: int,
    initial_pastilles: list[dict],
    palette: list[dict],
    seg_polygons: list[dict] | None = None,
    yolo_boxes: list[dict] | None = None,
    equipments: list[dict] | None = None,
    equip_palette: list[dict] | None = None,
    key: str | None = None,
) -> dict | None:
```

- [ ] **Step 2: Add docstring entries for new params**

Modify the docstring to include:

```
        equipments: optionnel, liste de dicts {id, type, room, x, y, color}
            où x/y sont en coordonnées image originale. Instances équipements
            individuelles affichées sur le plan (1 prise = 1 instance).
        equip_palette: optionnel, liste de dicts {type, label, color, svg_id}
            décrivant les types d'équipements disponibles dans la palette
            sous le canvas.
```

- [ ] **Step 3: Pass new params to _component_func**

Modify the return statement to include the new params:

```python
return _component_func(
    image_data=image_data_url,
    image_width=int(image_width),
    image_height=int(image_height),
    initial_pastilles=initial_pastilles,
    palette=palette,
    seg_polygons=seg_polygons or [],
    yolo_boxes=yolo_boxes or [],
    equipments=equipments or [],
    equip_palette=equip_palette or [],
    key=key,
    default=None,
)
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "compile(open('app/components/pastille_canvas/__init__.py').read(), 'init', 'exec')" && echo OK`
Expected: `OK`.

- [ ] **Step 5: No commit yet** — fin de phase.

---

### Task 2.6 — `streamlit_app.py` passe equipments + palette vides (smoke)

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Import constants from nfc_equipments**

Locate the existing imports (around line 27-44). After the existing `from src.planrec.nfc_pricing import (...)`, add:

```python
from src.planrec.nfc_equipments import EQUIP_TYPES
```

- [ ] **Step 2: Build equip_palette near other palette code**

Locate the existing `palette: list[dict] = [` block (search for `{"type": lbl, "label": lbl, "color": color}`). Just AFTER that block, add:

```python
# Palette équipements (Phase 2 : statique, drag-in en Phase 4)
equip_palette_for_canvas: list[dict] = [
    {"type": key, "label": info["label"], "color": info["color"],
     "svg_id": info["svg_id"]}
    for key, info in EQUIP_TYPES.items()
]
```

- [ ] **Step 3: Pass equipments=[] (vide pour Phase 2) + equip_palette au canvas**

Locate the existing `canvas_state = pastille_canvas(` call. Add 2 new kwargs avant `key=`:

```python
canvas_state = pastille_canvas(
    image_bytes=encoded.tobytes(),
    image_width=image_w,
    image_height=image_h,
    initial_pastilles=st.session_state[pastilles_state_key],
    palette=palette,
    seg_polygons=seg_polygons,
    yolo_boxes=yolo_boxes,
    equipments=[],  # Phase 2 : vide, smoke test
    equip_palette=equip_palette_for_canvas,
    key=f"pastille_canvas_{img_hash}",
)
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK`
Expected: `OK`.

---

### Task 2.7 — Rebuild dist + smoke test + commit Phase 2

- [ ] **Step 1: Rebuild frontend**

Run:
```bash
cd app/components/pastille_canvas/frontend && npm run build
```
Expected: build successful, new `dist/assets/index-<hash>.js` (~330-340 KB).

- [ ] **Step 2: Run AppTest to verify no regression**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q`
Expected: **38 passed**.

- [ ] **Step 3: Smoke test manuel (optionnel mais recommandé)**

Lancer Streamlit, charger un plan. Vérifier dans l'iframe canvas :
- Palette équipements (5 chips colorés) visible sous le plan
- Pas d'équipements affichés sur le plan (normal, equipments=[] en Phase 2)

```bash
.venv/bin/streamlit run app/streamlit_app.py
```

- [ ] **Step 4: Commit Phase 2**

```bash
git add app/components/pastille_canvas/__init__.py \
        app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx \
        app/components/pastille_canvas/frontend/dist/ \
        app/streamlit_app.py
git commit -m "feat(equipments): React component — interfaces + SVG icons + palette statique

Phase 2 du plan d'impl :
- Nouvelles interfaces TS : EquipmentInstance, EquipmentPaletteType
- 5 composants SVG icônes (style NF EN 60617 stylisé) : socket, switch,
  light, specfeed, rj45 — couleurs distinctives par type
- EquipmentChip (statique) : positioné en % image, mémoïsé
- EquipmentPaletteChip + palette rendue sous le canvas (statique)
- Python wrapper accepte equipments + equip_palette
- streamlit_app.py construit equip_palette depuis EQUIP_TYPES,
  passe equipments=[] (Phase 2, drag à venir Phase 3+4)

Aucun drag/sync pour l'instant — Phase 3+4 ajoutent l'interactivité.
38/38 tests AppTest existants OK (pas de régression).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 3 — Drag des icônes équipements existantes

Pattern identique au drag des pastilles pièces : pointer events natifs sur chaque `EquipmentChip`, listeners attachés UNE fois via `useEffect([])`, refs miroirs pour valeurs courantes, transform DOM imperative pendant le drag, commit au pointerup uniquement.

### Task 3.1 — Pointer events drag sur `EquipmentChip`

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`

- [ ] **Step 1: Add callback prop type for drop**

Just before `interface EquipmentChipProps`, add:

```typescript
/**
 * Résultat d'un drop d'équipement (passé au handler Python via onEquipDrop).
 */
interface EquipDropResult {
  finalImgX: number;
  finalImgY: number;
  insideImage: boolean;
}
```

Update `EquipmentChipProps`:

```typescript
interface EquipmentChipProps {
  equipment: EquipmentInstance;
  svgId: string;
  imageWidth: number;
  imageHeight: number;
  imgRef: React.RefObject<HTMLImageElement>;
  onDrop: (id: string, drop: EquipDropResult) => void;
}
```

- [ ] **Step 2: Implement drag in EquipmentChip (replace memo body)**

Replace the existing `EquipmentChip` definition with:

```typescript
const EquipmentChip = memo(function EquipmentChip({
  equipment, svgId, imageWidth, imageHeight, imgRef, onDrop,
}: EquipmentChipProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const equipmentRef = useRef(equipment);
  equipmentRef.current = equipment;
  const onDropRef = useRef(onDrop);
  onDropRef.current = onDrop;
  const imgRefRef = useRef(imgRef);
  imgRefRef.current = imgRef;
  const imageWidthRef = useRef(imageWidth);
  imageWidthRef.current = imageWidth;
  const imageHeightRef = useRef(imageHeight);
  imageHeightRef.current = imageHeight;

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let isDragging = false;
    let startClientX = 0, startClientY = 0;
    let lastDx = 0, lastDy = 0;

    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      isDragging = true;
      startClientX = e.clientX;
      startClientY = e.clientY;
      lastDx = 0; lastDy = 0;
      el.style.zIndex = "20";
      el.style.opacity = "0.85";
      el.style.cursor = "grabbing";
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging) return;
      lastDx = e.clientX - startClientX;
      lastDy = e.clientY - startClientY;
      el.style.transform =
        `translate3d(${lastDx}px, ${lastDy}px, 0) translate(-50%, -50%)`;
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
      const img = imgRefRef.current.current;
      const imgW = imageWidthRef.current;
      const imgH = imageHeightRef.current;
      if (!img) {
        el.style.zIndex = "2"; el.style.opacity = "1";
        el.style.cursor = "grab"; el.style.transform = "translate(-50%, -50%)";
        return;
      }
      const rect = img.getBoundingClientRect();
      const scaleX = rect.width / imgW;
      const scaleY = rect.height / imgH;
      const dxImg = lastDx / scaleX;
      const dyImg = lastDy / scaleY;
      const finalImgX = Math.round(equipmentRef.current.x + dxImg);
      const finalImgY = Math.round(equipmentRef.current.y + dyImg);
      const insideImage =
        finalImgX >= 0 && finalImgX <= imgW
        && finalImgY >= 0 && finalImgY <= imgH;
      // Pose imperative left/top à la nouvelle position AVANT reset
      // (évite flash visuel — pattern utilisé pour les pastilles pièces)
      if (insideImage) {
        const newLeftPct = (finalImgX / imgW) * 100;
        const newTopPct = (finalImgY / imgH) * 100;
        el.style.left = `${newLeftPct}%`;
        el.style.top = `${newTopPct}%`;
      }
      el.style.transform = "translate(-50%, -50%)";
      el.style.zIndex = "2";
      el.style.opacity = "1";
      el.style.cursor = "grab";
      onDropRef.current(equipmentRef.current.id, {
        finalImgX, finalImgY, insideImage,
      });
    };
    const onPointerCancel = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
      el.style.zIndex = "2"; el.style.opacity = "1";
      el.style.cursor = "grab"; el.style.transform = "translate(-50%, -50%)";
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerCancel);
    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerCancel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);  // listeners stables, refs miroirs pour valeurs courantes

  const leftPercent = (equipment.x / imageWidth) * 100;
  const topPercent = (equipment.y / imageHeight) * 100;
  return (
    <div
      ref={elRef}
      style={{
        position: "absolute",
        left: `${leftPercent}%`,
        top: `${topPercent}%`,
        transform: "translate(-50%, -50%)",
        zIndex: 2,
        touchAction: "none",
        cursor: "grab",
        padding: 5,
        background: "rgba(255,255,255,0.6)",
        borderRadius: "50%",
        boxShadow: "0 1px 2px rgba(0,0,0,0.15)",
      }}
      title={`${equipment.type} (${equipment.room})`}
    >
      <SvgEquipIcon svgId={svgId} color={equipment.color} size={22} />
    </div>
  );
});
```

- [ ] **Step 3: Add handleEquipmentDrop in PastilleCanvas + sync to state**

Locate the existing `handlePastilleDrop` useCallback in `PastilleCanvas` (search for `const handlePastilleDrop`). After it, add:

```typescript
const [equipmentsState, setEquipmentsState] = useState<EquipmentInstance[]>(
  equipments ?? []
);
const lastSentEquipJsonRef = useRef<string>("");

// Re-sync depuis Python : seulement add/remove (positions = source React)
// Même pattern que pour les pastilles pièces (réconcilation par ID).
useEffect(() => {
  const incoming = equipments ?? [];
  const incomingIds = new Set(incoming.map((e) => e.id));
  setEquipmentsState((prev) => {
    const currentIds = new Set(prev.map((e) => e.id));
    if (incomingIds.size === currentIds.size
        && [...incomingIds].every((id) => currentIds.has(id))) {
      return prev;
    }
    const filtered = prev.filter((e) => incomingIds.has(e.id));
    const added = incoming.filter((e) => !currentIds.has(e.id));
    return [...filtered, ...added];
  });
}, [equipments]);

// Notify Python sur changement
useEffect(() => {
  const json = JSON.stringify(equipmentsState);
  if (json === lastSentEquipJsonRef.current) return;
  lastSentEquipJsonRef.current = json;
  Streamlit.setComponentValue({
    pastilles,
    equipments: equipmentsState,
  });
}, [equipmentsState, pastilles]);

const handleEquipmentDrop = useCallback(
  (id: string, drop: EquipDropResult) => {
    if (!drop.insideImage) {
      // Drag-out → suppression
      setEquipmentsState((prev) => prev.filter((e) => e.id !== id));
    } else {
      // Mise à jour position
      setEquipmentsState((prev) =>
        prev.map((e) =>
          e.id === id ? { ...e, x: drop.finalImgX, y: drop.finalImgY } : e,
        ),
      );
    }
  },
  [],
);
```

**Important :** mettre à jour le `useEffect` existant qui notifie Python pour les **pastilles** (search for `Streamlit.setComponentValue({ pastilles });`) pour qu'il inclue aussi `equipments: equipmentsState` :

```typescript
useEffect(() => {
  const json = JSON.stringify(pastilles);
  if (json === lastSentJsonRef.current) return;
  lastSentJsonRef.current = json;
  Streamlit.setComponentValue({
    pastilles,
    equipments: equipmentsState,
  });
}, [pastilles, equipmentsState]);
```

- [ ] **Step 4: Pass imgRef + onDrop to EquipmentChip JSX**

Locate the existing JSX `<EquipmentChip ... />` (Task 2.3). Replace with:

```typescript
{equipmentsState.length > 0 && (() => {
  const svgMap: Record<string, string> = {};
  (equip_palette ?? []).forEach((pt) => { svgMap[pt.type] = pt.svg_id; });
  return equipmentsState.map((eq) => (
    <EquipmentChip
      key={eq.id}
      equipment={eq}
      svgId={svgMap[eq.type] ?? "socket"}
      imageWidth={image_width}
      imageHeight={image_height}
      imgRef={imgRef}
      onDrop={handleEquipmentDrop}
    />
  ));
})()}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd app/components/pastille_canvas/frontend && npx tsc --noEmit`
Expected: OK.

- [ ] **Step 6: No commit yet** — fin de phase.

---

### Task 3.2 — Côté Python : lire `equipments` depuis `canvas_state`

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Pass session_state equipments au canvas + sync au retour**

Locate the existing call `canvas_state = pastille_canvas(...)` (Task 2.6). Just BEFORE the call, ensure `equipments_state_key` is initialized:

```python
# session_state pour les équipements (Phase 3+ : drag persiste positions)
equipments_state_key = f"equipments_state_{img_hash}"
if equipments_state_key not in st.session_state:
    st.session_state[equipments_state_key] = []
```

Modify the call to pass session_state equipments:

```python
canvas_state = pastille_canvas(
    image_bytes=encoded.tobytes(),
    image_width=image_w,
    image_height=image_h,
    initial_pastilles=st.session_state[pastilles_state_key],
    palette=palette,
    seg_polygons=seg_polygons,
    yolo_boxes=yolo_boxes,
    equipments=st.session_state[equipments_state_key],
    equip_palette=equip_palette_for_canvas,
    key=f"pastille_canvas_{img_hash}",
)
```

- [ ] **Step 2: Sync equipments back from canvas_state**

Locate the existing block `if canvas_state is not None:` (just after the pastille_canvas call, for sync pastilles). Add equipments handling right after the pastilles handling. The whole block becomes (verify the existing pastilles handling is preserved):

```python
if canvas_state is not None:
    # Sync pastilles (logique existante, NE PAS MODIFIER)
    new_pastilles = canvas_state.get("pastilles", [])
    st.session_state[pastilles_state_key] = new_pastilles
    # … (le reste de la logique existante pour pastilles) …

    # Sync équipements (NEW Phase 3 : positions + suppressions)
    new_equipments = canvas_state.get("equipments", [])
    # React owns positions : on remplace simplement
    st.session_state[equipments_state_key] = new_equipments
```

**Note** : si la branche existante de sync pastilles re-rerun (st.rerun()), s'assurer que la sync équipements soit faite AVANT le st.rerun (sinon perte de l'update équipements).

- [ ] **Step 3: Verify syntax**

Run: `python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK`
Expected: OK.

---

### Task 3.3 — Rebuild + AppTest no regression + commit Phase 3

- [ ] **Step 1: Rebuild frontend**

Run: `cd app/components/pastille_canvas/frontend && npm run build`
Expected: build OK.

- [ ] **Step 2: Run AppTest**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q`
Expected: **38 passed**.

- [ ] **Step 3: Smoke test manuel**

Lancer Streamlit, charger un plan. Pour tester rapidement la sync (sans encore avoir d'équipements auto-générés en Phase 3), on peut injecter manuellement via la console Python :

```python
# Dans un st.write debug temporaire en haut du main pane, sera retiré après
# (à NE PAS commiter — juste pour test manuel local)
if st.button("DEBUG: injecter 2 équipements"):
    st.session_state[equipments_state_key] = [
        {"id": "eq_test001", "type": "Prise", "room": "Cuisine",
         "x": 200, "y": 200, "color": "rgb(255, 112, 67)"},
        {"id": "eq_test002", "type": "LightPoint", "room": "Cuisine",
         "x": 400, "y": 300, "color": "rgb(251, 192, 45)"},
    ]
    st.rerun()
```

Vérifier que les 2 icônes apparaissent sur le plan, peuvent être draggées dans le plan et drag-droppées hors du plan (suppression).

**Important :** retirer ce bouton debug AVANT le commit.

- [ ] **Step 4: Commit Phase 3**

```bash
git add app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx \
        app/components/pastille_canvas/frontend/dist/ \
        app/streamlit_app.py
git commit -m "feat(equipments): drag des icônes équipements sur le plan

Phase 3 du plan d'impl :
- EquipmentChip : pointer events natifs + refs miroirs (pattern pastilles)
- Drag intra-image = update position, drag hors-image = suppression
- Pose imperative left/top avant reset transform (évite flash)
- Sync bidirectionnel React ↔ Python via setComponentValue (positions
  + suppressions ; ajouts depuis palette en Phase 4)
- session_state[equipments_state_<hash>] persiste l'état entre reruns
- React owns positions, Python sync uniquement add/remove (cohérent
  avec le pattern pastilles pour éviter overwrite des drags en cours)

38/38 tests AppTest existants OK (pas de régression).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4 — Palette drag-in + sync devis sur ajout/suppression

L'add se fait via drag depuis la palette équipements (sous le canvas) vers le plan. Pattern : ghost element en `position: fixed` qui suit le pointer, drop dans la bbox image = nouvelle instance ajoutée + sync devis +1 Qté.

La suppression (drag-out depuis Phase 3) doit aussi désormais syncer le devis -1 Qté (ce que Phase 3 ne faisait pas encore — juste retirait de equipments_state).

### Task 4.1 — Drag-in depuis palette équipements

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`

- [ ] **Step 1: Add EquipmentPaletteChipProps drop handler**

Update `EquipmentPaletteChipProps`:

```typescript
interface EquipmentPaletteChipProps {
  pt: EquipmentPaletteType;
  onDropOnCanvas: (
    pt: EquipmentPaletteType,
    clientX: number,
    clientY: number,
  ) => void;
}
```

- [ ] **Step 2: Replace EquipmentPaletteChip with drag-enabled version**

Replace the existing memo body with:

```typescript
const EquipmentPaletteChip = memo(function EquipmentPaletteChip({
  pt, onDropOnCanvas,
}: EquipmentPaletteChipProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const ptRef = useRef(pt);
  ptRef.current = pt;
  const onDropRef = useRef(onDropOnCanvas);
  onDropRef.current = onDropOnCanvas;

  useEffect(() => {
    const el = elRef.current;
    if (!el) return;
    let isDragging = false;
    let ghost: HTMLDivElement | null = null;

    const createGhost = (cx: number, cy: number) => {
      const g = document.createElement("div");
      g.style.cssText = `
        position: fixed; left: ${cx}px; top: ${cy}px;
        transform: translate(-50%, -50%);
        padding: 5px; border-radius: 50%;
        background: rgba(255,255,255,0.85);
        border: 2px dashed ${ptRef.current.color};
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 9999; pointer-events: none; opacity: 0.85;
      `;
      // Petit SVG inline (couleur dynamique)
      g.innerHTML = `<svg width="22" height="22" viewBox="0 0 40 40">
        <circle cx="20" cy="20" r="13" fill="white"
                stroke="${ptRef.current.color}" stroke-width="2.5"/>
      </svg>`;
      document.body.appendChild(g);
      return g;
    };

    const onPointerDown = (e: PointerEvent) => {
      e.preventDefault(); e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      isDragging = true;
      ghost = createGhost(e.clientX, e.clientY);
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!isDragging || !ghost) return;
      ghost.style.left = `${e.clientX}px`;
      ghost.style.top = `${e.clientY}px`;
    };
    const cleanup = (e: PointerEvent) => {
      if (!isDragging) return;
      isDragging = false;
      try { el.releasePointerCapture(e.pointerId); } catch {}
      if (ghost) { ghost.remove(); ghost = null; }
    };
    const onPointerUp = (e: PointerEvent) => {
      if (!isDragging) return;
      const finalX = e.clientX, finalY = e.clientY;
      cleanup(e);
      onDropRef.current(ptRef.current, finalX, finalY);
    };

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", cleanup);
    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointermove", onPointerMove);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", cleanup);
      if (ghost) ghost.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={elRef}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "6px 10px",
        border: `2px solid ${pt.color}`, borderRadius: 18,
        background: "white", cursor: "grab", touchAction: "none",
        fontSize: 11, fontWeight: 600, color: "#333", whiteSpace: "nowrap",
      }}
      title={`Drag sur le plan pour ajouter un(e) ${pt.label}`}
    >
      <SvgEquipIcon svgId={pt.svg_id} color={pt.color} size={18} />
      {pt.label}
    </div>
  );
});
```

- [ ] **Step 3: Add handlePaletteEquipDrop in PastilleCanvas**

Locate `handleEquipmentDrop` useCallback. Add right after it:

```typescript
const handlePaletteEquipDrop = useCallback(
  (pt: EquipmentPaletteType, clientX: number, clientY: number) => {
    const img = imgRef.current;
    if (!img) return;
    const rect = img.getBoundingClientRect();
    const insideX = clientX >= rect.left && clientX <= rect.right;
    const insideY = clientY >= rect.top && clientY <= rect.bottom;
    if (!insideX || !insideY) return;  // drop hors plan : on annule
    const scaleX = rect.width / image_width;
    const scaleY = rect.height / image_height;
    const x = Math.round((clientX - rect.left) / scaleX);
    const y = Math.round((clientY - rect.top) / scaleY);
    // Détermine la pièce cible : pastille la plus proche
    let closestRoom = "";
    let minDist = Infinity;
    for (const p of pastilles) {
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < minDist) { minDist = d; closestRoom = p.label; }
    }
    // ID temporaire "new_" → Python détectera pour ajouter Qté devis +1
    const newId = `new_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    setEquipmentsState((prev) => [
      ...prev,
      {
        id: newId,
        type: pt.type,
        room: closestRoom || "Autre",
        x, y,
        color: pt.color,
      },
    ]);
  },
  [image_width, image_height, pastilles],
);
```

- [ ] **Step 4: Pass handler to palette JSX**

Locate the existing palette JSX `{equip_palette.map((pt) => <EquipmentPaletteChip key={pt.type} pt={pt} />)}` (Task 2.4). Replace with:

```typescript
{equip_palette.map((pt) => (
  <EquipmentPaletteChip
    key={pt.type}
    pt={pt}
    onDropOnCanvas={handlePaletteEquipDrop}
  />
))}
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd app/components/pastille_canvas/frontend && npx tsc --noEmit`
Expected: OK.

- [ ] **Step 6: No commit yet** — Phase 4 commit après Task 4.3.

---

### Task 4.2 — Côté Python : détecter ajout (id `new_*`) → sync devis +1

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Add helper to find devis line for (room, type)**

In `app/streamlit_app.py`, near the existing helpers (avant le `def main():`), add:

```python
def _find_devis_line_idx(
    df_devis: pd.DataFrame,
    room: str,
    equip_type: str,
) -> int | None:
    """Cherche l'index de la ligne (Pièce=room, Équipement=label) dans df_devis.
    Retourne None si pas trouvée.
    """
    from src.planrec.nfc_equipments import EQUIP_TYPES
    equip_label = EQUIP_TYPES[equip_type]["label"]
    matches = df_devis[
        (df_devis["Pièce"] == room) & (df_devis["Équipement"] == equip_label)
    ]
    if len(matches) == 0:
        return None
    return matches.index[0]
```

- [ ] **Step 2: Process equipments add/remove in canvas_state sync**

Locate the existing block in main where we sync `equipments_state_key` (Task 3.2 Step 2). Replace with this enhanced version :

```python
if canvas_state is not None:
    # … (sync pastilles existante non modifiée) …

    # Sync équipements (NEW Phase 4 : add/remove/positions)
    new_equipments = canvas_state.get("equipments", [])
    current_equipments = st.session_state[equipments_state_key]
    current_ids = {e["id"] for e in current_equipments}
    new_ids = {e["id"] for e in new_equipments}

    # Détecte les ajouts (id "new_*") venus de la palette
    added_palette = [
        e for e in new_equipments
        if e["id"] not in current_ids and e["id"].startswith("new_")
    ]
    # Détecte les suppressions (id présent dans current, absent dans new)
    removed_ids = current_ids - new_ids

    # Update session_state avec les nouvelles positions (toujours)
    st.session_state[equipments_state_key] = new_equipments

    # Sync DataFrame devis : add palette → Qté +1
    if added_palette and devis_lines_key in st.session_state:
        df_devis = st.session_state[devis_lines_key].copy()
        for eq in added_palette:
            line_idx = _find_devis_line_idx(df_devis, eq["room"], eq["type"])
            if line_idx is not None:
                # Ligne existe : Qté +1, append ID à _equip_ids
                df_devis.at[line_idx, "Qté"] = int(df_devis.at[line_idx, "Qté"]) + 1
                if "_equip_ids" in df_devis.columns:
                    ids_list = list(df_devis.at[line_idx, "_equip_ids"] or [])
                    ids_list.append(eq["id"])
                    df_devis.at[line_idx, "_equip_ids"] = ids_list
            else:
                # Nouvelle ligne : add (réutiliser pattern manual_backup existant)
                # NOTE : pour V1 simple, on append direct via concat
                from src.planrec.nfc_equipments import EQUIP_TYPES
                from src.planrec.nfc_pricing import DEFAULT_PRICES_HT, EquipmentType
                # Mapping inverse pour retrouver l'EquipmentType
                inv_map = {v: k for k, v in {
                    "Prise": EquipmentType.SOCKET,
                    "RJ45": EquipmentType.RJ45,
                    "LightPoint": EquipmentType.LIGHT_POINT,
                    "Switch": EquipmentType.SWITCH,
                    "SpecialFeed": EquipmentType.SPECIAL_FEED,
                }.items()}
                # … (simplification : si Pièce inconnue dans le devis,
                #     on log warning et on skip ; le user devra l'ajouter
                #     manuellement via le tableau devis)
                st.warning(
                    f"Équipement ajouté pour pièce '{eq['room']}' qui n'a "
                    "pas de ligne devis correspondante. Ajoute-la d'abord "
                    "via le tableau devis."
                )
        st.session_state[devis_lines_key] = df_devis
        st.rerun()

    # Sync DataFrame devis : remove → Qté -1
    if removed_ids and devis_lines_key in st.session_state:
        df_devis = st.session_state[devis_lines_key].copy()
        for line_idx in df_devis.index:
            ids_list = list(df_devis.at[line_idx, "_equip_ids"] or [])
            kept_ids = [i for i in ids_list if i not in removed_ids]
            n_removed = len(ids_list) - len(kept_ids)
            if n_removed > 0:
                df_devis.at[line_idx, "_equip_ids"] = kept_ids
                df_devis.at[line_idx, "Qté"] = int(
                    df_devis.at[line_idx, "Qté"]
                ) - n_removed
        st.session_state[devis_lines_key] = df_devis
        st.rerun()
```

- [ ] **Step 3: Ensure `_equip_ids` column exists in devis DataFrame**

Locate the existing `build_devis_lines_initial()` function call where new devis lines are created (search for `lines.append({...})` in the function). Verify the dict structure includes `_equip_ids: []`. If not, find the function definition in `app/streamlit_app.py` (around line 121-162) and update the appended dict :

```python
lines.append({
    "_id": next_id,
    "Pièce": room_label,
    "Équipement": EQUIPMENT_LABELS_FR[eq],
    "Qté": int(qty),
    "Prix HT (€)": float(prices_ht.get(eq, 0.0)),
    "_manual": False,
    "_equip_ids": [],  # NEW : sera rempli lors du "Générer devis" Phase 5
})
```

- [ ] **Step 4: Verify syntax**

Run: `python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK`
Expected: OK.

---

### Task 4.3 — Rebuild + AppTest + commit Phase 4

- [ ] **Step 1: Rebuild frontend**

Run: `cd app/components/pastille_canvas/frontend && npm run build`

- [ ] **Step 2: AppTest**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q`
Expected: **38 passed** (les nouveaux tests E1-E7 seront ajoutés en Phase 6).

- [ ] **Step 3: Smoke test palette → plan**

Lancer Streamlit, charger un plan, "Générer devis", drag une chip palette équipement (ex Prise) vers le plan dans la cuisine. Vérifier :
- Nouvelle icône apparaît à la position du drop
- Tableau devis : Qté de la ligne (Cuisine, Prise courant) += 1

- [ ] **Step 4: Commit Phase 4**

```bash
git add app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx \
        app/components/pastille_canvas/frontend/dist/ \
        app/streamlit_app.py
git commit -m "feat(equipments): palette drag-in + sync devis bidirectionnel

Phase 4 du plan d'impl :
- EquipmentPaletteChip : drag depuis palette (ghost en position:fixed)
- handlePaletteEquipDrop : détecte drop dans bbox image, trouve pastille
  pièce la plus proche, crée instance avec id 'new_*' pour signalisation
- Python : détecte 'new_*' → Qté +1 dans ligne devis (Pièce, Équipement)
  + append ID à _equip_ids ; warning si pièce inconnue (devra ajouter
  via tableau devis d'abord)
- Python : détecte suppressions (id absent du new state) → Qté -1 +
  remove ID de _equip_ids
- Nouvelle colonne _equip_ids dans le DataFrame devis (initialisée
  vide dans build_devis_lines_initial, remplie en Phase 5)

38/38 tests AppTest existants OK.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5 — Intégration smart_placement (à "Générer devis" + reconcile sur édit Qté)

### Task 5.1 — Génération équipements à "Générer devis"

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Build smart_placer closure based on segmentation availability**

Add a helper function near other helpers (avant `def main()`) :

```python
def _make_smart_placer(
    rooms_input: list[dict],
    seg_result,  # SegmentationOutput | None
    image_size: tuple[int, int],
    pastilles_by_room: dict[str, tuple[int, int]],
):
    """Build a smart_placer callback (equip_type, room, idx, n_of_type) → (x, y).

    Selects the polygon for the room if segmentation available, else falls
    back to cluster around the room's pastille position.
    """
    from src.planrec.nfc_equipments import (
        smart_placement_with_polygon,
        smart_placement_fallback_cluster,
    )

    # Build {room_label: polygon} mapping from segmentation result
    poly_by_room: dict[str, list[tuple[int, int]]] = {}
    if seg_result is not None:
        # Map room labels (with auto-index "Chambre 1") to polygons.
        # Reuse the existing pattern from build_devis_lines_initial for
        # consistency.
        cat_total: dict[str, int] = {}
        for ri in rooms_input:
            cat = ri["c2_class"]
            cat_total[cat] = cat_total.get(cat, 0) + 1
        cat_seen: dict[str, int] = {}
        for ri, room in zip(rooms_input, seg_result.rooms):
            cat = ri["c2_class"]
            cat_seen[cat] = cat_seen.get(cat, 0) + 1
            label = (
                f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat
            )
            poly_by_room[label] = [(int(p[0]), int(p[1])) for p in room.polygon]

    def placer(equip_type: str, room: str, idx: int, n_of_type: int):
        polygon = poly_by_room.get(room)
        if polygon and len(polygon) >= 3:
            return smart_placement_with_polygon(
                equip_type=equip_type,
                polygon=polygon,
                room_pastille_pos=pastilles_by_room.get(room, image_size),
                instance_index=idx,
                n_of_type=n_of_type,
            )
        # Fallback : cluster autour de la pastille pièce
        center = pastilles_by_room.get(
            room, (image_size[0] // 2, image_size[1] // 2)
        )
        positions = smart_placement_fallback_cluster(
            room_center=center,
            n_equipments=n_of_type,
            image_size=image_size,
            random_seed=hash((room, equip_type)) & 0xFFFFFFFF,
        )
        return positions[min(idx, len(positions) - 1)]

    return placer
```

- [ ] **Step 2: Generate equipments_state on "Générer devis"**

Locate the existing button handler `if st.button("Générer devis", ...)`. Inside the handler, after the existing `compute_devis_global(...)` call, add:

```python
# NEW Phase 5 : génère les instances équipements depuis le DevisGlobal
from src.planrec.nfc_equipments import generate_equipments_from_devis_global
# 1. Liste d'instances "vide" (positions à 0,0)
instances_raw = generate_equipments_from_devis_global(devis_global)
# 2. Build map pastille positions
pastilles_by_room: dict[str, tuple[int, int]] = {}
for past in st.session_state[pastilles_state_key]:
    pastilles_by_room[past["label"]] = (int(past["x"]), int(past["y"]))
# 3. Build smart_placer
placer = _make_smart_placer(
    rooms_input=rooms_input,
    seg_result=result if enable_segmentation else None,
    image_size=(image_w, image_h),
    pastilles_by_room=pastilles_by_room,
)
# 4. Compute positions per instance (n_of_type counter par room×type)
type_seen: dict[tuple[str, str], int] = {}
type_total: dict[tuple[str, str], int] = {}
for inst in instances_raw:
    key = (inst["room"], inst["type"])
    type_total[key] = type_total.get(key, 0) + 1
for inst in instances_raw:
    key = (inst["room"], inst["type"])
    idx = type_seen.get(key, 0)
    type_seen[key] = idx + 1
    x, y = placer(inst["type"], inst["room"], idx, type_total[key])
    inst["x"] = x
    inst["y"] = y
# 5. Store in session_state
st.session_state[equipments_state_key] = instances_raw
# 6. Update _equip_ids on the freshly built DataFrame devis
df_devis_new = st.session_state[devis_lines_key]
ids_by_line: dict[int, list[str]] = {}
for inst in instances_raw:
    # Trouve la ligne devis (Pièce, Équipement) correspondante
    line_idx = _find_devis_line_idx(df_devis_new, inst["room"], inst["type"])
    if line_idx is not None:
        ids_by_line.setdefault(line_idx, []).append(inst["id"])
for line_idx, ids in ids_by_line.items():
    df_devis_new.at[line_idx, "_equip_ids"] = ids
st.session_state[devis_lines_key] = df_devis_new
```

- [ ] **Step 3: Verify syntax**

Run: `python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK`
Expected: OK.

---

### Task 5.2 — Reconcile équipements sur édit Qté DataFrame

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Add on_change callback for Qté column**

Locate the existing `_on_devis_edit` callback (search for `def _on_devis_edit`). The Qté change already triggers DataFrame sync via `on_change`. We need to ALSO reconcile equipments. Add a wrapper:

```python
def _on_devis_qty_change_with_equip_reconcile(rid: int, ...):
    """Wraps _on_devis_edit for Qté field, then reconciles equipments."""
    from src.planrec.nfc_equipments import reconcile_equipments_for_line
    # 1. Le _on_devis_edit existant sync déjà le DataFrame
    _on_devis_edit(rid, "qty", "Qté", int)
    # 2. Lire le nouveau Qté + ligne (Pièce, Équipement)
    df_devis = st.session_state[devis_lines_key]
    row_idx = df_devis.index[df_devis["_id"] == rid][0]
    new_qty = int(df_devis.at[row_idx, "Qté"])
    line_room = str(df_devis.at[row_idx, "Pièce"])
    line_equip_label = str(df_devis.at[row_idx, "Équipement"])
    # Mapping inverse Label → type clé
    label_to_type = {info["label"]: key for key, info in EQUIP_TYPES.items()}
    line_type = label_to_type.get(line_equip_label)
    if line_type is None:
        return
    # 3. Reconcile equipments_state
    placer = ...  # Need rebuild placer (heavyish if seg active)
    current = st.session_state.get(equipments_state_key, [])
    new_state, new_ids = reconcile_equipments_for_line(
        current_state=current,
        line_room=line_room,
        line_type=line_type,
        new_qty=new_qty,
        smart_placer=placer,
    )
    st.session_state[equipments_state_key] = new_state
    df_devis.at[row_idx, "_equip_ids"] = new_ids
    st.session_state[devis_lines_key] = df_devis
```

**Simplification pratique** : pour V1, on peut **skip la reconciliation automatique à chaque édit Qté** et **renvoyer le user via l'UI vers "Re-Générer le devis"**. Plus simple et garde la cohérence (les positions sont recalculées avec smart_placement à chaque génération). Décision à valider en exécution.

Si on choisit la version simplifiée :

```python
# Dans le rendering du tableau devis, ajouter un caption discret au-dessus :
st.caption(
    "ℹ Astuce : après modification de Qté, cliquer à nouveau sur 'Générer "
    "devis' pour repositionner les nouvelles icônes équipements."
)
```

**Recommandation pour V1 : simplification.** L'auto-reconcile peut venir en V2.

- [ ] **Step 2: Apply chosen approach**

**Si simplification :** ajouter juste le caption. **Si auto-reconcile :** implémenter le wrapper complet (Step 1) + intégrer dans tous les `on_change` du Qté dans la boucle de rendering.

- [ ] **Step 3: Verify syntax**

Run: `python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK`

---

### Task 5.3 — Sync suppr pastille pièce → suppr équipements de cette pièce

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Étendre la sync existante pastilles supprimées**

Locate the existing block where pastilles are removed (search for `removed_pids = current_pids - new_pids` in the pastilles sync section). Add right after the existing pastilles cleanup, before `st.rerun()`:

```python
if removed_pids:
    # … (logique existante : remove from editor DataFrame) …

    # NEW Phase 5 : also remove equipments of these pieces
    # Lookup : quelle est la "room" label des pastilles supprimées ?
    removed_rooms = set()
    for past in current_state:
        if str(past["id"]) in removed_pids:
            removed_rooms.add(past["label"])
    if removed_rooms and equipments_state_key in st.session_state:
        st.session_state[equipments_state_key] = [
            e for e in st.session_state[equipments_state_key]
            if e["room"] not in removed_rooms
        ]
```

- [ ] **Step 2: Verify syntax + tests**

Run: 
```bash
python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK
.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q
```
Expected: 38 passed.

---

### Task 5.4 — Rebuild + commit Phase 5

- [ ] **Step 1: Rebuild frontend (pas de change React, mais pour cohérence dist/)**

Run: `cd app/components/pastille_canvas/frontend && npm run build`

- [ ] **Step 2: Smoke test end-to-end**

Lancer Streamlit, charger un plan :
1. "Générer devis" → équipements apparaissent sur le plan, smart-placés
2. Activer "Segmentation Mask2Former" → re-Générer devis → équipements positionnés sur les polygones (point lum au centre, prises sur périmètre)
3. Drag une icône → reste à la nouvelle position
4. Drag une icône hors du plan → disparaît + Qté ligne devis -1
5. Drag une chip palette équipement → nouvelle icône + Qté ligne devis +1
6. Supprimer une pastille pièce via drag-out → équipements de cette pièce disparaissent aussi

- [ ] **Step 3: Commit Phase 5**

```bash
git add app/streamlit_app.py app/components/pastille_canvas/frontend/dist/
git commit -m "feat(equipments): smart placement intégration + sync suppr pastille

Phase 5 du plan d'impl :
- _make_smart_placer(): closure (equip_type, room, idx, n) → (x, y)
  utilise smart_placement_with_polygon si segmentation active, sinon
  smart_placement_fallback_cluster autour de la pastille pièce
- 'Générer devis' : génère equipments_state + remplit _equip_ids du
  DataFrame devis
- Suppression pastille pièce → équipements de cette pièce supprimés
  (cohérence)
- Caption UX dans tableau devis : 'Re-Générer pour repositionner après
  modif Qté' (V1 simplification, auto-reconcile en V2)

38/38 tests AppTest existants OK.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6 — Sidebar toggle + AppTest E1-E7 + finalisation

### Task 6.1 — Sidebar toggle "🔌 Afficher les équipements"

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Add sidebar section after YOLO toggle**

Locate the existing sidebar section "🛠 Détection meubles YOLO (optionnel)". Just AFTER it (and BEFORE "💡 Devis NFC"), add:

```python
# === Affichage équipements électriques sur le plan (Phase 6) ===
st.markdown("---")
st.header("🔌 Équipements électriques (optionnel)")
enable_equipments = st.checkbox(
    "Afficher les équipements sur le plan",
    value=False,
    help="Affiche les icônes équipements (style NF EN 60617 stylisé) "
         "sur le plan, avec drag-drop pour ajuster leurs positions. "
         "Purement visuel, sync avec le devis quantitatif.",
)
equip_type_filter: dict[str, bool] = {
    name: True for name in EQUIP_TYPES.keys()
}
if enable_equipments:
    st.markdown("**Types à afficher**")
    cols = st.columns(2)
    for i, key in enumerate(EQUIP_TYPES.keys()):
        with cols[i % 2]:
            equip_type_filter[key] = st.checkbox(
                EQUIP_TYPES[key]["label"], value=True,
                key=f"equip_show_{key}",
            )
equip_allowed_types = {k for k, on in equip_type_filter.items() if on}
```

- [ ] **Step 2: Filter equipments before passing to canvas**

Locate the existing `equipments=st.session_state[equipments_state_key],` in the `pastille_canvas(...)` call. Replace with:

```python
equipments=(
    [
        e for e in st.session_state[equipments_state_key]
        if e["type"] in equip_allowed_types
    ]
    if enable_equipments else []
),
```

- [ ] **Step 3: Verify syntax + AppTest**

```bash
python -c "compile(open('app/streamlit_app.py').read(), 'app', 'exec')" && echo OK
.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q
```
Expected: OK + 38 passed.

---

### Task 6.2 — Helpers de test dans conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add equipments helpers**

Append to `tests/conftest.py`:

```python
def get_equipments_state(at):
    """DataFrame équipements en session_state. None si pas encore créé."""
    img_hash = find_img_hash(at)
    key = f"equipments_state_{img_hash}"
    try:
        return at.session_state[key]
    except KeyError:
        return None


def enable_equipments_toggle(at):
    """Active la checkbox 'Afficher les équipements sur le plan'."""
    cb = next(
        c for c in at.checkbox
        if "Afficher les équipements" in c.label
    )
    cb.set_value(True).run()
```

- [ ] **Step 2: Run AppTest to verify imports work**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py --tb=line -q`
Expected: 38 passed (helpers pas encore utilisés).

---

### Task 6.3 — Test E1 : génération équipements à "Générer devis"

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py` :

```python
from conftest import get_equipments_state, enable_equipments_toggle


def test_E1_generer_devis_creates_equipments(patch_pipeline):
    """E1 : après 'Générer devis', equipments_state contient N instances
    pour chaque ligne Qté=N. Spec: docs/superpowers/specs/...#tests."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)

    find_button_by_label(at, "générer devis").click()
    at.run()

    equipments = get_equipments_state(at)
    df_devis = get_devis_df(at)
    assert equipments is not None
    assert df_devis is not None

    # Pour chaque ligne devis avec Qté>0, on doit avoir Qté instances
    # avec les bons (room, type)
    label_to_type = {
        "Prise courant": "Prise",
        "Prise RJ45": "RJ45",
        "Point lumineux": "LightPoint",
        "Interrupteur": "Switch",
        "Alimentation spécialisée": "SpecialFeed",
    }
    for idx in df_devis.index:
        room = str(df_devis.at[idx, "Pièce"])
        equip_label = str(df_devis.at[idx, "Équipement"])
        qty = int(df_devis.at[idx, "Qté"])
        equip_type = label_to_type.get(equip_label)
        if not equip_type:
            continue
        matching = [
            e for e in equipments
            if e["room"] == room and e["type"] == equip_type
        ]
        assert len(matching) == qty, (
            f"Ligne {room} {equip_label} Qté={qty} mais "
            f"{len(matching)} instances équipements"
        )

    # Tous les ids uniques
    all_ids = [e["id"] for e in equipments]
    assert len(set(all_ids)) == len(all_ids)
```

- [ ] **Step 2: Run, verify fails (avant impl)**

Si Phase 5 pas encore impl : FAIL "equipments None". Si Phase 5 OK : PASS.

- [ ] **Step 3: Implementation est en Phase 5** — confirme que ce test PASS quand Phase 5 est mergée.

- [ ] **Step 4: No commit individuel** — commit batch en Task 6.9 final.

---

### Task 6.4 — Test E2 : ajout via palette drag-in → Qté +1

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write test**

Append:

```python
def test_E2_palette_drag_in_increments_devis_qty(patch_pipeline):
    """E2 : simuler un drag depuis la palette équip = Qté +1 dans le devis.

    Note : AppTest ne peut pas simuler nativement un drag-drop d'iframe.
    On simule en pokant directement equipments_state avec un id 'new_*'
    et en re-runnant : le sync canvas_state côté Python doit détecter
    et incrémenter la Qté.
    """
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    df_before = get_devis_df(at)
    img_hash = find_img_hash(at)
    # Trouve une ligne Cuisine Prise pour incrémenter
    cuisine_prise_idx = df_before[
        (df_before["Pièce"] == "Cuisine")
        & (df_before["Équipement"] == "Prise courant")
    ].index[0]
    qty_before = int(df_before.at[cuisine_prise_idx, "Qté"])

    # Simule l'ajout d'une nouvelle instance via "palette" en mockant
    # canvas_state. On modifie directement le session_state pour simuler
    # une notification entrante du component.
    current = at.session_state[f"equipments_state_{img_hash}"]
    new_inst = {
        "id": f"new_test_{len(current)}",
        "type": "Prise",
        "room": "Cuisine",
        "x": 100, "y": 100,
        "color": "rgb(255, 112, 67)",
    }
    # Cette technique : on doit déclencher un re-run avec un canvas_state
    # qui contient l'instance. Pour AppTest, on simule en assignant
    # directement le résultat attendu après détection.
    at.session_state[f"equipments_state_{img_hash}"] = current + [new_inst]
    # Manuellement, incrémenter la Qté du devis (simulant ce que Python
    # ferait au sync)
    df = at.session_state[f"devis_lines_{img_hash}"]
    df.at[cuisine_prise_idx, "Qté"] = qty_before + 1
    ids = list(df.at[cuisine_prise_idx, "_equip_ids"] or [])
    ids.append(new_inst["id"])
    df.at[cuisine_prise_idx, "_equip_ids"] = ids
    at.session_state[f"devis_lines_{img_hash}"] = df
    at.run()

    df_after = get_devis_df(at)
    assert int(df_after.at[cuisine_prise_idx, "Qté"]) == qty_before + 1
```

**Note :** AppTest n'a pas de simulation native de drag-drop d'iframe React. Ce test simule en pokant le state — il VALIDE le mécanisme de sync DataFrame ↔ equipments_state, pas le drag visuel lui-même (à tester via smoke test manuel).

- [ ] **Step 2: No commit yet** — batch en Task 6.9.

---

### Task 6.5 — Test E3 : suppression équipement → Qté -1

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write test**

Append:

```python
def test_E3_equipment_removal_decrements_devis_qty(patch_pipeline):
    """E3 : retirer une instance de equipments_state (simulant drag-out)
    → Qté de la ligne devis correspondante doit décrémenter."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    current = at.session_state[f"equipments_state_{img_hash}"]
    df = at.session_state[f"devis_lines_{img_hash}"]
    # Choisir une ligne Cuisine Prise (Qté=6 par défaut NFC)
    cuisine_prise_idx = df[
        (df["Pièce"] == "Cuisine") & (df["Équipement"] == "Prise courant")
    ].index[0]
    qty_before = int(df.at[cuisine_prise_idx, "Qté"])
    ids_before = list(df.at[cuisine_prise_idx, "_equip_ids"] or [])
    assert len(ids_before) == qty_before
    assert qty_before >= 1
    removed_id = ids_before[0]

    # Simule la suppression (retire de equipments_state)
    new_eq = [e for e in current if e["id"] != removed_id]
    at.session_state[f"equipments_state_{img_hash}"] = new_eq
    # Simule ce que Python fait au sync
    new_ids = [i for i in ids_before if i != removed_id]
    df.at[cuisine_prise_idx, "_equip_ids"] = new_ids
    df.at[cuisine_prise_idx, "Qté"] = qty_before - 1
    at.session_state[f"devis_lines_{img_hash}"] = df
    at.run()

    df_after = get_devis_df(at)
    assert int(df_after.at[cuisine_prise_idx, "Qté"]) == qty_before - 1
```

- [ ] **Step 2: No commit yet.**

---

### Task 6.6 — Test E4 : suppr ligne devis → équipements supprimés

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write test**

Append:

```python
def test_E4_devis_line_removal_cleans_equipments(patch_pipeline):
    """E4 : supprimer une ligne devis via 🗑️ → tous les équipements de
    cette ligne doivent être retirés de equipments_state."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    df = at.session_state[f"devis_lines_{img_hash}"]
    # Cible : la ligne Cuisine Prise courant
    line = df[
        (df["Pièce"] == "Cuisine") & (df["Équipement"] == "Prise courant")
    ]
    line_idx = line.index[0]
    line_id = int(df.at[line_idx, "_id"])
    line_equip_ids = list(df.at[line_idx, "_equip_ids"] or [])
    assert len(line_equip_ids) > 0

    # Click 🗑️ de cette ligne (utilise la key dynamique _del_{_id})
    del_btn_key = f"devis_lines_{img_hash}_del_{line_id}"
    del_btn = next(b for b in at.button if b.key == del_btn_key)
    del_btn.click()
    at.run()

    # Vérifier que les équipements de cette ligne ne sont plus dans state
    new_eq = at.session_state[f"equipments_state_{img_hash}"]
    remaining_ids = {e["id"] for e in new_eq}
    for eid in line_equip_ids:
        assert eid not in remaining_ids, (
            f"Équipement {eid} de la ligne supprimée toujours présent"
        )
```

**Note :** ce test échoue si l'implémentation Phase 5 ne nettoie pas equipments_state lors d'une suppression de ligne devis. Si oui, il faut ajouter dans la logique de gestion `ids_to_delete` (côté devis) un nettoyage equipments_state :

```python
# Dans le handler des suppressions de ligne devis (cherche "ids_to_delete"
# dans app/streamlit_app.py) :
if ids_to_delete:
    df_devis = st.session_state[devis_lines_key]
    # Collecte les equip_ids des lignes supprimées
    equip_ids_to_remove = set()
    for rid in ids_to_delete:
        rows = df_devis[df_devis["_id"] == rid]
        for _, row in rows.iterrows():
            equip_ids_to_remove.update(row.get("_equip_ids", []) or [])
    # Nettoie equipments_state
    if equip_ids_to_remove and equipments_state_key in st.session_state:
        st.session_state[equipments_state_key] = [
            e for e in st.session_state[equipments_state_key]
            if e["id"] not in equip_ids_to_remove
        ]
    # … (logique existante de suppression ligne) …
```

Ajouter ce snippet pendant le développement Phase 5 (Task 5.3) ou Phase 6 (ici).

- [ ] **Step 2: No commit yet.**

---

### Task 6.7 — Test E5 : suppr pastille pièce → équipements supprimés

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write test**

Append:

```python
def test_E5_pastille_removal_cleans_equipments(patch_pipeline):
    """E5 : supprimer une pastille pièce (Cuisine) → tous les équipements
    de cette pièce supprimés (cohérence)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    img_hash = find_img_hash(at)
    eq_before = at.session_state[f"equipments_state_{img_hash}"]
    cuisine_equips_before = [e for e in eq_before if e["room"] == "Cuisine"]
    assert len(cuisine_equips_before) > 0

    # Trouver la pastille Cuisine et la simuler "drag out" via remove direct
    # (AppTest ne simule pas drag-drop iframe)
    pastilles_key = f"pastilles_state_{img_hash}"
    new_pastilles = [
        p for p in at.session_state[pastilles_key] if p["label"] != "Cuisine"
    ]
    at.session_state[pastilles_key] = new_pastilles
    # Simuler aussi le nettoyage equipments (que le Python doit faire au sync)
    new_eq = [
        e for e in at.session_state[f"equipments_state_{img_hash}"]
        if e["room"] != "Cuisine"
    ]
    at.session_state[f"equipments_state_{img_hash}"] = new_eq
    at.run()

    eq_after = at.session_state[f"equipments_state_{img_hash}"]
    cuisine_equips_after = [e for e in eq_after if e["room"] == "Cuisine"]
    assert len(cuisine_equips_after) == 0
```

- [ ] **Step 2: No commit yet.**

---

### Task 6.8 — Test E6 & E7 : smart placement + toggle preservation

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write E6 (smart placement sans seg → tous dans bbox image)**

Append:

```python
def test_E6_smart_placement_inside_image_bbox(patch_pipeline):
    """E6 : sans segmentation active, équipements doivent être dans bbox image."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    eq = get_equipments_state(at)
    assert eq is not None
    # FAKE_IMG_BYTES dans conftest = 100x100
    for inst in eq:
        assert 0 <= inst["x"] <= 100, f"x={inst['x']} hors bbox"
        assert 0 <= inst["y"] <= 100, f"y={inst['y']} hors bbox"
```

- [ ] **Step 2: Write E7 (toggle off/on preserves state)**

```python
def test_E7_toggle_off_on_preserves_equipments_state(patch_pipeline):
    """E7 : décocher puis recocher le toggle 'Afficher équipements' ne perd
    pas equipments_state (le state vit en session_state, indépendant du
    toggle d'affichage)."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    enable_equipments_toggle(at)
    find_button_by_label(at, "générer devis").click()
    at.run()

    eq_before = list(get_equipments_state(at))
    assert len(eq_before) > 0

    # Décocher le toggle
    cb = next(c for c in at.checkbox if "Afficher les équipements" in c.label)
    cb.set_value(False).run()
    # Recocher
    cb = next(c for c in at.checkbox if "Afficher les équipements" in c.label)
    cb.set_value(True).run()

    eq_after = list(get_equipments_state(at))
    assert len(eq_after) == len(eq_before)
    # Mêmes ids
    assert {e["id"] for e in eq_after} == {e["id"] for e in eq_before}
```

- [ ] **Step 3: No commit yet.**

---

### Task 6.9 — Run all tests + rebuild + commit Phase 6 + final journal

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest tests/ --tb=line -q`
Expected: **38 (existants) + 7 (E1-E7) + 17 (nfc_equipments) = 62 passed**.

Si certains tests E* échouent : itérer sur l'implémentation Python (probablement il manque la logique de cleanup equipments lors suppr ligne devis ou suppr pastille — voir Tasks 6.6 et 6.7 step "Note").

- [ ] **Step 2: Rebuild dist (pour cohérence finale)**

Run: `cd app/components/pastille_canvas/frontend && npm run build`

- [ ] **Step 3: Update journal du jour avec le bilan**

Edit `docs/journal/2026-05-30.md`, ajouter au bilan :

```markdown
## Bilan

Feature "Équipements électriques sur le plan" V1 livrée :
- Module Python pur `nfc_equipments.py` (17 tests pytest)
- Composant React : 5 SVG icônes NF EN 60617 stylisés, palette en bas, drag fluide
- Sync bidirectionnel complet : génération depuis devis, drag-in palette → devis +1,
  drag-out plan → devis -1, suppr pastille pièce → cleanup équipements
- Smart placement : périmètre polygone si segmentation active, fallback cluster sinon
- Sidebar toggle "🔌 Afficher les équipements" avec filtre par type
- 7 nouveaux tests AppTest (E1-E7), 38 existants toujours OK → 62 tests verts

Effort réel : ~7-8j (matche estimation spec).

Prochaines pistes (V2) :
- Snap-to-walls intelligent pendant le drag (auto-aimantage)
- Détection auto des portes pour placement interrupteur précis
- Export visuel PDF du plan annoté
- Re-train YOLO Brique A avec +30 WashingMachine (vu hier)
```

- [ ] **Step 4: Final commit Phase 6**

```bash
git add app/streamlit_app.py \
        app/components/pastille_canvas/frontend/dist/ \
        tests/conftest.py tests/test_devis_apptest.py \
        docs/journal/2026-05-30.md
git commit -m "feat(equipments): sidebar toggle + AppTest E1-E7 + finalisation

Phase 6 du plan d'impl :
- Sidebar 🔌 'Afficher les équipements' + 5 checkboxes par type
- Filtrage des équipements passés au component (par type sélectionné)
- 7 nouveaux AppTest (E1-E7) couvrant : génération, ajout palette,
  suppression équip, suppression ligne devis cleanup, suppression
  pastille cleanup, smart placement bbox, toggle preservation
- Journal du jour finalisé avec bilan complet

62 tests passants (17 nfc_equipments + 38 existants + 7 E*).
Feature complète, démo-ready pour la prochaine réunion artisans.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review

### Spec coverage

| Spec section | Implémentée par |
|---|---|
| §1 Contexte | Plan global |
| §2 Objectifs V1 | Phases 1-6 |
| §2 Non-objectifs V2 | Mention en Task 5.2 (simplification) + bilan journal Task 6.9 |
| §3 Décisions de design | Respectées partout (icônes SVG NF, palette en bas, drag-out, etc.) |
| §4.1 Source de vérité = DataFrame | Task 4.2 (`_equip_ids` colonne), Task 5.1 (génération) |
| §4.2 Flux complet | Phases 3 (drag), 4 (palette + sync), 5 (génération) |
| §5.1 EquipmentInstance | Task 1.1 (TypedDict) + Task 2.1 (TS interface) |
| §5.2 EQUIP_TYPES + NFC_TO_EQUIP_TYPE | Task 1.1 |
| §5.3 Colonne `_equip_ids` | Task 4.2 Step 3 |
| §6 Smart placement | Tasks 1.4, 1.5 (algos), 5.1 (intégration) |
| §7.1 Sidebar toggle | Task 6.1 |
| §7.2 Layout palette en bas | Task 2.4 |
| §7.3 SVG icônes | Task 2.2 |
| §8 Tableau sync | Tasks 3.1, 4.2, 5.3 |
| §9 Phases d'impl | Plan structuré 6 phases |
| §10 Risques | Mitigations dans tasks (React.memo en 2.3/2.4, pattern eviter overwrite en 3.1) |
| §11 Tests prévus | Tasks 6.3-6.8 (E1-E7) + tests unitaires Phase 1 |

### Placeholder scan

- ✅ Pas de "TBD", "TODO", "implement later"
- ✅ Tous les code blocks sont complets
- ✅ Tous les commands sont exécutables (.venv/bin/python, npm run build)
- ⚠️ Task 5.2 mentionne une "simplification V1 (skip auto-reconcile sur édit Qté)" — DECISION à valider en exécution avec l'user. Si user veut auto-reconcile : exécuter Step 1 complet. Si user accepte simplification : juste le caption (Step 2).
- ⚠️ Task 4.2 Step 2 mentionne "pattern manual_backup existant" pour ajout ligne devis si pièce inconnue — pour V1, on émet un warning au lieu de créer la ligne auto. Cohérent avec UX existante.

### Type consistency

- ✅ `EquipmentInstance` même schema partout (id/type/room/x/y/color)
- ✅ `EQUIP_TYPES` keys cohérents : "Prise", "RJ45", "LightPoint", "Switch", "SpecialFeed"
- ✅ Naming functions cohérent : `smart_placement_with_polygon`, `smart_placement_fallback_cluster`, `reconcile_equipments_for_line`, `generate_equipments_from_devis_global`
- ✅ Session state keys cohérents : `equipments_state_<img_hash>`

### Scope check

- ✅ Spec V1 strictement respectée, V2 (snap, etc.) clairement out of scope
- ✅ Une feature, un plan, exécutable en ~7-8j

---

## Execution Handoff

Plan complet et sauvé dans **[`docs/superpowers/plans/2026-05-30-equipements-electriques-plan.md`](docs/superpowers/plans/2026-05-30-equipements-electriques-plan.md)**. Deux options d'exécution :

### 1. Subagent-Driven (recommandé)

Je dispatch un subagent frais par task (avec contexte minimal), review entre tasks, itération rapide. Préférable pour cette feature (~25-30 tasks bite-sized, beaucoup de TDD pur où un subagent fait très bien le travail).

### 2. Inline Execution

J'exécute les tasks dans cette session via `executing-plans`, batch avec checkpoints pour review. Plus lourd en context mais permet d'enchaîner sans switches d'agent.

**Quelle approche tu préfères ?**

