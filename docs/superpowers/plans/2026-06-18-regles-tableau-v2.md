# Règles tableau v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implémenter les règles tableau v2 : différentiels Type A/F/AC, prises générales 8 max, prises cuisine 20A dédiées, VMC auto, pompe à chaleur et borne véhicule manuelles, garantie ECS avec repli garage attenant.

**Architecture:** Les types/circuits/différentiels vivent dans `nfc_tableau.py` ; les équipements/garanties dans `nfc_rules.py` ; pastilles/palette dans `nfc_equipments.py` ; prix/libellés dans `nfc_pricing.py`. La géométrie « garage attenant » est hors scope (Spec B) — ici `attenant` est un attribut d'entrée (défaut `False`). Spec : [docs/superpowers/specs/2026-06-18-regles-tableau-v2-design.md](../specs/2026-06-18-regles-tableau-v2-design.md).

**Tech Stack:** Python 3.11, pytest. `.venv/bin/pytest`.

---

## ⚠ Staging git (WIP utilisateur)

`src/planrec/nfc_tableau.py` et `tests/test_nfc_tableau.py` contiennent du **WIP
utilisateur non-commité**. Les tâches qui les modifient NE doivent PAS faire
`git add <fichier>` directement (cela embarquerait le WIP). Le contrôleur de
session commite ces fichiers en **staging chirurgical** (`git show HEAD:<f>` +
réapplication des seules modifs de la tâche + `git hash-object` +
`git update-index --cacheinfo`). `nfc_rules.py`, `nfc_equipments.py`,
`nfc_pricing.py` sont propres → `git add` normal.

---

## File Structure
- `src/planrec/nfc_rules.py` — `EquipmentType` (VMC/HEAT_PUMP/EV_CHARGER), `Devis.attenant`, `_ensure_vmc`, `_ensure_ecs`, threading `attenant`.
- `src/planrec/nfc_tableau.py` — `CircuitType` (KITCHEN_SOCKET/VMC/HEAT_PUMP/EV_CHARGER), `Circuit.requires_type_f`, lighting Type A, socket max 8, kitchen sockets, `_SPECIALIZED_SPECS` étendu, `_compute_rcd_amps`, `_distribute_circuits_to_rcds` refonte.
- `src/planrec/nfc_equipments.py` — pastilles + palette VMC/PAC/borne.
- `src/planrec/nfc_pricing.py` — prix + libellés.
- Tests : `tests/test_nfc_tableau.py`, `tests/test_nfc_equipments.py`.

---

## Task 1 : Nouveaux types d'équipement + prix/libellés

**Files:** `src/planrec/nfc_rules.py`, `src/planrec/nfc_pricing.py`, `tests/test_nfc_equipments.py` (propres → `git add` normal).

- [ ] **Step 1 : test** — append à `tests/test_nfc_equipments.py` :

```python
def test_new_equipment_types_v2_have_price_and_label():
    from src.planrec.nfc_rules import EquipmentType
    from src.planrec.nfc_pricing import DEFAULT_PRICES_HT, EQUIPMENT_LABELS_FR
    for t in (EquipmentType.VMC, EquipmentType.HEAT_PUMP, EquipmentType.EV_CHARGER):
        assert DEFAULT_PRICES_HT[t] > 0
        assert len(EQUIPMENT_LABELS_FR[t]) > 0
    assert EquipmentType.VMC.value == "vmc"
    assert EquipmentType.HEAT_PUMP.value == "pompe_a_chaleur"
    assert EquipmentType.EV_CHARGER.value == "borne_vehicule"
```

- [ ] **Step 2 : run** — `.venv/bin/pytest tests/test_nfc_equipments.py::test_new_equipment_types_v2_have_price_and_label -v` → FAIL (AttributeError).

- [ ] **Step 3** — dans `src/planrec/nfc_rules.py`, enum `EquipmentType`, après `TOWEL_WARMER = "seche_serviettes"` :

```python
    # NEW v2 — VMC (auto), PAC + borne véhicule (manuels)
    VMC = "vmc"
    HEAT_PUMP = "pompe_a_chaleur"
    EV_CHARGER = "borne_vehicule"
```

- [ ] **Step 4** — dans `src/planrec/nfc_pricing.py`, ajouter aux deux dicts :

```python
    # DEFAULT_PRICES_HT :
    EquipmentType.VMC: 90.0,
    EquipmentType.HEAT_PUMP: 150.0,       # alim seule
    EquipmentType.EV_CHARGER: 250.0,      # alim seule
```
```python
    # EQUIPMENT_LABELS_FR :
    EquipmentType.VMC: "VMC",
    EquipmentType.HEAT_PUMP: "Alim pompe à chaleur",
    EquipmentType.EV_CHARGER: "Alim borne véhicule",
```

- [ ] **Step 5 : run** → PASS.

- [ ] **Step 6 : commit**

```bash
git add src/planrec/nfc_rules.py src/planrec/nfc_pricing.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): types VMC, pompe à chaleur, borne véhicule (+ prix/libellés)"
```

---

## Task 2 : Circuit.requires_type_f + nouveaux CircuitType

**Files:** `src/planrec/nfc_tableau.py` (WIP → staging chirurgical), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** — append à `tests/test_nfc_tableau.py` :

```python
def test_circuit_has_type_f_flag_default_false():
    from src.planrec.nfc_tableau import Circuit, CircuitType
    c = Circuit(id="c1", type=CircuitType.SOCKET, label="x", breaker_amps=16,
                cable_section_mm2=1.5)
    assert c.requires_type_f is False


def test_new_circuit_types_v2_exist():
    from src.planrec.nfc_tableau import CircuitType
    assert CircuitType.KITCHEN_SOCKET.value == "kitchen_socket"
    assert CircuitType.VMC.value == "vmc"
    assert CircuitType.HEAT_PUMP.value == "heat_pump"
    assert CircuitType.EV_CHARGER.value == "ev_charger"
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — `CircuitType` (après `TOWEL_WARMER`) :

```python
    KITCHEN_SOCKET  = "kitchen_socket"    # Prises cuisine (20A / 2,5 mm²)
    VMC             = "vmc"               # VMC (16A — Type A)
    HEAT_PUMP       = "heat_pump"         # Pompe à chaleur (32A — Type F)
    EV_CHARGER      = "ev_charger"        # Borne véhicule (32A — Type F)
```

- [ ] **Step 4** — dataclass `Circuit`, après `requires_type_a: bool = False` :

```python
    requires_type_f: bool = False
```

- [ ] **Step 5 : run** → PASS.

- [ ] **Step 6 : commit** (staging chirurgical — contrôleur).
  Message : `feat(tableau): Circuit.requires_type_f + CircuitType kitchen_socket/vmc/heat_pump/ev_charger`

---

## Task 3 : Éclairage en Type A

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** :

```python
def test_lighting_circuits_require_type_a():
    from src.planrec.nfc_tableau import _build_lighting_circuits
    circuits = _build_lighting_circuits([("Sejour", 3)])
    assert circuits and all(c.requires_type_a for c in circuits)
```

- [ ] **Step 2 : run** → FAIL (actuellement `requires_type_a=False`).

- [ ] **Step 3** — dans `_build_lighting_circuits`, les DEUX `Circuit(...)` (le `_flush` et la boucle de découpe) reçoivent `requires_type_a=True`. Le bloc `_flush` a déjà `requires_type_a=False` → passer à `True`. Le bloc de la boucle `while n_remaining > 0` n'a pas le champ → ajouter `requires_type_a=True,` après `n_devices=chunk,`.

- [ ] **Step 4 : run** → PASS.

- [ ] **Step 5 : commit** (staging chirurgical). `feat(tableau): circuits éclairage en Type A`

---

## Task 4 : Prises générales — 8 max

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : reconcile + test** — remplacer `test_sockets_large_room_dedicated_circuit` (qui attend 5+5+2) par :

```python
def test_sockets_large_room_split_by_eight():
    """Pièce 12 prises → découpée en circuits de 8 max : 8 + 4."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("Sejour", 12)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 2
    assert sorted(c.n_devices for c in circuits) == [4, 8]
    assert all(c.breaker_amps == 16 and c.cable_section_mm2 == 1.5
               for c in circuits)
```

- [ ] **Step 2 : run** → FAIL (max actuel = 5 → 5+5+2).

- [ ] **Step 3** — `SOCKET_MAX_PER_CIRCUIT = 5` → `8`. Mettre à jour le commentaire (`NFC : 16A/1,5mm² → 8 prises max`).

- [ ] **Step 4 : run** → PASS. Vérifier que `test_sockets_one_room_one_circuit` (5 prises → 1 circuit) passe toujours.

- [ ] **Step 5 : commit** (staging chirurgical). `feat(tableau): prises générales 8 max par circuit`

---

## Task 5 : Prises cuisine dédiées (20A / 2,5 mm²)

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** :

```python
def test_kitchen_sockets_dedicated_20a():
    from src.planrec.nfc_tableau import _build_kitchen_socket_circuits, CircuitType
    circuits = _build_kitchen_socket_circuits([("Cuisine", 6)])
    assert len(circuits) == 1
    assert circuits[0].type == CircuitType.KITCHEN_SOCKET
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].n_devices == 6


def test_generate_tableau_kitchen_sockets_separate(simple_kitchen_devis):
    # voir fixture en bas ; cuisine 6 prises → 1 circuit KITCHEN_SOCKET 20A,
    # aucune prise cuisine dans un circuit SOCKET 16A.
    from src.planrec.nfc_tableau import generate_tableau, CircuitType
    tableau = generate_tableau(devis_global=simple_kitchen_devis, heating_enabled=False)
    circuits = [c for r in tableau.rcds for c in r.circuits]
    ksock = [c for c in circuits if c.type == CircuitType.KITCHEN_SOCKET]
    assert len(ksock) == 1 and ksock[0].breaker_amps == 20
```

Fixture (append en haut du fichier de test, après les imports) :

```python
import pytest

@pytest.fixture
def simple_kitchen_devis():
    from src.planrec.nfc_rules import compute_devis_global
    return compute_devis_global([{"id": "K1", "c2_class": "Kitchen"}],
                                heating_enabled=False)
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — ajouter la constante (près de `SOCKET_MAX_PER_CIRCUIT`) :

```python
KITCHEN_SOCKET_MAX_PER_CIRCUIT = 6  # NFC : prises cuisine 20A / 2,5 mm²
```

Ajouter le builder (juste après `_build_socket_circuits`) :

```python
def _build_kitchen_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
) -> list[Circuit]:
    """Prises de cuisine : circuit dédié 20A / 2,5 mm², 6 prises max."""
    circuits: list[Circuit] = []
    for room_name, n_sockets in rooms_with_sockets:
        n_remaining = n_sockets
        while n_remaining > 0:
            chunk = min(n_remaining, KITCHEN_SOCKET_MAX_PER_CIRCUIT)
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.KITCHEN_SOCKET,
                label=f"Prises cuisine {room_name}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=[room_name],
                n_devices=chunk,
            ))
            n_remaining -= chunk
    return circuits
```

- [ ] **Step 4** — dans `generate_tableau`, là où `rooms_with_sockets` est rempli (boucle per_room, `n_sock = d.items.get(EquipmentType.SOCKET, 0)`), router selon la catégorie : déclarer `rooms_with_kitchen_sockets: list[tuple[str, int]] = []` à côté de `rooms_with_sockets`, puis :

```python
        n_sock = d.items.get(EquipmentType.SOCKET, 0)
        if n_sock > 0:
            if d.nfc_category == NFCCategory.KITCHEN:
                rooms_with_kitchen_sockets.append((room_label, n_sock))
            else:
                rooms_with_sockets.append((room_label, n_sock))
```

Et ajouter l'appel au builder (près de `circuits.extend(_build_socket_circuits(...))`) :

```python
    circuits.extend(_build_kitchen_socket_circuits(rooms_with_kitchen_sockets))
```

- [ ] **Step 5 : run** → PASS.

- [ ] **Step 6 : commit** (staging chirurgical). `feat(tableau): prises cuisine en circuit dédié 20A/2,5mm²`

---

## Task 6 : VMC / PAC / Borne dans _SPECIALIZED_SPECS

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** :

```python
def test_specialized_vmc_pac_ev_specs():
    from src.planrec.nfc_tableau import _build_specialized_circuits, CircuitType
    from src.planrec.nfc_rules import EquipmentType
    out = _build_specialized_circuits({
        EquipmentType.VMC: ["Cellier"],
        EquipmentType.HEAT_PUMP: ["Sejour"],
        EquipmentType.EV_CHARGER: ["Garage"],
    })
    by_type = {c.type: c for c in out}
    vmc = by_type[CircuitType.VMC]
    assert (vmc.breaker_amps, vmc.cable_section_mm2) == (16, 1.5)
    assert vmc.requires_type_a and not vmc.requires_type_f
    pac = by_type[CircuitType.HEAT_PUMP]
    assert (pac.breaker_amps, pac.cable_section_mm2) == (32, 6.0)
    assert pac.requires_type_f and not pac.requires_type_a
    ev = by_type[CircuitType.EV_CHARGER]
    assert (ev.breaker_amps, ev.cable_section_mm2) == (32, 6.0)
    assert ev.requires_type_f
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — étendre `_SPECIALIZED_SPECS` : le tuple passe à 6 éléments
  `(breaker_amps, cable_section_mm2, label, requires_type_a, requires_type_f, circuit_type)`. Mettre à jour les 6 lignes existantes en insérant `False` (type_f) avant le `circuit_type`, ex. :

```python
    EquipmentType.OVEN:    (20, 2.5, "Four",  False, False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.COOKTOP: (32, 6.0, "Plaque cuisson", True, False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.DISHWASHER: (20, 2.5, "Lave-vaisselle", False, False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.WASHING_MACHINE: (20, 2.5, "Lave-linge", True, False, CircuitType.LAUNDRY),
    EquipmentType.DRYER:   (20, 2.5, "Sèche-linge", False, False, CircuitType.LAUNDRY),
    EquipmentType.BOILER:  (20, 2.5, "Chaudière", False, False, CircuitType.BOILER),
    EquipmentType.VMC:        (16, 1.5, "VMC", True, False, CircuitType.VMC),
    EquipmentType.HEAT_PUMP:  (32, 6.0, "Pompe à chaleur", False, True, CircuitType.HEAT_PUMP),
    EquipmentType.EV_CHARGER: (32, 6.0, "Borne véhicule", False, True, CircuitType.EV_CHARGER),
```

Dans `_build_specialized_circuits`, dépaqueter 6 valeurs et poser les 2 flags :

```python
        amps, section, label, type_a, type_f, ctype = _SPECIALIZED_SPECS[eq_type]
        ...
            circuits.append(Circuit(
                ...
                requires_type_a=type_a,
                requires_type_f=type_f,
            ))
```

- [ ] **Step 4** — dans `generate_tableau`, ajouter les 3 types à la boucle de collecte `spec_rooms` (la liste de types itérés `(EquipmentType.OVEN, ... BOILER)`) : ajouter `EquipmentType.VMC, EquipmentType.HEAT_PUMP, EquipmentType.EV_CHARGER`.

- [ ] **Step 5 : run** → PASS.

- [ ] **Step 6 : commit** (staging chirurgical). `feat(tableau): circuits VMC/PAC/borne (Type A / Type F)`

---

## Task 7 : Calibre DDR — PAC comptée chauffage

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** :

```python
def test_rcd_amps_counts_heat_pump_as_heating():
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    pac = Circuit(id="p", type=CircuitType.HEAT_PUMP, label="PAC",
                  breaker_amps=32, cable_section_mm2=6.0, requires_type_f=True)
    # 32A chauffage plein pot → 32 → arrondi 40
    assert _compute_rcd_amps([pac]) == 40
```

- [ ] **Step 2 : run** → FAIL (PAC comptée ×0,5 → 16 → 25).

- [ ] **Step 3** — dans `_compute_rcd_amps`, ajouter `CircuitType.HEAT_PUMP` au tuple `heat_types`.

- [ ] **Step 4 : run** → PASS.

- [ ] **Step 5 : commit** (staging chirurgical). `feat(tableau): pompe à chaleur comptée en chauffage (calibre DDR)`

---

## Task 8 : Répartition différentiels A / F / AC (refonte)

**Files:** `src/planrec/nfc_tableau.py` (WIP), `tests/test_nfc_tableau.py` (WIP).

- [ ] **Step 1 : test** :

```python
def test_distribute_groups_by_differential_type():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    light = Circuit(id="l", type=CircuitType.LIGHTING, label="Ecl", breaker_amps=10,
                    cable_section_mm2=1.5, requires_type_a=True)
    plaque = Circuit(id="p", type=CircuitType.KITCHEN_SPECIAL, label="Plaque",
                     breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True)
    ev = Circuit(id="e", type=CircuitType.EV_CHARGER, label="Borne", breaker_amps=32,
                 cable_section_mm2=6.0, requires_type_f=True)
    sock = Circuit(id="s", type=CircuitType.SOCKET, label="Prises", breaker_amps=16,
                   cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([light, plaque, ev, sock], n_rcds=2)
    a = [r for r in rcds if r.rcd_type == "A"]
    f = [r for r in rcds if r.rcd_type == "F"]
    ac = [r for r in rcds if r.rcd_type == "AC"]
    assert a and all(c.requires_type_a for r in a for c in r.circuits)
    assert f and all(c.requires_type_f for r in f for c in r.circuits)
    assert ac and all(not c.requires_type_a and not c.requires_type_f
                      for r in ac for c in r.circuits)


def test_distribute_no_type_f_when_absent():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    light = Circuit(id="l", type=CircuitType.LIGHTING, label="Ecl", breaker_amps=10,
                    cable_section_mm2=1.5, requires_type_a=True)
    sock = Circuit(id="s", type=CircuitType.SOCKET, label="P", breaker_amps=16,
                   cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([light, sock], n_rcds=2)
    assert not any(r.rcd_type == "F" for r in rcds)
    assert any(r.rcd_type == "A" for r in rcds)


def test_distribute_splits_group_over_eight():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    circuits = [Circuit(id=f"l{i}", type=CircuitType.LIGHTING, label="E",
                        breaker_amps=10, cable_section_mm2=1.5, requires_type_a=True)
                for i in range(10)]
    rcds = _distribute_circuits_to_rcds(circuits, n_rcds=1)
    a = [r for r in rcds if r.rcd_type == "A"]
    assert len(a) == 2 and all(len(r.circuits) <= 8 for r in a)
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — remplacer entièrement `_distribute_circuits_to_rcds` par :

```python
def _distribute_circuits_to_rcds(
    circuits: list[Circuit],
    n_rcds: int,
) -> list[RCD]:
    """Répartit les circuits par famille de différentiel (A / F / AC).

    - Type A : circuits requires_type_a (plaque, lave-linge, éclairage, VMC).
    - Type F : circuits requires_type_f (pompe à chaleur, borne véhicule).
    - Type AC : le reste.
    Chaque famille est découpée en paquets de MAX_BREAKERS_PER_RCD (8). Le
    nombre total de DDR est complété par des DDR AC vides jusqu'à n_rcds (min
    typologie/surface). Calibre recalculé par circuit, 30 mA.
    """
    a_circuits = [c for c in circuits if c.requires_type_a]
    f_circuits = [c for c in circuits if c.requires_type_f and not c.requires_type_a]
    ac_circuits = [c for c in circuits if not c.requires_type_a and not c.requires_type_f]

    def _chunk(items: list[Circuit], rcd_type: str) -> list[RCD]:
        out: list[RCD] = []
        for i in range(0, max(len(items), 0), MAX_BREAKERS_PER_RCD):
            out.append(RCD(id=generate_rcd_id(), rcd_type=rcd_type, amps=40,
                           sensitivity_ma=30,
                           circuits=items[i:i + MAX_BREAKERS_PER_RCD]))
        return out

    rcds: list[RCD] = []
    # Toujours ≥ 1 Type A (l'éclairage est toujours présent) ; si vide, 1 DDR A vide.
    rcds.extend(_chunk(a_circuits, "A") or
                [RCD(id=generate_rcd_id(), rcd_type="A", amps=40,
                     sensitivity_ma=30, circuits=[])])
    # Type F seulement si des circuits le requièrent.
    rcds.extend(_chunk(f_circuits, "F"))
    # Reste en AC.
    rcds.extend(_chunk(ac_circuits, "AC"))

    # Complément jusqu'au minimum (typologie/surface) avec des DDR AC vides.
    while len(rcds) < n_rcds:
        rcds.append(RCD(id=generate_rcd_id(), rcd_type="AC", amps=40,
                        sensitivity_ma=30, circuits=[]))

    for rcd in rcds:
        rcd.amps = _compute_rcd_amps(rcd.circuits)
    return rcds
```

- [ ] **Step 4 : run** → PASS. Mettre à jour le commentaire de `RCD.rcd_type` (`"A" | "AC" | "F"`).

- [ ] **Step 5 : commit** (staging chirurgical). `feat(tableau): répartition différentiels par famille A/F/AC`

---

## Task 9 : VMC auto (1 par logement)

**Files:** `src/planrec/nfc_rules.py` (propre), `tests/test_nfc_rules_evolutions.py` (propre).

- [ ] **Step 1 : test** — append à `tests/test_nfc_rules_evolutions.py` :

```python
def test_vmc_auto_placed_cellier_then_sdb():
    dg = compute_devis_global([
        {"id": "C1", "c2_class": "Storage"},
        {"id": "S1", "c2_class": "Bath"},
    ])
    vmc_rooms = [d.room_id for d in dg.per_room
                 if d.items.get(EquipmentType.VMC, 0) >= 1]
    assert vmc_rooms == ["C1"]  # cellier prioritaire


def test_vmc_fallback_sdb_when_no_cellier():
    dg = compute_devis_global([{"id": "S1", "c2_class": "Bath"}])
    s1 = next(d for d in dg.per_room if d.room_id == "S1")
    assert s1.items.get(EquipmentType.VMC) == 1


def test_vmc_none_when_no_candidate():
    dg = compute_devis_global([{"id": "B1", "c2_class": "BedRoom"}])
    assert all(d.items.get(EquipmentType.VMC, 0) == 0 for d in dg.per_room)
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — dans `nfc_rules.py`, ajouter avant `compute_devis_global` :

```python
_VMC_FALLBACK_PRIORITY: tuple[NFCCategory, ...] = (
    NFCCategory.STORAGE, NFCCategory.BATH,
)


def _ensure_vmc(out: DevisGlobal) -> None:
    """1 VMC par logement (auto). Placement cellier → SDB ; rien sinon."""
    for d in out.per_room:
        if d.items.get(EquipmentType.VMC, 0) >= 1:
            return
    for cat in _VMC_FALLBACK_PRIORITY:
        for d in out.per_room:
            if d.nfc_category == cat:
                d.items[EquipmentType.VMC] = 1
                return
```

- [ ] **Step 4** — appeler `_ensure_vmc(out)` dans `compute_devis_global`, juste avant `_ensure_washing_machine(out)`.

- [ ] **Step 5 : run** → PASS.

- [ ] **Step 6 : commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_rules_evolutions.py
git commit -m "feat(nfc): VMC auto par logement (cellier -> SDB)"
```

---

## Task 10 : Garantie ECS + attribut attenant

**Files:** `src/planrec/nfc_rules.py` (propre), `tests/test_nfc_rules_evolutions.py` (propre).

- [ ] **Step 1 : test** :

```python
def test_ecs_in_cellier_no_change():
    dg = compute_devis_global([{"id": "C1", "c2_class": "Storage"}])
    c1 = next(d for d in dg.per_room if d.room_id == "C1")
    assert c1.items.get(EquipmentType.BOILER) == 1  # cellier garde l'ECS


def test_ecs_fallback_garage_only_if_attenant():
    dg = compute_devis_global([
        {"id": "G1", "c2_class": "Garage", "attenant": True},
        {"id": "S1", "c2_class": "Bath"},
    ])
    boiler_rooms = [d.room_id for d in dg.per_room
                    if d.items.get(EquipmentType.BOILER, 0) >= 1]
    assert boiler_rooms == ["G1"]  # garage attenant prioritaire sur SDB


def test_ecs_fallback_sdb_when_garage_not_attenant():
    dg = compute_devis_global([
        {"id": "G1", "c2_class": "Garage", "attenant": False},
        {"id": "S1", "c2_class": "Bath"},
    ])
    boiler_rooms = [d.room_id for d in dg.per_room
                    if d.items.get(EquipmentType.BOILER, 0) >= 1]
    assert boiler_rooms == ["S1"]


def test_ecs_none_when_no_candidate():
    dg = compute_devis_global([{"id": "B1", "c2_class": "BedRoom"}])
    assert all(d.items.get(EquipmentType.BOILER, 0) == 0 for d in dg.per_room)
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — `Devis` dataclass : ajouter `attenant: bool = False`.

- [ ] **Step 4** — dans `compute_devis_global`, l'appel à `compute_devis_for_room` ne porte pas `attenant` ; après création du `devis`, poser le flag depuis le dict source :

```python
        devis = compute_devis_for_room(...)
        devis.attenant = bool(r.get("attenant", False))
        out.per_room.append(devis)
```

- [ ] **Step 5** — ajouter avant `compute_devis_global` :

```python
def _ensure_ecs(out: DevisGlobal) -> None:
    """Garantit une alim ECS (cumulus) hors cellier : garage si attenant → SDB.
    (Le cellier la génère déjà via sa règle.) Rien si aucune candidate."""
    for d in out.per_room:
        if d.items.get(EquipmentType.BOILER, 0) >= 1:
            return
    for d in out.per_room:
        if d.nfc_category == NFCCategory.GARAGE and d.attenant:
            d.items[EquipmentType.BOILER] = 1
            d.special_feeds_detail.append("Cumulus (ECS)")
            return
    for d in out.per_room:
        if d.nfc_category == NFCCategory.BATH:
            d.items[EquipmentType.BOILER] = 1
            d.special_feeds_detail.append("Cumulus (ECS)")
            return
```

Appeler `_ensure_ecs(out)` dans `compute_devis_global` après `_ensure_washing_machine(out)`.

- [ ] **Step 6 : run** → PASS.

- [ ] **Step 7 : commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_rules_evolutions.py
git commit -m "feat(nfc): garantie ECS hors cellier (garage attenant -> SDB) + attribut attenant"
```

---

## Task 11 : Pastilles + palette + billing VMC/PAC/borne

**Files:** `src/planrec/nfc_equipments.py` (propre), `tests/test_nfc_equipments.py` (propre).

- [ ] **Step 1 : test** :

```python
def test_vmc_pac_ev_have_own_pastille_and_palette():
    from src.planrec.nfc_equipments import (
        EQUIP_TYPES, NFC_TO_EQUIP_TYPE, CANVAS_HIDDEN_EQUIP_KEYS,
        generate_equipments_from_devis_global,
    )
    from src.planrec.nfc_rules import EquipmentType, compute_devis_global
    for key in ("VMC", "HeatPump", "EVCharger"):
        assert key in EQUIP_TYPES
        assert key not in CANVAS_HIDDEN_EQUIP_KEYS  # visibles en palette
    assert NFC_TO_EQUIP_TYPE[EquipmentType.VMC] == "VMC"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.HEAT_PUMP] == "HeatPump"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.EV_CHARGER] == "EVCharger"
    # VMC auto → pastille propre (pas "SpecialFeed")
    dg = compute_devis_global([{"id": "S1", "c2_class": "Bath"}])
    types = {i["type"] for i in generate_equipments_from_devis_global(dg)}
    assert "VMC" in types


def test_vmc_billed_on_own_line():
    from app.streamlit_app import build_devis_lines_initial
    from src.planrec.nfc_pricing import DEFAULT_PRICES_HT
    from src.planrec.nfc_rules import compute_devis_global
    dg = compute_devis_global([{"id": "S1", "c2_class": "Bath"}])
    lines, _ = build_devis_lines_initial(dg, DEFAULT_PRICES_HT)
    assert "VMC" in {l["Équipement"] for l in lines}
```

- [ ] **Step 2 : run** → FAIL.

- [ ] **Step 3** — dans `nfc_equipments.py`, `EQUIP_TYPES` : ajouter 3 entrées (couleurs au choix cohérent, `svg_id` = `special_feed` en attendant des assets dédiés) :

```python
    "VMC":       {"label": "VMC",   "color": "rgb(120, 144, 156)", "svg_id": "special_feed"},
    "HeatPump":  {"label": "PAC",   "color": "rgb(0, 137, 123)",   "svg_id": "special_feed"},
    "EVCharger": {"label": "Borne", "color": "rgb(57, 73, 171)",   "svg_id": "special_feed"},
```

`NFC_TO_EQUIP_TYPE` : ajouter `EquipmentType.VMC: "VMC"`, `EquipmentType.HEAT_PUMP: "HeatPump"`, `EquipmentType.EV_CHARGER: "EVCharger"`.

`CANVAS_HIDDEN_EQUIP_KEYS` : inchangé (ne contient que les 6 appareils ; les 3 nouveaux restent donc visibles en palette et générés avec leur pastille propre via le `else` de `generate_equipments_from_devis_global`).

- [ ] **Step 4 : run** → PASS (le billing fonctionne déjà : VMC/PAC/EV ne sont pas dans `SPECIAL_FEED_EQUIPMENT_TYPES` → lignes propres via `EQUIPMENT_LABELS_FR`).

- [ ] **Step 5 : commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equip): pastilles + palette + billing VMC/PAC/borne"
```

---

## Task 12 : Non-régression + réconciliation

**Files:** suite complète ; `tests/test_nfc_tableau.py` (WIP) si réconciliation.

- [ ] **Step 1 : run** — `.venv/bin/pytest -m "not slow" -q`. Identifier les échecs.

- [ ] **Step 2** — échecs attendus probables : tests de flux complet `test_nfc_tableau.py` qui supposaient l'ancien modèle « 1 Type A + reste AC » (ex. comptage de DDR, ou un test affirmant que l'éclairage est sur AC) ; tests RCD comptant un nombre de DDR précis. Pour chacun : vérifier que le nouveau nombre/type correspond au spec (familles A/F/AC, éclairage en A), puis ajuster l'attendu **uniquement si conforme au spec**. Ne pas masquer une vraie régression.

- [ ] **Step 3** — pour `tests/test_nfc_tableau.py` (WIP) : réconciliations commitées en **staging chirurgical** par le contrôleur.

- [ ] **Step 4 : run** — `.venv/bin/pytest -m "not slow" -q` → vert.

- [ ] **Step 5 : commit** (staging chirurgical pour le fichier WIP, `git add` normal sinon). `test(tableau): réconciliation modèle différentiels v2`

---

## Self-Review (effectuée)

- **Spec coverage :** #1 Type A élargi (Task 3 éclairage, Task 6 VMC, Task 8 répartition) ; #2 prises 8 (Task 4) ; #3 prises cuisine 20A (Task 5) + plaque 32A inchangée (Task 6) ; #4 ECS (Task 10) ; #5 PAC + #6 borne (Task 1/6/8/11) ; Type F (Task 2/6/8) ; VMC auto (Task 9) + pastille/billing (Task 11) ; PAC calibre (Task 7) ; attenant (Task 10). Couvert.
- **Placeholders :** aucun — code complet par step.
- **Type consistency :** `requires_type_f`, `CircuitType.KITCHEN_SOCKET/VMC/HEAT_PUMP/EV_CHARGER`, `EquipmentType.VMC/HEAT_PUMP/EV_CHARGER`, clés pastille `VMC/HeatPump/EVCharger`, `Devis.attenant`, `_ensure_vmc/_ensure_ecs` — cohérents entre tâches.
- **Staging :** fichiers WIP (`nfc_tableau.py`, `test_nfc_tableau.py`) en chirurgical ; autres en `git add` explicite.
