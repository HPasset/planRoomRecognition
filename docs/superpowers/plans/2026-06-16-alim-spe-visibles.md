# Alimentations visibles (plan + devis) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre visibles sur le plan et facturées dans le devis toutes les alimentations spécialisées (6 appareils → pastille/ligne « Alim spé ») et le chauffage (convecteur/sèche-serviettes → pastille/ligne dédiées), sans toucher au tableau électrique.

**Architecture:** Les types précis restent dans `devis.items` (le tableau les lit pour calibres/DDR Type A — inchangé). On migre la *génération de pastilles* et la *construction des lignes de devis* : un nouvel ensemble `SPECIAL_FEED_EQUIPMENT_TYPES` (6 appareils) remplace progressivement `CIRCUIT_ONLY_EQUIPMENT_TYPES` (supprimé en fin de plan). Les appareils s'affichent/facturent en « Alimentation spécialisée » générique ; le chauffage récupère ses pastilles/lignes propres.

**Tech Stack:** Python 3.11, pytest, Streamlit. Invoquer via `.venv/bin/pytest`. Spec : [docs/superpowers/specs/2026-06-16-alim-spe-visibles-design.md](../specs/2026-06-16-alim-spe-visibles-design.md).

---

## File Structure

- **Modify** `src/planrec/nfc_rules.py` — ajouter `SPECIAL_FEED_EQUIPMENT_TYPES` ; réduire `SOCKET` cuisine 9→6 ; supprimer `CIRCUIT_ONLY_EQUIPMENT_TYPES` (Task 5).
- **Modify** `src/planrec/nfc_equipments.py` — réduire `CANVAS_HIDDEN_EQUIP_KEYS` aux 6 appareils ; générer les appareils en pastille `SpecialFeed`, le chauffage en pastille propre.
- **Modify** `app/streamlit_app.py` — `build_devis_lines_initial` : agrège les 6 appareils en 1 ligne « Alimentation spécialisée » par pièce, plus de filtrage circuit-only.
- **Modify** `app/pages/0_📋_Devis.py` — `_devis_global_montant_ht` : prix appareils = prix `SPECIAL_FEED`, plus de filtrage.
- **Modify** tests : `tests/test_nfc_equipments.py`, `tests/test_nfc_rules_evolutions.py`, `tests/test_devis_apptest.py` (réconciliations).

**⚠ Staging git :** `tests/test_devis_apptest.py`, `tests/test_nfc_tableau.py`, `tests/test_tableau_renderer.py`, `src/planrec/nfc_tableau.py`, `src/planrec/tableau_renderer.py` contiennent du **WIP utilisateur non-commité**. NE JAMAIS faire `git add -A`. Stager explicitement les fichiers de chaque tâche. Pour `tests/test_devis_apptest.py` (Task 6), voir la procédure de staging chirurgical.

---

## Task 1: Définir SPECIAL_FEED_EQUIPMENT_TYPES

**Files:**
- Modify: `src/planrec/nfc_rules.py` (après `CIRCUIT_ONLY_EQUIPMENT_TYPES`, ~ligne 64)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write the failing test** — Ajouter à la fin de `tests/test_nfc_equipments.py` :

```python
def test_special_feed_equipment_types_are_the_six_appliances():
    """SPECIAL_FEED_EQUIPMENT_TYPES = les 6 appareils à alim dédiée (affichés/
    facturés en « Alim spé »). Le chauffage (Convecteur/Sèche-serv) en est exclu."""
    from src.planrec.nfc_rules import SPECIAL_FEED_EQUIPMENT_TYPES, EquipmentType
    assert SPECIAL_FEED_EQUIPMENT_TYPES == frozenset({
        EquipmentType.OVEN, EquipmentType.COOKTOP, EquipmentType.DISHWASHER,
        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER, EquipmentType.BOILER,
    })
    assert EquipmentType.CONVECTOR not in SPECIAL_FEED_EQUIPMENT_TYPES
    assert EquipmentType.TOWEL_WARMER not in SPECIAL_FEED_EQUIPMENT_TYPES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_special_feed_equipment_types_are_the_six_appliances -v`
Expected: FAIL (ImportError: cannot import name 'SPECIAL_FEED_EQUIPMENT_TYPES').

- [ ] **Step 3: Add the frozenset** — Dans `src/planrec/nfc_rules.py`, juste après la définition de `CIRCUIT_ONLY_EQUIPMENT_TYPES` (qui se termine ligne ~64), ajouter :

```python
# Appareils à alimentation dédiée fournis par l'occupant : l'artisan pose
# l'alimentation (prise/circuit), facturée et affichée comme « Alim spé »
# générique. Distinct du chauffage (Convecteur/Sèche-serviettes), qui a ses
# propres pastilles/lignes. Cf. retour métier 2026-06-16.
SPECIAL_FEED_EQUIPMENT_TYPES: frozenset[EquipmentType] = frozenset({
    EquipmentType.OVEN,
    EquipmentType.COOKTOP,
    EquipmentType.DISHWASHER,
    EquipmentType.WASHING_MACHINE,
    EquipmentType.DRYER,
    EquipmentType.BOILER,
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_special_feed_equipment_types_are_the_six_appliances -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): ajoute SPECIAL_FEED_EQUIPMENT_TYPES (6 appareils alim spé)"
```

---

## Task 2: Cuisine SOCKET 9 → 6

**Files:**
- Modify: `src/planrec/nfc_rules.py` (bloc `KITCHEN` de `compute_devis_for_room`)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write the failing test** — Ajouter à `tests/test_nfc_equipments.py` :

```python
def test_kitchen_socket_count_is_six():
    """Cuisine : 6 prises normales (les 3 alim spé sont des circuits typés
    séparés, plus fondues dans le compteur de prises)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("k1", "Kitchen")
    assert devis.items.get(EquipmentType.SOCKET) == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_kitchen_socket_count_is_six -v`
Expected: FAIL (obtient 9).

- [ ] **Step 3: Reduce the socket count** — Dans le bloc `elif nfc_cat == NFCCategory.KITCHEN:` de `compute_devis_for_room`, remplacer :

```python
        devis.items[EquipmentType.SOCKET] = 9
```

par :

```python
        devis.items[EquipmentType.SOCKET] = 6
```

Puis remplacer la note existante :

```python
        devis.notes.append(
            "9 prises au total : 6 prises normales (dont 4 au-dessus plan "
            "de travail) + 3 alimentations spécialisées (Plaque/Four/LV)"
        )
```

par :

```python
        devis.notes.append(
            "6 prises normales (dont 4 au-dessus plan de travail) + 3 "
            "alimentations spécialisées (Plaque/Four/LV) affichées séparément"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_kitchen_socket_count_is_six -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): cuisine 6 prises normales (3 alim spé désormais affichées à part)"
```

---

## Task 3: Génération des pastilles (appareils → Alim spé, chauffage → propre)

**Files:**
- Modify: `src/planrec/nfc_equipments.py` (`CANVAS_HIDDEN_EQUIP_KEYS` ~ligne 76 ; import ~ligne 15 ; `generate_equipments_from_devis_global` ~ligne 113)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write the failing tests** — Ajouter à `tests/test_nfc_equipments.py` :

```python
def test_kitchen_pastilles_six_sockets_three_special_feeds():
    """Cuisine sur le plan : 6 Prise + 3 SpecialFeed (Four/Plaque/LV génériques),
    aucune pastille typée."""
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([{"id": "k1", "c2_class": "Kitchen"}])
    instances = generate_equipments_from_devis_global(devis)
    counts: dict[str, int] = {}
    for inst in instances:
        counts[inst["type"]] = counts.get(inst["type"], 0) + 1
    assert counts.get("Prise", 0) == 6
    assert counts.get("SpecialFeed", 0) == 3
    assert counts.get("Oven", 0) == 0
    assert counts.get("Cooktop", 0) == 0
    assert counts.get("Dishwasher", 0) == 0


def test_storage_pastilles_three_special_feeds():
    """Cellier : LL+SL+Cumulus → 3 pastilles SpecialFeed."""
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([{"id": "c1", "c2_class": "Storage"}])
    instances = generate_equipments_from_devis_global(devis)
    counts: dict[str, int] = {}
    for inst in instances:
        counts[inst["type"]] = counts.get(inst["type"], 0) + 1
    assert counts.get("SpecialFeed", 0) == 3


def test_heating_pastilles_use_own_type_not_special_feed():
    """Convecteur et sèche-serviettes gardent leur pastille propre."""
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 45.0},  # 3 convecteurs
        {"id": "S1", "c2_class": "Bath"},                            # 1 sèche-serv
    ], heating_enabled=True)
    instances = generate_equipments_from_devis_global(devis)
    counts: dict[str, int] = {}
    for inst in instances:
        counts[inst["type"]] = counts.get(inst["type"], 0) + 1
    assert counts.get("Convector", 0) == 3
    assert counts.get("TowelWarmer", 0) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py -k "pastilles_six_sockets or pastilles_three_special or heating_pastilles_use_own" -v`
Expected: FAIL (appareils masqués → 0 SpecialFeed ; convecteur masqué → 0 Convector).

- [ ] **Step 3: Import the new set** — Dans `src/planrec/nfc_equipments.py`, remplacer la ligne 15 :

```python
from src.planrec.nfc_rules import EquipmentType, DevisGlobal
```

par :

```python
from src.planrec.nfc_rules import (
    EquipmentType,
    DevisGlobal,
    SPECIAL_FEED_EQUIPMENT_TYPES,
)
```

- [ ] **Step 4: Reduce CANVAS_HIDDEN_EQUIP_KEYS** — Remplacer la définition (lignes ~76-79) :

```python
CANVAS_HIDDEN_EQUIP_KEYS: frozenset[str] = frozenset({
    "Oven", "Cooktop", "Dishwasher", "WashingMachine",
    "Dryer", "Boiler", "Convector", "TowelWarmer",
})
```

par :

```python
# Clés masquées de la PALETTE manuelle (drag-drop) : les 6 appareils, qui sont
# représentés par la pastille générique « Alim spé » (SpecialFeed), pas par des
# boutons typés. Convecteur/Sèche-serviettes en sont sortis → disponibles en
# palette et générés avec leur pastille propre. Cf. retour métier 2026-06-16.
CANVAS_HIDDEN_EQUIP_KEYS: frozenset[str] = frozenset({
    "Oven", "Cooktop", "Dishwasher", "WashingMachine", "Dryer", "Boiler",
})
```

- [ ] **Step 5: Update the generation loop** — Dans `generate_equipments_from_devis_global`, remplacer le corps de la boucle (lignes ~113-130) :

```python
        for nfc_type, qty in room_devis.items.items():
            equip_key = NFC_TO_EQUIP_TYPE[nfc_type]
            # Skip les types masqués (Four/Plaque/LV/LL/SL/Chaudière/Conv/SS) :
            # ils restent dans devis.items (donc dans le tableau électrique)
            # mais pas comme pastilles sur le plan.
            if equip_key in CANVAS_HIDDEN_EQUIP_KEYS:
                continue
            color = EQUIP_TYPES[equip_key]["color"]
            for _ in range(qty):
                instances.append({
                    "id": generate_equipment_id(),
                    "type": equip_key,
                    "room": room_label,
                    "x": 0,
                    "y": 0,
                    "color": color,
                    "uncertain": False,
                })
```

par :

```python
        for nfc_type, qty in room_devis.items.items():
            if qty <= 0:
                continue
            # Les 6 appareils à alim dédiée → pastille générique « Alim spé ».
            # Le reste (dont Convecteur/Sèche-serviettes) → sa pastille propre.
            if nfc_type in SPECIAL_FEED_EQUIPMENT_TYPES:
                equip_key = "SpecialFeed"
            else:
                equip_key = NFC_TO_EQUIP_TYPE[nfc_type]
                if equip_key in CANVAS_HIDDEN_EQUIP_KEYS:
                    continue
            color = EQUIP_TYPES[equip_key]["color"]
            for _ in range(qty):
                instances.append({
                    "id": generate_equipment_id(),
                    "type": equip_key,
                    "room": room_label,
                    "x": 0,
                    "y": 0,
                    "color": color,
                    "uncertain": False,
                })
```

- [ ] **Step 6: Reconcile the two existing tests that encode the old hidden behavior.**

In `tests/test_nfc_equipments.py`, replace `test_generate_equipments_kitchen_qty_explodes` (the `assert type_counts.get("Prise", 0) == 9` and `assert type_counts.get("SpecialFeed", 0) == 0` block) with the updated body — find the function and replace its assertions:

```python
    # Pastilles visibles : 6 prises + 3 Alim spé + 1 lum + 1 interrupteur
    assert type_counts.get("Prise", 0) == 6
    assert type_counts.get("SpecialFeed", 0) == 3
    assert type_counts.get("LightPoint", 0) >= 1
    assert type_counts.get("Switch", 0) >= 1
    # Sous-types typés jamais émis comme pastilles (rendus en SpecialFeed)
    assert type_counts.get("Oven", 0) == 0
    assert type_counts.get("Cooktop", 0) == 0
    assert type_counts.get("Dishwasher", 0) == 0
    # Les sous-types restent dans le devis lui-même (pour le tableau)
    from src.planrec.nfc_rules import EquipmentType
    cuisine_items = devis.per_room[0].items
    assert cuisine_items.get(EquipmentType.OVEN) == 1
    assert cuisine_items.get(EquipmentType.COOKTOP) == 1
    assert cuisine_items.get(EquipmentType.DISHWASHER) == 1
```

Then replace `test_canvas_hidden_equip_keys_contains_all_v12_subtypes` entirely with:

```python
def test_canvas_hidden_equip_keys_are_the_six_appliances():
    """CANVAS_HIDDEN_EQUIP_KEYS masque de la palette les 6 appareils (rendus en
    « Alim spé »). Convecteur/Sèche-serviettes en sont sortis (palette + pastille
    propre). Les 5 types legacy restent visibles."""
    from src.planrec.nfc_equipments import CANVAS_HIDDEN_EQUIP_KEYS

    assert CANVAS_HIDDEN_EQUIP_KEYS == {
        "Oven", "Cooktop", "Dishwasher", "WashingMachine", "Dryer", "Boiler",
    }
    assert "Convector" not in CANVAS_HIDDEN_EQUIP_KEYS
    assert "TowelWarmer" not in CANVAS_HIDDEN_EQUIP_KEYS
    visible_legacy = {"Prise", "RJ45", "LightPoint", "Switch", "SpecialFeed"}
    assert visible_legacy.isdisjoint(CANVAS_HIDDEN_EQUIP_KEYS)
```

- [ ] **Step 7: Run the equipments test module**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py -v`
Expected: PASS (les nouveaux + réconciliés ; `test_kitchen_generates_typed_special_feeds`, `test_storage_*`, `test_bath_*` restent verts car `devis.items` est inchangé).

- [ ] **Step 8: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equip): appareils en pastille Alim spé, chauffage en pastille propre"
```

---

## Task 4: Facturation — agrégation Alim spé + chauffage facturé

**Files:**
- Modify: `app/streamlit_app.py` (import ligne 43 ; `build_devis_lines_initial` lignes ~292-309)
- Modify: `app/pages/0_📋_Devis.py` (import ligne 27 ; `_devis_global_montant_ht` lignes ~49-56)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write the failing test** — Remplacer entièrement `test_build_devis_lines_initial_filters_circuit_only_types` dans `tests/test_nfc_equipments.py` par :

```python
def test_build_devis_lines_appliances_aggregated_heating_billed():
    """Les 6 appareils → 1 ligne « Alimentation spécialisée » agrégée par pièce
    au prix SPECIAL_FEED ; le chauffage est facturé sur sa propre ligne ;
    plus aucun équipement n'est exclu (pas de trou)."""
    from app.streamlit_app import build_devis_lines_initial
    from src.planrec.nfc_pricing import DEFAULT_PRICES_HT
    from src.planrec.nfc_rules import compute_devis_global, EquipmentType

    rooms = [
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "C1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    lines, _ = build_devis_lines_initial(devis, DEFAULT_PRICES_HT)

    # Cuisine : 1 ligne Alim spé agrégée Qté 3 au prix SPECIAL_FEED
    kitchen_sf = [l for l in lines
                  if l["Pièce"] == "Cuisine"
                  and l["Équipement"] == "Alimentation spécialisée"]
    assert len(kitchen_sf) == 1
    assert kitchen_sf[0]["Qté"] == 3
    assert kitchen_sf[0]["Prix HT (€)"] == DEFAULT_PRICES_HT[EquipmentType.SPECIAL_FEED]

    labels = {l["Équipement"] for l in lines}
    # Plus de lignes typées appareil
    assert "Four" not in labels
    assert "Lave-linge" not in labels
    # Chauffage désormais facturé sur sa propre ligne
    assert "Convecteur" in labels
    assert "Sèche-serviettes" in labels
    # Artisan conservés
    assert "Prise de courant" in labels
    assert "Point lumineux" in labels
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_build_devis_lines_appliances_aggregated_heating_billed -v`
Expected: FAIL (appareils/chauffage filtrés ; pas de ligne agrégée).

- [ ] **Step 3: Update the streamlit_app import** — Remplacer `app/streamlit_app.py` ligne 43 :

```python
from src.planrec.nfc_rules import CIRCUIT_ONLY_EQUIPMENT_TYPES, compute_devis_global
```

par :

```python
from src.planrec.nfc_rules import (
    SPECIAL_FEED_EQUIPMENT_TYPES,
    EquipmentType,
    compute_devis_global,
)
```

- [ ] **Step 4: Rewrite the line-building loop** — Dans `build_devis_lines_initial`, remplacer la boucle interne (lignes ~292-309) :

```python
        for eq, qty in d.items.items():
            if qty <= 0:
                continue
            # Électroménager / chauffage (Four, Plaque, LV, LL, SL, Chaudière,
            # Convecteur, Sèche-serviettes) : circuit-only — présents dans le
            # tableau électrique mais hors devis facturable (fournis par l'occupant).
            if eq in CIRCUIT_ONLY_EQUIPMENT_TYPES:
                continue
            lines.append({
                "_id": next_id,
                "Pièce": room_label,
                "Équipement": EQUIPMENT_LABELS_FR[eq],
                "Qté": int(qty),
                "Prix HT (€)": float(prices_ht.get(eq, 0.0)),
                "_manual": False,  # généré par le moteur NFC (vs ajout manuel)
                "_equip_ids": [],  # IDs équipements drag-droppés (Phase 4+)
            })
            next_id += 1
```

par :

```python
        special_feed_qty = 0
        for eq, qty in d.items.items():
            if qty <= 0:
                continue
            # Les 6 appareils → agrégés en une seule ligne « Alim spé » par pièce.
            if eq in SPECIAL_FEED_EQUIPMENT_TYPES:
                special_feed_qty += int(qty)
                continue
            lines.append({
                "_id": next_id,
                "Pièce": room_label,
                "Équipement": EQUIPMENT_LABELS_FR[eq],
                "Qté": int(qty),
                "Prix HT (€)": float(prices_ht.get(eq, 0.0)),
                "_manual": False,  # généré par le moteur NFC (vs ajout manuel)
                "_equip_ids": [],  # IDs équipements drag-droppés (Phase 4+)
            })
            next_id += 1
        if special_feed_qty > 0:
            lines.append({
                "_id": next_id,
                "Pièce": room_label,
                "Équipement": EQUIPMENT_LABELS_FR[EquipmentType.SPECIAL_FEED],
                "Qté": special_feed_qty,
                "Prix HT (€)": float(prices_ht.get(EquipmentType.SPECIAL_FEED, 0.0)),
                "_manual": False,
                "_equip_ids": [],
            })
            next_id += 1
```

- [ ] **Step 5: Update the Devis page total** — Remplacer `app/pages/0_📋_Devis.py` ligne 27 :

```python
from src.planrec.nfc_rules import CIRCUIT_ONLY_EQUIPMENT_TYPES, DevisGlobal
```

par :

```python
from src.planrec.nfc_rules import (
    SPECIAL_FEED_EQUIPMENT_TYPES,
    EquipmentType,
    DevisGlobal,
)
```

Puis remplacer le corps de `_devis_global_montant_ht` (lignes ~49-56) :

```python
    total = Decimal("0")
    for room in devis_global.per_room:
        for eq_type, qty in room.items.items():
            if eq_type in CIRCUIT_ONLY_EQUIPMENT_TYPES:
                continue
            price = DEFAULT_PRICES_HT.get(eq_type, 0.0)
            total += Decimal(str(price)) * Decimal(qty)
    return total.quantize(Decimal("0.01"))
```

par :

```python
    total = Decimal("0")
    for room in devis_global.per_room:
        for eq_type, qty in room.items.items():
            # Les 6 appareils sont facturés au prix « Alim spé » générique
            # (cohérent avec build_devis_lines_initial). Plus aucun type exclu.
            if eq_type in SPECIAL_FEED_EQUIPMENT_TYPES:
                price = DEFAULT_PRICES_HT[EquipmentType.SPECIAL_FEED]
            else:
                price = DEFAULT_PRICES_HT.get(eq_type, 0.0)
            total += Decimal(str(price)) * Decimal(qty)
    return total.quantize(Decimal("0.01"))
```

Mettre aussi à jour le docstring de la fonction (lignes ~41-48) : remplacer la mention d'exclusion par « Facture tous les équipements ; les 6 appareils au prix Alim spé générique. »

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py::test_build_devis_lines_appliances_aggregated_heating_billed -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/streamlit_app.py "app/pages/0_📋_Devis.py" tests/test_nfc_equipments.py
git commit -m "feat(devis): appareils agrégés en Alim spé, chauffage facturé (plus de trou)"
```

---

## Task 5: Supprimer CIRCUIT_ONLY_EQUIPMENT_TYPES + réconcilier les tests restants

**Files:**
- Modify: `src/planrec/nfc_rules.py` (suppression du frozenset, lignes ~52-64)
- Test: `tests/test_nfc_equipments.py`, `tests/test_nfc_rules_evolutions.py`

- [ ] **Step 1: Find every remaining reference**

Run: `grep -rn "CIRCUIT_ONLY_EQUIPMENT_TYPES" src/ app/ tests/`
Expected restant après Tasks 3-4 : la définition dans `nfc_rules.py`, et 3 tests : `test_circuit_only_equipment_types_contains_oven_cooktop_convector`, `test_circuit_only_excludes_billable_artisan_equipment` (dans `test_nfc_equipments.py`), `test_lave_linge_synthetique_est_circuit_only` (dans `test_nfc_rules_evolutions.py`). Si d'autres apparaissent, les traiter de la même façon (migrer vers `SPECIAL_FEED_EQUIPMENT_TYPES` ou supprimer).

- [ ] **Step 2: Replace the two circuit-only tests** — Dans `tests/test_nfc_equipments.py`, remplacer `test_circuit_only_equipment_types_contains_oven_cooktop_convector` ET `test_circuit_only_excludes_billable_artisan_equipment` par une seule fonction :

```python
def test_special_feed_set_holds_appliances_not_heating_nor_artisan():
    """SPECIAL_FEED_EQUIPMENT_TYPES = les 6 appareils. Le chauffage et les
    équipements posés par l'artisan en sont exclus."""
    from src.planrec.nfc_rules import SPECIAL_FEED_EQUIPMENT_TYPES, EquipmentType
    for appliance in (
        EquipmentType.OVEN, EquipmentType.COOKTOP, EquipmentType.DISHWASHER,
        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER, EquipmentType.BOILER,
    ):
        assert appliance in SPECIAL_FEED_EQUIPMENT_TYPES
    for excluded in (
        EquipmentType.CONVECTOR, EquipmentType.TOWEL_WARMER,
        EquipmentType.SOCKET, EquipmentType.LIGHT_POINT,
        EquipmentType.SWITCH, EquipmentType.RJ45,
    ):
        assert excluded not in SPECIAL_FEED_EQUIPMENT_TYPES
```

- [ ] **Step 3: Reconcile the synthetic laundry test** — Dans `tests/test_nfc_rules_evolutions.py`, remplacer `test_lave_linge_synthetique_est_circuit_only` par :

```python
def test_lave_linge_synthetique_est_facture_en_alim_spe():
    """Le Devis synthétique ne porte que des appareils « Alim spé » → il produit
    une ligne facturable « Alimentation spécialisée », plus aucun trou."""
    from src.planrec.nfc_rules import SPECIAL_FEED_EQUIPMENT_TYPES
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    virtual = next(d for d in dg.per_room if d.room_id == "__laundry_virtual__")
    assert virtual.items  # non vide
    assert all(eq in SPECIAL_FEED_EQUIPMENT_TYPES for eq in virtual.items)
```

Puis, en tête de `tests/test_nfc_rules_evolutions.py`, remplacer l'import :

```python
from src.planrec.nfc_rules import (
    CIRCUIT_ONLY_EQUIPMENT_TYPES,
    EquipmentType,
    NFCCategory,
    compute_devis_global,
)
```

par :

```python
from src.planrec.nfc_rules import (
    SPECIAL_FEED_EQUIPMENT_TYPES,
    EquipmentType,
    NFCCategory,
    compute_devis_global,
)
```

- [ ] **Step 4: Delete the frozenset** — Dans `src/planrec/nfc_rules.py`, supprimer entièrement la définition de `CIRCUIT_ONLY_EQUIPMENT_TYPES` (le commentaire lignes ~52-54 + le `frozenset({...})` lignes ~55-64).

- [ ] **Step 5: Verify no references remain**

Run: `grep -rn "CIRCUIT_ONLY_EQUIPMENT_TYPES" src/ app/ tests/`
Expected: aucun résultat.

- [ ] **Step 6: Run the affected modules**

Run: `.venv/bin/pytest tests/test_nfc_equipments.py tests/test_nfc_rules_evolutions.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py tests/test_nfc_rules_evolutions.py
git commit -m "refactor(nfc): supprime CIRCUIT_ONLY_EQUIPMENT_TYPES (tout est désormais facturé)"
```

---

## Task 6: Non-régression complète + réconciliation test_devis_apptest.py

**Files:**
- Modify (peut-être) : `tests/test_devis_apptest.py` (**WIP utilisateur — staging chirurgical**)

- [ ] **Step 1: Run the full fast suite**

Run: `.venv/bin/pytest -m "not slow" -q`
Expected: au plus 1 échec attendu — `tests/test_devis_apptest.py` (assertion `"Alimentation spécialisée" not in equipements` pour la cuisine, ~ligne 816, qui encode l'ancien comportement). Tout le reste vert, y compris `tests/test_nfc_tableau.py` (tableau inchangé).

- [ ] **Step 2: Inspect the failing assertion** — Ouvrir `tests/test_devis_apptest.py` autour de la ligne 806-816. Le test affirme que la cuisine n'a que prises/point lumineux/interrupteur et `"Alimentation spécialisée" not in equipements`. Avec le nouveau comportement, la cuisine DOIT contenir « Alimentation spécialisée » (Qté 3). Inverser l'assertion : remplacer

```python
    assert "Alimentation spécialisée" not in equipements
```

par

```python
    assert "Alimentation spécialisée" in equipements
```

et adapter le commentaire/docstring voisin (« Cuisine NFC = 6 prises + 3 alim spé + point lumineux + interrupteur »). Si d'autres assertions du même test encodent l'absence d'alim spé ou le compte de 9 prises, les ajuster au nouveau comportement (6 prises + 1 ligne Alim spé Qté 3). NE PAS masquer une vraie régression — vérifier que chaque écart correspond au spec.

- [ ] **Step 3: Re-run that test file**

Run: `.venv/bin/pytest tests/test_devis_apptest.py -q`
Expected: PASS.

- [ ] **Step 4: Commit — staging chirurgical (le fichier contient du WIP utilisateur)**

Le fichier `tests/test_devis_apptest.py` a des modifications WIP non-commitées de l'utilisateur, antérieures à cette tâche. Pour ne committer QUE la réconciliation de ce test sans embarquer le WIP, demander au contrôleur (session principale) de réaliser le staging chirurgical via `git hash-object` + `git update-index --cacheinfo` (même technique que pour les commits précédents de cette branche). NE PAS faire `git add tests/test_devis_apptest.py` directement.

> Note pour le contrôleur : construire la version `HEAD:tests/test_devis_apptest.py` + la seule réconciliation (assertion inversée), la placer dans l'index via cacheinfo, committer `test(devis): cuisine attend désormais une ligne Alim spé`, puis vérifier que le WIP utilisateur reste non-commité (`git diff --stat -- tests/test_devis_apptest.py`).

- [ ] **Step 5: Final full run**

Run: `.venv/bin/pytest -m "not slow" -q`
Expected: tout vert (0 échec).

---

## Self-Review (effectuée)

- **Spec coverage :** SPECIAL_FEED_EQUIPMENT_TYPES (Task 1) ; cuisine 9→6 (Task 2) ; pastilles appareils→Alim spé + chauffage propre (Task 3) ; facturation agrégée + chauffage facturé + total cohérent (Task 4) ; suppression CIRCUIT_ONLY + réconciliations (Task 5) ; lave-linge garanti facturé en Alim spé (couvert Tasks 3-5, test Task 5 step 3) ; tableau inchangé (Task 6 step 1). Couvert.
- **Placeholders :** aucun — chaque step montre le code complet et la commande exacte.
- **Type consistency :** `SPECIAL_FEED_EQUIPMENT_TYPES`, `EquipmentType.SPECIAL_FEED`, `EQUIPMENT_LABELS_FR[...]` (= "Alimentation spécialisée"), clé pastille `"SpecialFeed"`, `CANVAS_HIDDEN_EQUIP_KEYS` (6 appareils) — cohérents entre tâches et conformes au code lu.
- **Staging :** chaque commit stage des fichiers explicites ; `test_devis_apptest.py` traité en chirurgical (WIP utilisateur).
