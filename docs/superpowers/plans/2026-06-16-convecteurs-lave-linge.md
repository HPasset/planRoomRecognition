# Convecteurs + garantie lave-linge — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Faire évoluer les règles NFC du devis pour (1) garantir au moins un lave-linge 20A par logement et (2) compter les convecteurs par surface avec un forfait de repli par type de pièce.

**Architecture:** Tout vit dans la couche règles `src/planrec/nfc_rules.py`. Le comptage convecteurs passe par un helper `_convector_count` appelé dans `compute_devis_for_room`. La garantie lave-linge est un post-traitement logement `_ensure_washing_machine` appelé en fin de `compute_devis_global` (seul niveau ayant la visibilité sur toutes les pièces). Aucune modification du tableau électrique : il lit déjà `WASHING_MACHINE`/`CONVECTOR` depuis `devis.items` par pièce.

**Tech Stack:** Python 3.11, pytest. Invoquer via `.venv/bin/pytest`. Spec : [docs/superpowers/specs/2026-06-16-convecteurs-lave-linge-design.md](../specs/2026-06-16-convecteurs-lave-linge-design.md).

---

## File Structure

- **Modify** `src/planrec/nfc_rules.py`
  - Ajout `import math` en tête.
  - Nouveau helper `_convector_count(nfc_cat, surface_m2) -> int`.
  - Remplacement du forfait `CONVECTOR = 1` (lignes 230-232) par appel au helper.
  - Correction libellé cellier « Lave-linge (16A) » → « Lave-linge (20A) » (ligne 179).
  - Nouvelle constante `_WASHING_FALLBACK_PRIORITY` + helper `_ensure_washing_machine(out)`.
  - Appel de `_ensure_washing_machine(out)` avant le `return out` de `compute_devis_global` (ligne 314).
- **Create** `tests/test_nfc_rules_evolutions.py` — tests des deux évolutions + intégration tableau.

---

## Task 1: Comptage des convecteurs par surface

**Files:**
- Modify: `src/planrec/nfc_rules.py` (import `math`, helper `_convector_count`, lignes 230-232)
- Test: `tests/test_nfc_rules_evolutions.py`

- [ ] **Step 1: Write the failing tests**

Créer `tests/test_nfc_rules_evolutions.py` :

```python
from __future__ import annotations

from src.planrec.nfc_rules import (
    EquipmentType,
    NFCCategory,
    compute_devis_global,
)


def _conv(devis_global, room_id):
    """Nb de convecteurs d'une pièce donnée du DevisGlobal."""
    for d in devis_global.per_room:
        if d.room_id == room_id:
            return d.items.get(EquipmentType.CONVECTOR, 0)
    raise AssertionError(f"room {room_id} absente")


def test_convecteur_sejour_surface_45_donne_3():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 45.0},
    ])
    assert _conv(dg, "L1") == 3


def test_convecteur_chambre_11m2_donne_1():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom", "surface_m2": 11.0},
    ])
    assert _conv(dg, "B1") == 1


def test_convecteur_sejour_sans_surface_forfait_2():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom"},
    ])
    assert _conv(dg, "L1") == 2


def test_convecteur_chambre_sans_surface_forfait_1():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    assert _conv(dg, "B1") == 1


def test_convecteur_chauffage_desactive_zero():
    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 45.0},
    ], heating_enabled=False)
    assert _conv(dg, "L1") == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py -v`
Expected: les tests `surface_45` (obtient 1) et `sejour_sans_surface` (obtient 1) ÉCHOUENT. Les autres peuvent passer par coïncidence.

- [ ] **Step 3: Add `import math`**

Dans `src/planrec/nfc_rules.py`, après la ligne `from enum import Enum` (ligne 16) :

```python
import math
```

- [ ] **Step 4: Add the `_convector_count` helper**

Insérer cette fonction juste avant `def compute_devis_for_room(` (avant la ligne 98) :

```python
def _convector_count(nfc_cat: NFCCategory, surface_m2: float | None) -> int:
    """Nombre de convecteurs pour une pièce chauffée.

    Surface connue → 1 convecteur / 20 m² (≈ 100 W/m², convecteur ~2000 W).
    Surface inconnue → forfait par type : séjour 2, chambre 1.
    """
    if surface_m2 is not None and surface_m2 > 0:
        return max(1, math.ceil(surface_m2 / 20))
    return 2 if nfc_cat == NFCCategory.LIVINGROOM else 1
```

- [ ] **Step 5: Wire the helper into the room rule**

Dans `compute_devis_for_room`, remplacer le bloc (lignes 230-232) :

```python
    # Auto-génération chauffage électrique pour pièces principales (V1.2)
    if heating_enabled and nfc_cat in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM):
        devis.items[EquipmentType.CONVECTOR] = 1
```

par :

```python
    # Auto-génération chauffage électrique pour pièces principales (V1.2)
    if heating_enabled and nfc_cat in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM):
        devis.items[EquipmentType.CONVECTOR] = _convector_count(nfc_cat, surface_m2)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py -v`
Expected: les 5 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_rules_evolutions.py
git commit -m "feat(nfc): comptage convecteurs par surface + forfait de repli par type"
```

---

## Task 2: Garantie « au moins 1 lave-linge par logement »

**Files:**
- Modify: `src/planrec/nfc_rules.py` (constante + helper `_ensure_washing_machine`, appel dans `compute_devis_global`)
- Test: `tests/test_nfc_rules_evolutions.py`

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `tests/test_nfc_rules_evolutions.py` :

```python
def _ll_rooms(devis_global):
    """(room_id, nfc_category) des pièces portant un lave-linge."""
    return [
        (d.room_id, d.nfc_category)
        for d in devis_global.per_room
        if d.items.get(EquipmentType.WASHING_MACHINE, 0) >= 1
    ]


def test_lave_linge_cellier_pas_de_doublon():
    dg = compute_devis_global([
        {"id": "C1", "c2_class": "Storage"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "K1", "c2_class": "Kitchen"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "C1"  # rattaché au cellier existant


def test_lave_linge_repli_sur_sdb_si_pas_de_cellier():
    dg = compute_devis_global([
        {"id": "S1", "c2_class": "Bath"},
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0] == ("S1", NFCCategory.BATH)


def test_lave_linge_priorite_sdb_avant_cuisine():
    dg = compute_devis_global([
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "S1"  # SDB prioritaire sur cuisine


def test_lave_linge_circuit_only_si_aucune_piece_candidate():
    dg = compute_devis_global([
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
    ])
    ll = _ll_rooms(dg)
    assert len(ll) == 1
    assert ll[0][0] == "__laundry_virtual__"
    assert ll[0][1] == NFCCategory.STORAGE


def test_lave_linge_label_20A_sur_repli():
    dg = compute_devis_global([
        {"id": "S1", "c2_class": "Bath"},
    ])
    sdb = next(d for d in dg.per_room if d.room_id == "S1")
    assert "Lave-linge (20A)" in sdb.special_feeds_detail
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py -k lave_linge -v`
Expected: `repli_sur_sdb`, `priorite_sdb`, `circuit_only`, `label_20A` ÉCHOUENT (aucun lave-linge généré sans cellier).

- [ ] **Step 3: Add the priority constant and the helper**

Insérer juste avant `def compute_devis_global(` (avant la ligne 283) :

```python
# Ordre de repli pour rattacher le lave-linge garanti quand aucun cellier
# n'est détecté. STORAGE absent volontairement : s'il existe, il porte déjà
# un lave-linge → garantie satisfaite avant d'arriver ici.
_WASHING_FALLBACK_PRIORITY: tuple[NFCCategory, ...] = (
    NFCCategory.BATH,
    NFCCategory.KITCHEN,
    NFCCategory.GARAGE,
    NFCCategory.ENTRY,
)


def _ensure_washing_machine(out: DevisGlobal) -> None:
    """Garantit au moins un lave-linge 20A par logement (retour métier 2026-06-16).

    - Si une pièce porte déjà un lave-linge (cellier détecté) → ne rien faire.
    - Sinon → rattacher 1 lave-linge à la première pièce de repli trouvée
      selon `_WASHING_FALLBACK_PRIORITY`.
    - Si aucune pièce candidate → Devis synthétique circuit-only
      (`__laundry_virtual__`, pas de polygone → pas de pastille sur le plan,
      mais le circuit LAUNDRY Type A apparaît dans le tableau).
    """
    for d in out.per_room:
        if d.items.get(EquipmentType.WASHING_MACHINE, 0) >= 1:
            return  # garantie déjà satisfaite, pas de doublon

    for cat in _WASHING_FALLBACK_PRIORITY:
        for d in out.per_room:
            if d.nfc_category == cat:
                d.items[EquipmentType.WASHING_MACHINE] = 1
                d.special_feeds_detail.append("Lave-linge (20A)")
                return

    out.per_room.append(Devis(
        room_id="__laundry_virtual__",
        nfc_category=NFCCategory.STORAGE,
        surface_m2=None,
        handicap=out.handicap,
        items={EquipmentType.WASHING_MACHINE: 1},
        special_feeds_detail=["Lave-linge (20A)"],
    ))
```

- [ ] **Step 4: Call the helper in `compute_devis_global`**

Remplacer la fin de `compute_devis_global` (lignes 313-314) :

```python
        out.per_room.append(devis)
    return out
```

par :

```python
        out.per_room.append(devis)
    _ensure_washing_machine(out)
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py -k lave_linge -v`
Expected: les 5 tests lave-linge PASS.

- [ ] **Step 6: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_rules_evolutions.py
git commit -m "feat(nfc): garantie d'au moins un lave-linge 20A par logement"
```

---

## Task 3: Cohérence du libellé cellier (16A → 20A)

**Files:**
- Modify: `src/planrec/nfc_rules.py:179`
- Test: `tests/test_nfc_rules_evolutions.py`

- [ ] **Step 1: Write the failing test**

Ajouter à `tests/test_nfc_rules_evolutions.py` :

```python
def test_cellier_lave_linge_label_20A():
    dg = compute_devis_global([
        {"id": "C1", "c2_class": "Storage"},
    ])
    cellier = next(d for d in dg.per_room if d.room_id == "C1")
    assert "Lave-linge (20A)" in cellier.special_feeds_detail
    assert "Lave-linge (16A)" not in cellier.special_feeds_detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py::test_cellier_lave_linge_label_20A -v`
Expected: FAIL — le libellé actuel est « Lave-linge (16A) ».

- [ ] **Step 3: Fix the label**

Dans le bloc `STORAGE` de `compute_devis_for_room`, remplacer (lignes 178-180) :

```python
        devis.special_feeds_detail.extend([
            "Lave-linge (16A)", "Sèche-linge (16A)", "Cumulus",
        ])
```

par :

```python
        devis.special_feeds_detail.extend([
            "Lave-linge (20A)", "Sèche-linge (16A)", "Cumulus",
        ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py::test_cellier_lave_linge_label_20A -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_rules_evolutions.py
git commit -m "fix(nfc): libellé lave-linge cellier 16A -> 20A (cohérence circuit réel)"
```

---

## Task 4: Test d'intégration tableau — DDR Type A sans cellier

**Files:**
- Test: `tests/test_nfc_rules_evolutions.py`

- [ ] **Step 1: Write the failing test**

Ajouter à `tests/test_nfc_rules_evolutions.py` :

```python
def test_tableau_force_rcd_type_a_sans_cellier():
    """Logement sans cellier mais avec SDB → le lave-linge garanti crée un
    circuit LAUNDRY qui force un DDR Type A dans le tableau."""
    from src.planrec.nfc_tableau import generate_tableau

    dg = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "S1", "c2_class": "Bath"},
    ])
    tableau = generate_tableau(devis_global=dg, heating_enabled=True)
    assert any(rcd.rcd_type == "A" for rcd in tableau.rcds)
```

- [ ] **Step 2: Run test to verify it passes (guarantee already in place)**

Run: `.venv/bin/pytest tests/test_nfc_rules_evolutions.py::test_tableau_force_rcd_type_a_sans_cellier -v`
Expected: PASS — Tasks 1-3 ont déjà branché la garantie. Ce test verrouille la chaîne règles → tableau pour éviter toute régression future.

> Note : si ce test échoue, vérifier que `_ensure_washing_machine` est bien appelé dans `compute_devis_global` (Task 2, Step 4) et que `requires_type_a=True` pour le lave-linge dans `nfc_tableau.py:273`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_nfc_rules_evolutions.py
git commit -m "test(nfc): verrou intégration — lave-linge garanti force un DDR Type A"
```

---

## Task 5: Non-régression suite complète

**Files:** aucun (vérification)

- [ ] **Step 1: Run the full fast test suite**

Run: `.venv/bin/pytest -m "not slow" -q`
Expected: PASS. En particulier `tests/test_nfc_tableau.py`, `tests/test_nfc_equipments.py`, `tests/test_devis_apptest.py`, `tests/test_tableau_renderer.py` ne doivent pas régresser.

- [ ] **Step 2: If any pre-existing test breaks, inspect and reconcile**

Les tests existants comptant les convecteurs (séjour/chambre avec surface) ou les lave-linge agrégés peuvent désormais voir des quantités différentes. Pour chacun : vérifier que le nouveau total correspond à la règle du spec (convecteurs = `max(1, ceil(surface/20))` ; +1 lave-linge garanti si aucun cellier). Mettre à jour l'attendu du test si — et seulement si — l'écart est conforme au spec. Ne pas masquer une vraie régression.

- [ ] **Step 3: Commit any reconciled tests**

```bash
git add -A
git commit -m "test(nfc): réconciliation des tests impactés par convecteurs/lave-linge"
```

---

## Self-Review (effectuée)

- **Spec coverage :** Garantie lave-linge (Task 2), repli prioritaire (Task 2 step 1/3), circuit-only (Task 2), libellé 20A neuf + cellier (Task 2 & 3), convecteurs surface + forfait (Task 1), sèche-serviettes/sèche-linge/cumulus inchangés (aucune tâche ne les touche). Couvert.
- **Placeholders :** aucun — chaque step montre le code complet et la commande exacte.
- **Type consistency :** `_convector_count(nfc_cat, surface_m2)`, `_ensure_washing_machine(out)`, `_WASHING_FALLBACK_PRIORITY`, `EquipmentType.WASHING_MACHINE/CONVECTOR`, `NFCCategory.*`, `Devis(...)` et `tableau.rcds[].rcd_type` — noms cohérents entre tâches et conformes au code lu (`nfc_rules.py`, `nfc_tableau.py`).
