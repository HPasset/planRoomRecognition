# Tableau électrique V1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Génération automatique du schéma de tableau électrique batIA (style Hager Ready) à partir du devis NFC, avec rendu SVG inline dans Streamlit + export PDF A4 prêt-pour-chantier.

**Architecture:** Logique métier 100% pure dans `src/planrec/nfc_tableau.py` (testable pytest). Rendu SVG + PDF dans `src/planrec/tableau_renderer.py`. Refactor préalable de `EquipmentType` (éclatement de `SPECIAL_FEED` en 6 sous-types typés + 2 chauffage). Intégration en bas de la page Streamlit actuelle, gated par le click "Générer devis".

**Tech Stack:** Python 3.11, Streamlit 1.57, reportlab (PDF), pytest, Streamlit AppTest, pypdf (validation tests PDF).

**Spec de référence :** [`docs/superpowers/specs/2026-06-02-tableau-electrique-design.md`](../specs/2026-06-02-tableau-electrique-design.md)

---

## File Structure

**Création** :
- `src/planrec/nfc_tableau.py` — Module Python pur : `CircuitType` enum, `Circuit`/`RCD`/`Tableau` dataclasses, algo greedy 7-phase de répartition.
- `src/planrec/tableau_renderer.py` — Rendu SVG inline (str XML) + tableau HTML descriptif + export PDF reportlab.
- `tests/test_nfc_tableau.py` — Tests unitaires pytest (~18 tests) pour le module ci-dessus.
- `tests/test_tableau_renderer.py` — Tests unitaires pytest (~6 tests) pour le rendu.

**Modification (Python)** :
- `src/planrec/nfc_rules.py` — Éclater `EquipmentType.SPECIAL_FEED` en 6 sous-types (`OVEN`/`COOKTOP`/`DISHWASHER`/`WASHING_MACHINE`/`DRYER`/`BOILER`) + 2 chauffage (`CONVECTOR`/`TOWEL_WARMER`). Adapter `compute_devis_for_room` (Cuisine, Cellier, SdB, auto-génération chauffage pour pièces principales).
- `src/planrec/nfc_equipments.py` — Étendre `EQUIP_TYPES` + `NFC_TO_EQUIP_TYPE` avec les 8 nouveaux types.
- `src/planrec/nfc_pricing.py` — Étendre `DEFAULT_PRICES_HT` + `EQUIPMENT_LABELS_FR` avec les 8 nouveaux types.
- `app/streamlit_app.py` — Sidebar : toggle "Chauffage électrique" + expander override typologie. Section principale "⚡ Tableau électrique" en bas (gated trigger devis) avec rendu SVG + liste HTML + bouton download PDF.

**Modification (React + dist)** :
- `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx` — Ajouter 8 nouveaux SVG icônes (style NF EN 60617 stylisé) pour les nouveaux types d'équipements.
- `app/components/pastille_canvas/frontend/dist/` — Auto-régénéré par `npm run build`, commit après Phase 1.

**Modification (tests)** :
- `tests/test_nfc_equipments.py` — Adapter `test_generate_equipments_kitchen_qty_explodes` (compte `Oven`/`Cooktop`/`Dishwasher` au lieu de `SpecialFeed`).
- `tests/test_devis_apptest.py` — Adapter compteurs équipements cuisine + buanderie + ajouter 5 nouveaux tests AppTest T1-T5.
- `tests/conftest.py` — Helpers `get_tableau_state(at)` si besoin.

**Journal** :
- `docs/journal/2026-06-02.md` — Mis à jour en continu pendant l'exécution.

---

## Phases — Vue d'ensemble

| Phase | Périmètre | Effort | Sortie |
|---|---|---|---|
| 1 | Refactor `EquipmentType` — éclater `SPECIAL_FEED` + ajouter chauffage + adapter tests existants | 0.5j | 62 tests existants toujours verts (compteurs adaptés) + 8 SVG icônes |
| 2 | Module `nfc_tableau.py` : typologie, circuits, RCD, répartition (TDD strict 7-phase) | 2j | 18 tests pytest verts |
| 3 | `tableau_renderer.py` : SVG inline + couleurs + liste HTML | 1j | Rendu visible dans Streamlit |
| 4 | `tableau_renderer.py` : export PDF reportlab | 0.5-1j | Download fonctionne, parse pypdf OK |
| 5 | Intégration `streamlit_app.py` + 5 tests AppTest (T1-T5) | 0.5j | E2E démo prête, 75 tests verts |
| 6 | Polish + journal + spec coverage check | 0.5j | Démo OK, journal à jour |

**Total estimé : ~5j ouvrés**.

---

## Phase 1 — Refactor `EquipmentType` + chauffage

### Task 1.1 — Étendre l'enum `EquipmentType` avec les 8 nouveaux types

**Files:**
- Modify: `src/planrec/nfc_rules.py:33-38`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_equipment_type_has_all_v2_subtypes():
    """Les 6 sous-types spécialisés + 2 chauffage doivent être présents."""
    from src.planrec.nfc_rules import EquipmentType
    assert EquipmentType.OVEN.value == "four"
    assert EquipmentType.COOKTOP.value == "plaque_cuisson"
    assert EquipmentType.DISHWASHER.value == "lave_vaisselle"
    assert EquipmentType.WASHING_MACHINE.value == "lave_linge"
    assert EquipmentType.DRYER.value == "seche_linge"
    assert EquipmentType.BOILER.value == "chaudiere_cumulus"
    assert EquipmentType.CONVECTOR.value == "convecteur"
    assert EquipmentType.TOWEL_WARMER.value == "seche_serviettes"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_equipment_type_has_all_v2_subtypes -v`
Expected: FAIL with `AttributeError: OVEN` (ou similaire).

- [ ] **Step 3: Étendre l'enum dans `src/planrec/nfc_rules.py`**

Replace lines 33-38 :

```python
class EquipmentType(str, Enum):
    # Anciens types (préservés pour compatibilité)
    SOCKET = "prise_courant"
    RJ45 = "prise_rj45"
    LIGHT_POINT = "point_lumineux"
    SWITCH = "interrupteur"
    SPECIAL_FEED = "alimentation_specialisee"  # legacy, plus généré par compute_devis_for_room
    # NEW V1.2 — éclatement de SPECIAL_FEED en sous-types typés
    OVEN = "four"
    COOKTOP = "plaque_cuisson"
    DISHWASHER = "lave_vaisselle"
    WASHING_MACHINE = "lave_linge"
    DRYER = "seche_linge"
    BOILER = "chaudiere_cumulus"
    # NEW V1.2 — chauffage électrique
    CONVECTOR = "convecteur"
    TOWEL_WARMER = "seche_serviettes"
```

- [ ] **Step 4: Run test, verify pass**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_equipment_type_has_all_v2_subtypes -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "$(cat <<'EOF'
feat(nfc): étendre EquipmentType avec 6 sous-types spé + 2 chauffage

SPECIAL_FEED gardé legacy. Ajouts :
- OVEN, COOKTOP, DISHWASHER, WASHING_MACHINE, DRYER, BOILER (spécialisés)
- CONVECTOR, TOWEL_WARMER (chauffage)

Prérequis du tableau électrique V1 — chaque circuit spécialisé doit
avoir son type identifié pour générer le bon calibre disjoncteur.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.2 — Étendre `DEFAULT_PRICES_HT` + `EQUIPMENT_LABELS_FR`

**Files:**
- Modify: `src/planrec/nfc_pricing.py`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_pricing_covers_all_new_types():
    """DEFAULT_PRICES_HT et EQUIPMENT_LABELS_FR couvrent les 8 nouveaux types."""
    from src.planrec.nfc_rules import EquipmentType
    from src.planrec.nfc_pricing import DEFAULT_PRICES_HT, EQUIPMENT_LABELS_FR

    new_types = [
        EquipmentType.OVEN, EquipmentType.COOKTOP, EquipmentType.DISHWASHER,
        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER, EquipmentType.BOILER,
        EquipmentType.CONVECTOR, EquipmentType.TOWEL_WARMER,
    ]
    for t in new_types:
        assert t in DEFAULT_PRICES_HT, f"prix manquant pour {t.value}"
        assert DEFAULT_PRICES_HT[t] > 0
        assert t in EQUIPMENT_LABELS_FR, f"label manquant pour {t.value}"
        assert len(EQUIPMENT_LABELS_FR[t]) > 0
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_pricing_covers_all_new_types -v`
Expected: FAIL avec `KeyError` ou `AssertionError`.

- [ ] **Step 3: Étendre les dicts dans `src/planrec/nfc_pricing.py`**

Remplacer le bloc `DEFAULT_PRICES_HT` et `EQUIPMENT_LABELS_FR` :

```python
# Prix unitaires HT par défaut (€) — fourniture + pose
DEFAULT_PRICES_HT: dict[EquipmentType, float] = {
    # Anciens (préservés pour rétrocompat)
    EquipmentType.SOCKET: 25.0,
    EquipmentType.RJ45: 40.0,
    EquipmentType.LIGHT_POINT: 50.0,
    EquipmentType.SWITCH: 18.0,
    EquipmentType.SPECIAL_FEED: 70.0,  # legacy fourre-tout, valeur moyenne
    # NEW V1.2 — circuits spécialisés typés
    EquipmentType.OVEN: 80.0,
    EquipmentType.COOKTOP: 110.0,        # 32A + câble 6mm² → plus cher
    EquipmentType.DISHWASHER: 75.0,
    EquipmentType.WASHING_MACHINE: 75.0,
    EquipmentType.DRYER: 75.0,
    EquipmentType.BOILER: 85.0,
    # NEW V1.2 — chauffage
    EquipmentType.CONVECTOR: 65.0,       # alim seule, hors convecteur
    EquipmentType.TOWEL_WARMER: 70.0,
}


EQUIPMENT_LABELS_FR: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise de courant",
    EquipmentType.RJ45: "Prise RJ45",
    EquipmentType.LIGHT_POINT: "Point lumineux",
    EquipmentType.SWITCH: "Interrupteur",
    EquipmentType.SPECIAL_FEED: "Alimentation spécialisée",
    EquipmentType.OVEN: "Four",
    EquipmentType.COOKTOP: "Plaque de cuisson",
    EquipmentType.DISHWASHER: "Lave-vaisselle",
    EquipmentType.WASHING_MACHINE: "Lave-linge",
    EquipmentType.DRYER: "Sèche-linge",
    EquipmentType.BOILER: "Chaudière/cumulus",
    EquipmentType.CONVECTOR: "Convecteur",
    EquipmentType.TOWEL_WARMER: "Sèche-serviettes",
}
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_pricing_covers_all_new_types -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_pricing.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): prix et labels FR pour les 8 nouveaux types équipement

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.3 — Refactor cuisine : `SPECIAL_FEED×3` → `OVEN+COOKTOP+DISHWASHER`

**Files:**
- Modify: `src/planrec/nfc_rules.py:121-131` (bloc KITCHEN)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_kitchen_generates_typed_special_feeds():
    """Cuisine génère 1 Four + 1 Plaque + 1 LV (au lieu de 3× SPECIAL_FEED)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("k1", "Kitchen")
    assert devis.items.get(EquipmentType.OVEN) == 1
    assert devis.items.get(EquipmentType.COOKTOP) == 1
    assert devis.items.get(EquipmentType.DISHWASHER) == 1
    # plus de SPECIAL_FEED générique en cuisine
    assert EquipmentType.SPECIAL_FEED not in devis.items
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_kitchen_generates_typed_special_feeds -v`
Expected: FAIL (cuisine produit encore `SPECIAL_FEED = 3`).

- [ ] **Step 3: Refactor le bloc KITCHEN dans `compute_devis_for_room`**

Dans `src/planrec/nfc_rules.py`, remplacer le bloc Kitchen (lignes 121-131) :

```python
    elif nfc_cat == NFCCategory.KITCHEN:
        # 6 prises (dont 4 au-dessus plan travail) + 1 lumière + 1 interrupteur
        devis.items[EquipmentType.SOCKET] = 6
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        # Circuits spécialisés typés (V1.2)
        devis.items[EquipmentType.OVEN] = 1
        devis.items[EquipmentType.COOKTOP] = 1
        devis.items[EquipmentType.DISHWASHER] = 1
        devis.special_feeds_detail.extend([
            "Plaque de cuisson (32A)", "Four (16A)", "Lave-vaisselle (16A)",
        ])
        devis.notes.append("4 prises au-dessus du plan de travail")
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_kitchen_generates_typed_special_feeds -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): cuisine génère OVEN+COOKTOP+DISHWASHER typés

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.4 — Refactor cellier/buanderie : `SPECIAL_FEED×3` → `WASHING_MACHINE+DRYER+BOILER`

**Files:**
- Modify: `src/planrec/nfc_rules.py:133-142` (bloc STORAGE)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_storage_generates_typed_special_feeds():
    """Cellier/Buanderie : LL + SL + Chaudière (au lieu de 3× SPECIAL_FEED)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("s1", "Storage")
    assert devis.items.get(EquipmentType.WASHING_MACHINE) == 1
    assert devis.items.get(EquipmentType.DRYER) == 1
    assert devis.items.get(EquipmentType.BOILER) == 1
    assert EquipmentType.SPECIAL_FEED not in devis.items
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_storage_generates_typed_special_feeds -v`
Expected: FAIL.

- [ ] **Step 3: Refactor le bloc STORAGE**

Dans `src/planrec/nfc_rules.py`, remplacer le bloc Storage (lignes 133-142) :

```python
    elif nfc_cat == NFCCategory.STORAGE:
        # Cellier/Buanderie : 1 lumière + 1 prise + 3 circuits spécialisés typés
        devis.items[EquipmentType.LIGHT_POINT] = 1
        devis.items[EquipmentType.SWITCH] = 1
        devis.items[EquipmentType.SOCKET] = 1
        devis.items[EquipmentType.WASHING_MACHINE] = 1
        devis.items[EquipmentType.DRYER] = 1
        devis.items[EquipmentType.BOILER] = 1
        devis.special_feeds_detail.extend([
            "Lave-linge (16A)", "Sèche-linge (16A)", "Cumulus",
        ])
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_storage_generates_typed_special_feeds -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): cellier génère WASHING_MACHINE+DRYER+BOILER typés

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.5 — Refactor SdB : `SPECIAL_FEED×1` (sèche-serviette) → `TOWEL_WARMER`

**Files:**
- Modify: `src/planrec/nfc_rules.py:111-119` (bloc BATH)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_bath_generates_towel_warmer_not_special_feed():
    """SdB génère 1 TOWEL_WARMER (sèche-serviettes, chauffage)."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    devis = compute_devis_for_room("b1", "Bath")
    assert devis.items.get(EquipmentType.TOWEL_WARMER) == 1
    assert EquipmentType.SPECIAL_FEED not in devis.items
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_bath_generates_towel_warmer_not_special_feed -v`
Expected: FAIL.

- [ ] **Step 3: Refactor le bloc BATH**

Dans `src/planrec/nfc_rules.py`, remplacer le bloc Bath (lignes 111-119) :

```python
    elif nfc_cat == NFCCategory.BATH:
        # Central + applique au-dessus vasque
        devis.items[EquipmentType.LIGHT_POINT] = 2
        devis.items[EquipmentType.SWITCH] = 1
        devis.items[EquipmentType.SOCKET] = 1 + (1 if handicap else 0)
        # Sèche-serviettes (V1.2 : circuit chauffage typé)
        devis.items[EquipmentType.TOWEL_WARMER] = 1
        devis.special_feeds_detail.append("Sèche-serviettes")
        devis.notes.append("⚠ Zone 60 cm autour douche/baignoire interdite")
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_bath_generates_towel_warmer_not_special_feed -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "feat(nfc): SdB génère TOWEL_WARMER (chauffage) au lieu de SPECIAL_FEED

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.6 — Auto-génération `CONVECTOR` pour pièces principales (gated par `heating_enabled`)

**Files:**
- Modify: `src/planrec/nfc_rules.py` (signature `compute_devis_for_room` + nouveau param + appel `compute_devis_global`)
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_equipments.py`:

```python
def test_heating_enabled_adds_convector_to_living_and_bedroom():
    """Avec heating_enabled=True (défaut), séjour et chambres reçoivent 1 CONVECTOR."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    living = compute_devis_for_room("L1", "LivingRoom", surface_m2=20.0)
    bedroom = compute_devis_for_room("B1", "BedRoom")
    assert living.items.get(EquipmentType.CONVECTOR) == 1
    assert bedroom.items.get(EquipmentType.CONVECTOR) == 1


def test_heating_disabled_no_convector():
    """heating_enabled=False supprime convecteur + sèche-serviettes."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    living = compute_devis_for_room("L1", "LivingRoom", surface_m2=20.0,
                                     heating_enabled=False)
    bath = compute_devis_for_room("B1", "Bath", heating_enabled=False)
    assert EquipmentType.CONVECTOR not in living.items
    assert EquipmentType.TOWEL_WARMER not in bath.items


def test_heating_no_convector_in_secondary_rooms():
    """Convecteur uniquement en pièces principales (séjour, chambres). Pas en
    cuisine/WC/SdB/cellier/entrée."""
    from src.planrec.nfc_rules import compute_devis_for_room, EquipmentType
    for c2 in ("Kitchen", "Bath", "Storage", "Entry"):
        d = compute_devis_for_room("x", c2, heating_enabled=True)
        assert EquipmentType.CONVECTOR not in d.items, (
            f"Convecteur indu pour {c2}"
        )
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -k "heating" -v`
Expected: tous FAIL (signature `heating_enabled` n'existe pas encore).

- [ ] **Step 3: Ajouter le param `heating_enabled` et la logique chauffage**

Dans `src/planrec/nfc_rules.py`, modifier la signature de `compute_devis_for_room` :

```python
def compute_devis_for_room(
    room_id: str,
    c2_class: str,
    surface_m2: float | None = None,
    handicap: bool = False,
    ocr_hint: str | None = None,
    heating_enabled: bool = True,    # NEW V1.2
) -> Devis:
```

Et dans le bloc BATH, gater le `TOWEL_WARMER` par `heating_enabled` :

```python
    elif nfc_cat == NFCCategory.BATH:
        devis.items[EquipmentType.LIGHT_POINT] = 2
        devis.items[EquipmentType.SWITCH] = 1
        devis.items[EquipmentType.SOCKET] = 1 + (1 if handicap else 0)
        if heating_enabled:
            devis.items[EquipmentType.TOWEL_WARMER] = 1
            devis.special_feeds_detail.append("Sèche-serviettes")
        devis.notes.append("⚠ Zone 60 cm autour douche/baignoire interdite")
```

À la fin de la fonction, juste avant `return devis`, ajouter l'auto-gen convecteur :

```python
    # Auto-génération chauffage électrique pour pièces principales
    if heating_enabled and nfc_cat in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM):
        devis.items[EquipmentType.CONVECTOR] = 1

    return devis
```

Et propager le param dans `compute_devis_global` (ligne 250) :

```python
def compute_devis_global(
    rooms: list[dict],
    handicap: bool = False,
    heating_enabled: bool = True,     # NEW V1.2
) -> DevisGlobal:
    out = DevisGlobal(handicap=handicap)
    for r in rooms:
        devis = compute_devis_for_room(
            room_id=r["id"],
            c2_class=r["c2_class"],
            surface_m2=r.get("surface_m2"),
            handicap=handicap,
            ocr_hint=r.get("ocr_hint"),
            heating_enabled=heating_enabled,
        )
        out.per_room.append(devis)
    return out
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -k "heating" -v`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_rules.py tests/test_nfc_equipments.py
git commit -m "$(cat <<'EOF'
feat(nfc): auto-gen CONVECTOR pour pièces principales + toggle heating_enabled

- Séjour + chambres reçoivent 1 CONVECTOR si heating_enabled=True
- SdB conserve TOWEL_WARMER si heating_enabled=True
- Param heating_enabled (default True) propagé à compute_devis_global
- Pas de convecteur en cuisine / WC / cellier / entrée (NFC §10)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.7 — Étendre `EQUIP_TYPES` + `NFC_TO_EQUIP_TYPE` dans `nfc_equipments.py`

**Files:**
- Modify: `src/planrec/nfc_equipments.py:29-45`
- Test: `tests/test_nfc_equipments.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_equipments.py`:

```python
def test_equip_types_has_8_new_keys():
    """EQUIP_TYPES contient les 8 nouvelles clés avec label/color/svg_id."""
    from src.planrec.nfc_equipments import EQUIP_TYPES, NFC_TO_EQUIP_TYPE
    from src.planrec.nfc_rules import EquipmentType

    new_keys = ["Oven", "Cooktop", "Dishwasher", "WashingMachine", "Dryer",
                "Boiler", "Convector", "TowelWarmer"]
    for k in new_keys:
        assert k in EQUIP_TYPES, f"clé manquante : {k}"
        for field in ("label", "color", "svg_id"):
            assert field in EQUIP_TYPES[k], f"{k}: {field} manquant"
        assert EQUIP_TYPES[k]["color"].startswith("rgb(")

    # Mapping enum → clé
    assert NFC_TO_EQUIP_TYPE[EquipmentType.OVEN] == "Oven"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.COOKTOP] == "Cooktop"
    assert NFC_TO_EQUIP_TYPE[EquipmentType.CONVECTOR] == "Convector"
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_equip_types_has_8_new_keys -v`
Expected: FAIL.

- [ ] **Step 3: Étendre les dicts dans `src/planrec/nfc_equipments.py`**

Remplacer le bloc `EQUIP_TYPES` (lignes 29-35) :

```python
# Mapping label devis (FR) + couleur (CSS) + svg_id (pour le composant React)
EQUIP_TYPES: dict[str, dict[str, str]] = {
    # Anciens types (préservés)
    "Prise":          {"label": "Prise courant",  "color": "rgb(255, 112, 67)", "svg_id": "socket"},
    "RJ45":           {"label": "Prise RJ45",     "color": "rgb(38, 166, 154)", "svg_id": "rj45"},
    "LightPoint":     {"label": "Point lumineux", "color": "rgb(251, 192, 45)", "svg_id": "light"},
    "Switch":         {"label": "Interrupteur",   "color": "rgb(66, 165, 245)", "svg_id": "switch"},
    "SpecialFeed":    {"label": "Alim spé",       "color": "rgb(171, 71, 188)", "svg_id": "specfeed"},
    # NEW V1.2 — circuits spécialisés typés (violet cuisine, orange buanderie, rouge cumulus)
    "Oven":           {"label": "Four",           "color": "rgb(171, 71, 188)", "svg_id": "oven"},
    "Cooktop":        {"label": "Plaque cuisson", "color": "rgb(123, 31, 162)", "svg_id": "cooktop"},
    "Dishwasher":     {"label": "Lave-vaisselle", "color": "rgb(194, 24, 91)",  "svg_id": "dishwasher"},
    "WashingMachine": {"label": "Lave-linge",     "color": "rgb(255, 112, 67)", "svg_id": "washingmachine"},
    "Dryer":          {"label": "Sèche-linge",    "color": "rgb(255, 167, 38)", "svg_id": "dryer"},
    "Boiler":         {"label": "Chaudière",      "color": "rgb(198, 40, 40)",  "svg_id": "boiler"},
    # NEW V1.2 — chauffage (rouge clair)
    "Convector":      {"label": "Convecteur",     "color": "rgb(239, 83, 80)",  "svg_id": "convector"},
    "TowelWarmer":    {"label": "Sèche-serv.",    "color": "rgb(239, 154, 154)", "svg_id": "towelwarmer"},
}
```

Et étendre `NFC_TO_EQUIP_TYPE` (lignes 39-45) :

```python
NFC_TO_EQUIP_TYPE: dict[EquipmentType, str] = {
    EquipmentType.SOCKET: "Prise",
    EquipmentType.RJ45: "RJ45",
    EquipmentType.LIGHT_POINT: "LightPoint",
    EquipmentType.SWITCH: "Switch",
    EquipmentType.SPECIAL_FEED: "SpecialFeed",
    # NEW V1.2
    EquipmentType.OVEN: "Oven",
    EquipmentType.COOKTOP: "Cooktop",
    EquipmentType.DISHWASHER: "Dishwasher",
    EquipmentType.WASHING_MACHINE: "WashingMachine",
    EquipmentType.DRYER: "Dryer",
    EquipmentType.BOILER: "Boiler",
    EquipmentType.CONVECTOR: "Convector",
    EquipmentType.TOWEL_WARMER: "TowelWarmer",
}
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py::test_equip_types_has_8_new_keys -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_equipments.py tests/test_nfc_equipments.py
git commit -m "feat(equipments): EQUIP_TYPES + NFC_TO_EQUIP_TYPE étendus aux 8 nouveaux types

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 1.8 — Adapter les tests existants impactés par le refactor

**Files:**
- Modify: `tests/test_nfc_equipments.py` (test_generate_equipments_kitchen_qty_explodes)
- Modify: `tests/test_devis_apptest.py` (compteurs équipements impactés)

- [ ] **Step 1: Faire passer la baseline pytest pour identifier les régressions**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v 2>&1 | tail -30`
Expected: `test_generate_equipments_kitchen_qty_explodes` FAIL car attend `SpecialFeed ≥ 3` mais ne reçoit plus rien (cuisine n'émet plus `SPECIAL_FEED`).

- [ ] **Step 2: Adapter `test_generate_equipments_kitchen_qty_explodes`**

Dans `tests/test_nfc_equipments.py`, remplacer le test existant :

```python
def test_generate_equipments_kitchen_qty_explodes():
    """Cuisine NFC : Four + Plaque + LV (typés) + 6 prises + 1 lum + 1 inter."""
    from src.planrec.nfc_rules import compute_devis_global

    rooms_input = [
        {"id": "room_001", "c2_class": "Kitchen", "surface_m2": None,
         "ocr_hint": None},
    ]
    devis = compute_devis_global(rooms_input, handicap=False)
    instances = generate_equipments_from_devis_global(devis)
    type_counts: dict[str, int] = {}
    for inst in instances:
        type_counts[inst["type"]] = type_counts.get(inst["type"], 0) + 1
    # 6 prises + 1 lum + 1 interrupteur en cuisine NFC
    assert type_counts.get("Prise", 0) >= 6
    assert type_counts.get("LightPoint", 0) >= 1
    assert type_counts.get("Switch", 0) >= 1
    # 3 circuits spécialisés typés (au lieu de 3 SpecialFeed génériques)
    assert type_counts.get("Oven", 0) == 1
    assert type_counts.get("Cooktop", 0) == 1
    assert type_counts.get("Dishwasher", 0) == 1
    # Pas de SpecialFeed légacy en cuisine
    assert type_counts.get("SpecialFeed", 0) == 0
```

- [ ] **Step 3: Run pytest, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_equipments.py -v 2>&1 | tail -20`
Expected: tous PASS (17 tests anciens + ~6 nouveaux = ~23 PASS).

- [ ] **Step 4: Identifier impact sur AppTest**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py -v 2>&1 | grep -E "FAIL|ERROR" | head -10`

Identifier les tests AppTest qui FAIL à cause du refactor (probablement ceux qui comptent `SpecialFeed` dans le devis cuisine/buanderie/SdB ou les apptest qui vérifient le nb total d'équipements).

- [ ] **Step 5: Adapter les AppTest qui régressent**

Pour chaque test AppTest impacté (ex `test_E1_xxx`, `test_devis_cuisine_xxx`), remplacer les compteurs :
- Cuisine : `SpecialFeed = 3` → vérifier `Oven=1, Cooktop=1, Dishwasher=1`
- Buanderie : `SpecialFeed = 3` → vérifier `WashingMachine=1, Dryer=1, Boiler=1`
- SdB : `SpecialFeed = 1` → vérifier `TowelWarmer=1`
- Séjour : ajouter `Convector=1` (heating default ON)
- Chambres : ajouter `Convector=1`

Faire un test AppTest à la fois, mettre à jour les assertions, run pytest pour valider chaque correction avant la suivante.

- [ ] **Step 6: Verify all 62 tests pass**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -3`
Expected: 62+ PASS, 0 FAIL.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "$(cat <<'EOF'
test: adapter tests existants au refactor EquipmentType

- test_generate_equipments_kitchen_qty_explodes : compte Oven/Cooktop/
  Dishwasher au lieu de SpecialFeed×3
- AppTest cuisine/buanderie/SdB : compteurs équipements adaptés
- AppTest séjour/chambres : ajout Convector=1 (heating default ON)

Tous les 62 tests existants restent verts après le refactor.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.9 — Ajouter 8 SVG icônes dans `PastilleCanvas.tsx`

**Files:**
- Modify: `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`
- Rebuild: `app/components/pastille_canvas/frontend/dist/`

- [ ] **Step 1: Identifier le bloc des SVG icônes existants**

Run: `grep -n "svg_id\|EQUIP_TYPES\|equipSvg\|switch.*svg" app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx | head -20`

Localiser le composant ou la map qui rend les SVG par `svg_id` (probablement un `switch` ou un `case` sur le type).

- [ ] **Step 2: Ajouter les 8 nouveaux SVG icônes**

Dans `app/components/pastille_canvas/frontend/src/PastilleCanvas.tsx`, ajouter les 8 cas correspondant aux nouveaux `svg_id` (`oven`, `cooktop`, `dishwasher`, `washingmachine`, `dryer`, `boiler`, `convector`, `towelwarmer`).

Style cohérent NF EN 60617 stylisé : carré 24×24 px avec bordure colorée + glyphe simple (lettre F pour Four, ≡ pour Plaque, ◇ pour LV, etc.) :

```tsx
// Exemple pour 'oven' (Four) — adapter pour les 8 types
case "oven":
  return (
    <svg width={24} height={24} viewBox="0 0 24 24">
      <rect x="2" y="2" width="20" height="20" rx="2"
            fill={color} stroke="#37474F" strokeWidth="1.5" />
      <text x="12" y="16" fontSize="11" fontWeight="bold"
            textAnchor="middle" fill="white">F</text>
    </svg>
  );
case "cooktop":
  // ... (glyphe "P", 4 cercles, etc.)
```

Pour chaque type, utiliser un glyphe lisible :
- `oven` → "F" (Four)
- `cooktop` → 4 cercles (plaques)
- `dishwasher` → "LV"
- `washingmachine` → "LL"
- `dryer` → "SL"
- `boiler` → "C" (Cumulus)
- `convector` → "≋" (3 vagues, chaud)
- `towelwarmer` → "T"

- [ ] **Step 3: Rebuild dist**

Run: `cd app/components/pastille_canvas/frontend && npm run build && cd ../../../..`
Expected: build success, nouveau bundle `dist/assets/index-<hash>.js` produit (le hash change à chaque build).

- [ ] **Step 4: Verify pytest still passes (les nouveaux SVG n'affectent pas Python)**

Run: `.venv/bin/python -m pytest tests/ -v 2>&1 | tail -3`
Expected: 62+ PASS, 0 FAIL.

- [ ] **Step 5: Commit**

```bash
git add app/components/pastille_canvas/frontend/
git commit -m "$(cat <<'EOF'
feat(pastille_canvas): 8 nouveaux SVG icônes équipements typés

Glyphes simples NF EN 60617 stylisé pour Oven (F), Cooktop (≣), LV, LL,
SL, Boiler (C), Convector (≋), TowelWarmer (T). Code couleur cohérent
avec le rendu tableau électrique (violet cuisine, orange buanderie,
rouge chauffage).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 1.10 — Finalisation Phase 1 — verify 62 tests + journal

**Files:**
- Modify: `docs/journal/2026-06-02.md` (append Phase 1 summary)

- [ ] **Step 1: Run full test suite**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -5`
Expected: `N passed, 0 failed` (N ≈ 70 = 62 baseline + ~8 nouveaux Phase 1).

- [ ] **Step 2: Append Phase 1 summary au journal**

Dans `docs/journal/2026-06-02.md`, append :

```markdown

## Tableau électrique V1 — Phase 1 livrée (refactor EquipmentType)

**Contexte** : refacto modèle de données pour casser SPECIAL_FEED en sous-types
typés (Four, Plaque, LL, SL, LV, Chaudière) + ajout chauffage (Convecteur,
Sèche-serviettes). Prérequis du tableau électrique.

**Mise en œuvre** : 10 tasks TDD strict avec adaptation des 62 tests existants.

| Task | Sujet | Tests ajoutés |
|------|-------|---------------|
| 1.1 | Enum EquipmentType +8 valeurs | +1 |
| 1.2 | Prix HT + labels FR | +1 |
| 1.3 | Cuisine refacto | +1 |
| 1.4 | Cellier refacto | +1 |
| 1.5 | SdB refacto | +1 |
| 1.6 | heating_enabled + convecteurs auto | +3 |
| 1.7 | EQUIP_TYPES + mapping | +1 |
| 1.8 | Adapter tests existants | — |
| 1.9 | 8 SVG icônes React + rebuild dist | — |
| 1.10 | Bilan + journal | — |

**Résultat** : Phase 1 ✅ — tests verts (~70 total), prêt pour Phase 2.
```

- [ ] **Step 3: Commit**

```bash
git add docs/journal/2026-06-02.md
git commit -m "docs(journal): bilan Phase 1 tableau électrique — refactor EquipmentType

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 2 — Module `nfc_tableau.py` (algo greedy 7-phase)

### Task 2.1 — Setup module + `CircuitType` enum + `Circuit` dataclass

**Files:**
- Create: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_nfc_tableau.py
"""Tests pour le module nfc_tableau (algo greedy de répartition tableau électrique)."""
from __future__ import annotations
import pytest

from src.planrec.nfc_tableau import CircuitType, Circuit


def test_circuit_type_has_7_values():
    """7 types de circuits couvrent le périmètre V1."""
    expected = {"lighting", "socket", "kitchen_special", "laundry",
                "boiler", "heating", "towel_warmer"}
    actual = {ct.value for ct in CircuitType}
    assert actual == expected


def test_circuit_dataclass_fields():
    """Circuit a id, type, label, breaker_amps, cable_section_mm2, rooms_served,
    n_devices, requires_type_a."""
    c = Circuit(
        id="circ_abc12345",
        type=CircuitType.LIGHTING,
        label="Lum Séjour",
        breaker_amps=10,
        cable_section_mm2=1.5,
        rooms_served=["Sejour"],
        n_devices=3,
        requires_type_a=False,
    )
    assert c.id == "circ_abc12345"
    assert c.type == CircuitType.LIGHTING
    assert c.breaker_amps == 10
    assert c.cable_section_mm2 == 1.5
    assert not c.requires_type_a
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -v`
Expected: FAIL avec `ModuleNotFoundError`.

- [ ] **Step 3: Créer le module avec types**

Créer `src/planrec/nfc_tableau.py` :

```python
"""Algo greedy de répartition du tableau électrique selon NFC 15-100 + règles
cabinet associé. Logique métier 100% pure (testable pytest seul, aucune
dépendance Streamlit/React).

Source : docs/superpowers/specs/2026-06-02-tableau-electrique-design.md
"""
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class CircuitType(str, Enum):
    LIGHTING        = "lighting"          # 10A — points lumineux
    SOCKET          = "socket"            # 20A — prises courant
    KITCHEN_SPECIAL = "kitchen_special"   # Four / Plaque / LV (20A ou 32A)
    LAUNDRY         = "laundry"           # LL / SL (20A)
    BOILER          = "boiler"            # Chaudière / cumulus (20A)
    HEATING         = "heating"           # Convecteur (20A)
    TOWEL_WARMER    = "towel_warmer"      # Sèche-serviettes SdB (20A)


@dataclass
class Circuit:
    id: str
    type: CircuitType
    label: str
    breaker_amps: int
    cable_section_mm2: float
    rooms_served: list[str] = field(default_factory=list)
    n_devices: int = 0
    requires_type_a: bool = False


def generate_circuit_id() -> str:
    """Génère un ID unique 'circ_<8 hex>'."""
    return f"circ_{secrets.token_hex(4)}"
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -v`
Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): setup module nfc_tableau + CircuitType + Circuit

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.2 — `RCD` + `Tableau` dataclasses

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_tableau.py`:

```python
def test_rcd_dataclass_fields():
    from src.planrec.nfc_tableau import RCD, Circuit, CircuitType
    c = Circuit(id="c1", type=CircuitType.LIGHTING, label="x",
                breaker_amps=10, cable_section_mm2=1.5)
    rcd = RCD(id="rcd_1", rcd_type="A", amps=40, sensitivity_ma=30,
              circuits=[c])
    assert rcd.rcd_type == "A"
    assert rcd.amps == 40
    assert rcd.sensitivity_ma == 30
    assert len(rcd.circuits) == 1


def test_tableau_dataclass_fields():
    from src.planrec.nfc_tableau import Tableau
    t = Tableau(
        typology="T3", typology_source="auto", surface_m2=80.0,
        heating_enabled=True, rcds=[], total_modules=0, n_rails=1,
        notes=["RJ45 → coffret VDI"], warnings=[],
    )
    assert t.typology == "T3"
    assert t.heating_enabled is True
    assert t.notes == ["RJ45 → coffret VDI"]
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "rcd_dataclass or tableau_dataclass" -v`
Expected: FAIL.

- [ ] **Step 3: Ajouter `RCD` + `Tableau` dans le module**

Append to `src/planrec/nfc_tableau.py`:

```python
@dataclass
class RCD:
    """Interrupteur Différentiel."""
    id: str
    rcd_type: str        # "A" (plaque + LL obligatoire) ou "AC"
    amps: int            # 25, 40, 63, 80, 100, 125 (normalisé)
    sensitivity_ma: int  # 30 mA (résidentiel standard)
    circuits: list[Circuit] = field(default_factory=list)


@dataclass
class Tableau:
    typology: str                    # "T3"
    typology_source: str             # "auto" | "user_override"
    surface_m2: Optional[float]
    heating_enabled: bool
    rcds: list[RCD]
    total_modules: int               # somme circuits + RCD + headroom 20%
    n_rails: int                     # ceil(total / 13 modules par rail)
    notes: list[str]
    warnings: list[str]


def generate_rcd_id() -> str:
    """Génère un ID unique 'rcd_<8 hex>'."""
    return f"rcd_{secrets.token_hex(4)}"
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): RCD + Tableau dataclasses

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.3 — `detect_typology()` depuis les pièces du devis

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_detect_typology_T1_studio():
    """1 séjour seul → T1 (studio)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global(
        [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}],
    )
    assert detect_typology(devis) == "T1"


def test_detect_typology_T2_living_plus_1_bedroom():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T2"


def test_detect_typology_T3_living_plus_2_bedrooms():
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T3"


def test_detect_typology_T5_capped_at_5():
    """4+ chambres + séjour → T5 (on cap au lieu de T6/T7)."""
    from src.planrec.nfc_tableau import detect_typology
    from src.planrec.nfc_rules import compute_devis_global
    devis = compute_devis_global([
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "B4", "c2_class": "BedRoom"},
    ])
    assert detect_typology(devis) == "T5"
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "detect_typology" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `detect_typology()`**

Append to `src/planrec/nfc_tableau.py`:

```python
from src.planrec.nfc_rules import DevisGlobal, NFCCategory


def detect_typology(devis: DevisGlobal) -> str:
    """Auto-détecte la typologie du logement à partir du devis.

    Compte les pièces principales (séjour + chambres) :
    - 1 pièce principale (séjour seul, studio) → T1
    - séjour + 1 chambre → T2
    - séjour + 2 chambres → T3
    - séjour + 3 chambres → T4
    - séjour + 4+ chambres → T5 (cap)
    """
    n_main_rooms = sum(
        1 for d in devis.per_room
        if d.nfc_category in (NFCCategory.LIVINGROOM, NFCCategory.BEDROOM)
    )
    return f"T{min(n_main_rooms, 5)}"
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "detect_typology" -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): detect_typology() auto T1-T5 depuis devis

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.4 — Phase 2 algo : circuits éclairage (bin-packing 5 lights/circuit)

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_nfc_tableau.py`:

```python
def test_lighting_one_room_one_circuit_if_few_lights():
    """Une pièce avec ≤5 lights → 1 circuit éclairage 10A/1.5mm²."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    rooms_with_lights = [("Sejour", 3), ("Chambre 1", 2)]  # 5 total
    circuits = _build_lighting_circuits(rooms_with_lights)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 10
    assert circuits[0].cable_section_mm2 == 1.5
    assert circuits[0].n_devices == 5
    assert set(circuits[0].rooms_served) == {"Sejour", "Chambre 1"}


def test_lighting_bin_packing_overflow_creates_2_circuits():
    """7 lights ne tiennent pas sur 1 circuit (cap 5) → 2 circuits."""
    from src.planrec.nfc_tableau import _build_lighting_circuits
    rooms_with_lights = [("Cuisine", 7)]
    circuits = _build_lighting_circuits(rooms_with_lights)
    assert len(circuits) == 2
    assert sum(c.n_devices for c in circuits) == 7
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "lighting" -v`
Expected: FAIL avec `ImportError`.

- [ ] **Step 3: Implémenter `_build_lighting_circuits()`**

Append to `src/planrec/nfc_tableau.py`:

```python
LIGHTING_MAX_PER_CIRCUIT = 5      # Règle cabinet associé (NFC stricte = 8)
SOCKET_MAX_PER_CIRCUIT = 12       # Règle cabinet associé (NFC stricte = 8)
CONVECTOR_MAX_PER_CIRCUIT = 2     # Règle cabinet associé (2× 2000W max)


def _build_lighting_circuits(
    rooms_with_lights: list[tuple[str, int]],
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leur n_lights → circuits 5/circuit max.

    Trie pièces par n_lights décroissant. Ouvre circuits successifs en y
    ajoutant pièces tant que capacité restante.
    """
    sorted_rooms = sorted(rooms_with_lights, key=lambda x: -x[1])
    circuits: list[Circuit] = []
    current_capacity = 0
    current_rooms: list[str] = []
    current_n = 0

    def _flush():
        nonlocal current_capacity, current_rooms, current_n
        if current_n > 0:
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.LIGHTING,
                label=f"Éclairage {', '.join(current_rooms)}",
                breaker_amps=10,
                cable_section_mm2=1.5,
                rooms_served=list(current_rooms),
                n_devices=current_n,
                requires_type_a=False,
            ))
        current_capacity = 0
        current_rooms = []
        current_n = 0

    for room_name, n_lights in sorted_rooms:
        if n_lights > LIGHTING_MAX_PER_CIRCUIT:
            # Pièce trop chargée → ses lights occupent N circuits dédiés
            _flush()
            n_remaining = n_lights
            while n_remaining > 0:
                chunk = min(n_remaining, LIGHTING_MAX_PER_CIRCUIT)
                circuits.append(Circuit(
                    id=generate_circuit_id(),
                    type=CircuitType.LIGHTING,
                    label=f"Éclairage {room_name}",
                    breaker_amps=10,
                    cable_section_mm2=1.5,
                    rooms_served=[room_name],
                    n_devices=chunk,
                ))
                n_remaining -= chunk
        elif current_capacity + n_lights <= LIGHTING_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_capacity += n_lights
            current_n += n_lights
        else:
            _flush()
            current_rooms = [room_name]
            current_capacity = n_lights
            current_n = n_lights

    _flush()
    return circuits
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "lighting" -v`
Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _build_lighting_circuits (bin-packing 5/circuit 10A)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.5 — Phase 3 algo : circuits prises (bin-packing 12 sockets/circuit)

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_sockets_one_room_one_circuit():
    """Pièce 5 prises → 1 circuit 20A/2.5mm²."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms_with_sockets = [("Sejour", 5)]
    circuits = _build_socket_circuits(rooms_with_sockets)
    assert len(circuits) == 1
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].n_devices == 5


def test_sockets_pack_small_rooms_together():
    """3 petites pièces (2+1+1 prises) → 1 circuit grouppé."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("WC", 1), ("Entrée", 2), ("Couloir", 1)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 1
    assert circuits[0].n_devices == 4


def test_sockets_large_room_dedicated_circuit():
    """Pièce 12 prises → 1 circuit dédié."""
    from src.planrec.nfc_tableau import _build_socket_circuits
    rooms = [("Sejour", 12)]
    circuits = _build_socket_circuits(rooms)
    assert len(circuits) == 1
    assert circuits[0].n_devices == 12
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "sockets" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `_build_socket_circuits()`**

Append to `src/planrec/nfc_tableau.py`:

```python
def _build_socket_circuits(
    rooms_with_sockets: list[tuple[str, int]],
) -> list[Circuit]:
    """Bin-packing greedy : pièces avec leurs n_sockets → circuits 12/circuit
    max. Pièces avec n_sockets ≥ 6 prennent un circuit dédié, les plus petites
    sont packées ensemble."""
    sorted_rooms = sorted(rooms_with_sockets, key=lambda x: -x[1])
    circuits: list[Circuit] = []
    current_rooms: list[str] = []
    current_n = 0

    def _flush():
        nonlocal current_rooms, current_n
        if current_n > 0:
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=CircuitType.SOCKET,
                label=f"Prises {', '.join(current_rooms)}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=list(current_rooms),
                n_devices=current_n,
            ))
        current_rooms = []
        current_n = 0

    for room_name, n_sockets in sorted_rooms:
        if n_sockets > SOCKET_MAX_PER_CIRCUIT:
            _flush()
            n_remaining = n_sockets
            while n_remaining > 0:
                chunk = min(n_remaining, SOCKET_MAX_PER_CIRCUIT)
                circuits.append(Circuit(
                    id=generate_circuit_id(),
                    type=CircuitType.SOCKET,
                    label=f"Prises {room_name}",
                    breaker_amps=20,
                    cable_section_mm2=2.5,
                    rooms_served=[room_name],
                    n_devices=chunk,
                ))
                n_remaining -= chunk
        elif current_n + n_sockets <= SOCKET_MAX_PER_CIRCUIT:
            current_rooms.append(room_name)
            current_n += n_sockets
        else:
            _flush()
            current_rooms = [room_name]
            current_n = n_sockets

    _flush()
    return circuits
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "sockets" -v`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _build_socket_circuits (bin-packing 12/circuit 20A)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.6 — Phase 4 algo : circuits chauffage

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_heating_pack_2_convectors_per_circuit():
    """4 convecteurs → 2 circuits HEATING (2 max par circuit, 20A)."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    rooms_with_conv = [("Sejour", 1), ("Chambre 1", 1), ("Chambre 2", 1),
                       ("Chambre 3", 1)]
    circuits = _build_heating_circuits(rooms_with_conv, n_towel_warmers=0)
    heating = [c for c in circuits if c.type.value == "heating"]
    assert len(heating) == 2
    assert all(c.breaker_amps == 20 and c.cable_section_mm2 == 2.5
               for c in heating)
    assert sum(c.n_devices for c in heating) == 4


def test_heating_1_circuit_per_towel_warmer():
    """3 sèche-serviettes → 3 circuits dédiés TOWEL_WARMER (1 par circuit)."""
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits(rooms_with_convectors=[],
                                       n_towel_warmers=3)
    tw = [c for c in circuits if c.type.value == "towel_warmer"]
    assert len(tw) == 3


def test_heating_empty_lists():
    from src.planrec.nfc_tableau import _build_heating_circuits
    circuits = _build_heating_circuits([], n_towel_warmers=0)
    assert circuits == []
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "heating" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `_build_heating_circuits()`**

Append to `src/planrec/nfc_tableau.py`:

```python
def _build_heating_circuits(
    rooms_with_convectors: list[tuple[str, int]],
    n_towel_warmers: int,
) -> list[Circuit]:
    """Génère les circuits chauffage : convecteurs packés 2/circuit + 1 circuit
    par sèche-serviettes."""
    circuits: list[Circuit] = []

    # Convecteurs : pack 2 par circuit
    all_convectors: list[str] = []
    for room, n in rooms_with_convectors:
        all_convectors.extend([room] * n)

    while all_convectors:
        chunk = all_convectors[:CONVECTOR_MAX_PER_CIRCUIT]
        all_convectors = all_convectors[CONVECTOR_MAX_PER_CIRCUIT:]
        circuits.append(Circuit(
            id=generate_circuit_id(),
            type=CircuitType.HEATING,
            label=f"Chauffage {', '.join(chunk)}",
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=list(chunk),
            n_devices=len(chunk),
        ))

    # Sèche-serviettes : 1 circuit dédié par instance
    for i in range(n_towel_warmers):
        circuits.append(Circuit(
            id=generate_circuit_id(),
            type=CircuitType.TOWEL_WARMER,
            label=f"Sèche-serviettes {i+1}",
            breaker_amps=20,
            cable_section_mm2=2.5,
            rooms_served=[],
            n_devices=1,
        ))

    return circuits
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "heating" -v`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _build_heating_circuits (2 conv/circuit + 1 SS/circuit)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.7 — Phase 5 algo : circuits spécialisés (Plaque 32A, etc.)

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_specialized_each_appliance_one_circuit():
    """6 appareils spé → 6 circuits dédiés."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {
        EquipmentType.OVEN: 1,
        EquipmentType.COOKTOP: 1,
        EquipmentType.DISHWASHER: 1,
        EquipmentType.WASHING_MACHINE: 1,
        EquipmentType.DRYER: 1,
        EquipmentType.BOILER: 1,
    }
    circuits = _build_specialized_circuits(counts)
    assert len(circuits) == 6


def test_specialized_plaque_is_32A_6mm2_type_a():
    """Plaque cuisson → calibre 32A, câble 6mm², requires_type_a=True."""
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {EquipmentType.COOKTOP: 1}
    circuits = _build_specialized_circuits(counts)
    assert len(circuits) == 1
    plaque = circuits[0]
    assert plaque.breaker_amps == 32
    assert plaque.cable_section_mm2 == 6.0
    assert plaque.requires_type_a is True


def test_specialized_lavelinge_is_20A_2_5mm2_type_a():
    from src.planrec.nfc_tableau import _build_specialized_circuits
    from src.planrec.nfc_rules import EquipmentType
    counts = {EquipmentType.WASHING_MACHINE: 1}
    circuits = _build_specialized_circuits(counts)
    assert circuits[0].breaker_amps == 20
    assert circuits[0].cable_section_mm2 == 2.5
    assert circuits[0].requires_type_a is True
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "specialized" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `_build_specialized_circuits()`**

Append to `src/planrec/nfc_tableau.py`:

```python
from src.planrec.nfc_rules import EquipmentType


_SPECIALIZED_SPECS: dict[EquipmentType, tuple[int, float, str, bool, CircuitType]] = {
    # (breaker_amps, cable_section_mm2, label, requires_type_a, circuit_type)
    EquipmentType.OVEN:            (20, 2.5, "Four",          False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.COOKTOP:         (32, 6.0, "Plaque cuisson", True, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.DISHWASHER:      (20, 2.5, "Lave-vaisselle", False, CircuitType.KITCHEN_SPECIAL),
    EquipmentType.WASHING_MACHINE: (20, 2.5, "Lave-linge",     True, CircuitType.LAUNDRY),
    EquipmentType.DRYER:           (20, 2.5, "Sèche-linge",   False, CircuitType.LAUNDRY),
    EquipmentType.BOILER:          (20, 2.5, "Chaudière",      False, CircuitType.BOILER),
}


def _build_specialized_circuits(
    counts: dict[EquipmentType, int],
) -> list[Circuit]:
    """Génère 1 circuit par instance d'appareil spécialisé."""
    circuits: list[Circuit] = []
    for eq_type, n in counts.items():
        if eq_type not in _SPECIALIZED_SPECS or n <= 0:
            continue
        amps, section, label, type_a, ctype = _SPECIALIZED_SPECS[eq_type]
        for i in range(n):
            suffix = f" {i+1}" if n > 1 else ""
            circuits.append(Circuit(
                id=generate_circuit_id(),
                type=ctype,
                label=f"{label}{suffix}",
                breaker_amps=amps,
                cable_section_mm2=section,
                rooms_served=[],
                n_devices=1,
                requires_type_a=type_a,
            ))
    return circuits
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "specialized" -v`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _build_specialized_circuits (Plaque 32A Type A, etc.)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.8 — Phase 6 algo : calcul nombre min de RCD

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_min_rcds_T2_returns_2():
    """T2 → 2 RCD minimum (règle cabinet)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=None,
                             n_breakers=5) == 2


def test_min_rcds_surface_overrides_typology():
    """T1 mais 120 m² → 3 RCD (règle NFC stricte > règle typo)."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T1", surface_m2=120.0,
                             n_breakers=5) == 3


def test_min_rcds_many_breakers_forces_more():
    """T2 (2 RCD min) mais 18 disjoncteurs → ceil(18/8) = 3 RCD."""
    from src.planrec.nfc_tableau import _compute_min_rcds
    assert _compute_min_rcds(typology="T2", surface_m2=80.0,
                             n_breakers=18) == 3
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "min_rcds" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `_compute_min_rcds()`**

Append to `src/planrec/nfc_tableau.py`:

```python
_TYPO_RCD_RULE = {"T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 4}
MAX_BREAKERS_PER_RCD = 8


def _compute_min_rcds(
    typology: str,
    surface_m2: Optional[float],
    n_breakers: int,
) -> int:
    """Max des 3 contraintes : règle typo, règle surface NFC, ceil(N/8)."""
    n_typo = _TYPO_RCD_RULE.get(typology, 1)

    if surface_m2 is None:
        n_surface = 1
    elif surface_m2 <= 35:
        n_surface = 1
    elif surface_m2 <= 100:
        n_surface = 2
    else:
        n_surface = 3

    n_packing = math.ceil(n_breakers / MAX_BREAKERS_PER_RCD)

    return max(n_typo, n_surface, n_packing)
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "min_rcds" -v`
Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _compute_min_rcds (max typo/surface/packing)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.9 — Phase 7 algo : répartition circuits sur RCD + calcul calibre

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_distribute_type_A_contains_cooktop_and_lavelinge():
    """RCD1 Type A contient OBLIGATOIREMENT Plaque + LL."""
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Plaque",
                     breaker_amps=32, cable_section_mm2=6.0,
                     requires_type_a=True)
    ll = Circuit(id="c2", type=CircuitType.LAUNDRY, label="LL",
                 breaker_amps=20, cable_section_mm2=2.5,
                 requires_type_a=True)
    other = Circuit(id="c3", type=CircuitType.LIGHTING, label="Lum",
                    breaker_amps=10, cable_section_mm2=1.5)
    rcds = _distribute_circuits_to_rcds([plaque, ll, other], n_rcds=2)
    assert rcds[0].rcd_type == "A"
    type_a_ids = {c.id for c in rcds[0].circuits}
    assert "c1" in type_a_ids
    assert "c2" in type_a_ids


def test_distribute_other_rcds_are_type_AC():
    from src.planrec.nfc_tableau import _distribute_circuits_to_rcds, Circuit, CircuitType
    plaque = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="P",
                     breaker_amps=32, cable_section_mm2=6.0, requires_type_a=True)
    others = [Circuit(id=f"c{i+2}", type=CircuitType.LIGHTING, label=f"L{i}",
                      breaker_amps=10, cable_section_mm2=1.5)
              for i in range(2)]
    rcds = _distribute_circuits_to_rcds([plaque] + others, n_rcds=2)
    assert rcds[0].rcd_type == "A"
    assert rcds[1].rcd_type == "AC"


def test_rcd_amps_formula_normalized():
    """RCD avec 4× 20A non-chauffage → (4*20)/2 = 40A normalisé."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id=f"c{i}", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5)
        for i in range(4)
    ]
    assert _compute_rcd_amps(circuits) == 40


def test_rcd_amps_heating_summed_not_halved():
    """1× 20A socket + 1× 20A heating → 20/2 + 20 = 30 → arrondi à 40A."""
    from src.planrec.nfc_tableau import _compute_rcd_amps, Circuit, CircuitType
    circuits = [
        Circuit(id="c1", type=CircuitType.SOCKET, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
        Circuit(id="c2", type=CircuitType.HEATING, label="x",
                breaker_amps=20, cable_section_mm2=2.5),
    ]
    assert _compute_rcd_amps(circuits) == 40
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "distribute or rcd_amps" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `_distribute_circuits_to_rcds()` + `_compute_rcd_amps()`**

Append to `src/planrec/nfc_tableau.py`:

```python
_NORMALIZED_RCD_AMPS = [25, 40, 63, 80, 100, 125]


def _ceil_to_normalized(x: float) -> int:
    """Arrondi au calibre normalisé supérieur dans {25, 40, 63, 80, 100, 125}."""
    for cap in _NORMALIZED_RCD_AMPS:
        if x <= cap:
            return cap
    return _NORMALIZED_RCD_AMPS[-1]


def _compute_rcd_amps(circuits: list[Circuit]) -> int:
    """Calibre RCD = (Σ non-chauffage)/2 + Σ chauffage, arrondi normalisé."""
    non_heat = [c for c in circuits if c.type not in
                (CircuitType.HEATING, CircuitType.TOWEL_WARMER)]
    heat = [c for c in circuits if c.type in
            (CircuitType.HEATING, CircuitType.TOWEL_WARMER)]
    raw = sum(c.breaker_amps for c in non_heat) / 2 + sum(c.breaker_amps for c in heat)
    return _ceil_to_normalized(raw)


def _distribute_circuits_to_rcds(
    circuits: list[Circuit],
    n_rcds: int,
) -> list[RCD]:
    """Bin-packing greedy :
    1. RCD1 = Type A → reçoit les circuits requires_type_a (Plaque + LL)
    2. RCD2..N = Type AC → reçoivent le reste
    3. Tri restant par amps décroissant, placement greedy au RCD le moins chargé
    4. Calcul calibre par formule (Σ hors-chauf)/2 + Σ chauf, normalisé
    """
    rcds: list[RCD] = []
    rcds.append(RCD(id=generate_rcd_id(), rcd_type="A", amps=40,
                    sensitivity_ma=30, circuits=[]))
    for _ in range(max(0, n_rcds - 1)):
        rcds.append(RCD(id=generate_rcd_id(), rcd_type="AC", amps=40,
                        sensitivity_ma=30, circuits=[]))

    # Type A obligatoire → RCD1
    type_a_circuits = [c for c in circuits if c.requires_type_a]
    other_circuits = [c for c in circuits if not c.requires_type_a]
    for c in type_a_circuits:
        rcds[0].circuits.append(c)

    # Trier autres par amps décroissant, bin-packing greedy
    sorted_others = sorted(other_circuits, key=lambda c: -c.breaker_amps)
    for c in sorted_others:
        # Choisir le RCD le moins chargé (en nombre de circuits, cap 8)
        candidates = [r for r in rcds if len(r.circuits) < MAX_BREAKERS_PER_RCD]
        if not candidates:
            # Si tous saturés, ajouter un RCD AC supplémentaire
            new_rcd = RCD(id=generate_rcd_id(), rcd_type="AC", amps=40,
                          sensitivity_ma=30, circuits=[])
            rcds.append(new_rcd)
            candidates = [new_rcd]
        target = min(candidates, key=lambda r: len(r.circuits))
        target.circuits.append(c)

    # Recalculer calibre de chaque RCD
    for rcd in rcds:
        rcd.amps = _compute_rcd_amps(rcd.circuits)

    return rcds
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "distribute or rcd_amps" -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "feat(tableau): _distribute_circuits_to_rcds + _compute_rcd_amps

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2.10 — Fonction publique `generate_tableau()` (orchestrateur 7-phase)

**Files:**
- Modify: `src/planrec/nfc_tableau.py`
- Test: `tests/test_nfc_tableau.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_nfc_tableau.py`:

```python
def test_generate_tableau_T3_complete_flow():
    """T3 standard (séjour + 2 chambres + cuisine + SdB + entrée) →
    tableau cohérent : 3 RCD min, Type A contient Plaque + LL, notes RJ45."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "E1", "c2_class": "Entry"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)

    assert tableau.typology == "T3"
    assert tableau.heating_enabled is True
    assert len(tableau.rcds) >= 3
    # Premier RCD est Type A et contient Plaque + LL
    type_a_rcd = tableau.rcds[0]
    assert type_a_rcd.rcd_type == "A"
    labels = [c.label for c in type_a_rcd.circuits]
    assert any("Plaque" in lbl for lbl in labels)
    assert any("Lave-linge" in lbl for lbl in labels)
    # Note RJ45 hors tableau
    assert any("RJ45" in n for n in tableau.notes)


def test_generate_tableau_typology_override():
    """typology_override force la typologie quel que soit le devis."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 20.0},
        {"id": "B1", "c2_class": "BedRoom"},
    ]  # auto = T2
    devis = compute_devis_global(rooms)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True,
                                typology_override="T4")
    assert tableau.typology == "T4"
    assert tableau.typology_source == "user_override"


def test_generate_tableau_heating_disabled_no_heating_circuits():
    """heating_enabled=False → 0 circuits HEATING ni TOWEL_WARMER."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "S1", "c2_class": "Bath"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    all_circuits = [c for r in tableau.rcds for c in r.circuits]
    heating_circuits = [c for c in all_circuits
                        if c.type.value in ("heating", "towel_warmer")]
    assert heating_circuits == []
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "generate_tableau" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `generate_tableau()`**

Append to `src/planrec/nfc_tableau.py`:

```python
def generate_tableau(
    devis_global: DevisGlobal,
    heating_enabled: bool = True,
    typology_override: Optional[str] = None,
) -> Tableau:
    """Orchestre les 7 phases pour produire un Tableau complet."""

    # Phase 0 : typologie + surface
    typology = typology_override or detect_typology(devis_global)
    typology_source = "user_override" if typology_override else "auto"
    surfaces = [d.surface_m2 for d in devis_global.per_room if d.surface_m2]
    surface_m2 = sum(surfaces) if surfaces else None

    notes: list[str] = []
    warnings: list[str] = []

    # Phase 1 : RJ45 hors tableau
    n_rj45 = sum(
        d.items.get(EquipmentType.RJ45, 0) for d in devis_global.per_room
    )
    if n_rj45 > 0:
        notes.append(f"{n_rj45} prises RJ45 → coffret VDI séparé (hors V1 batIA)")

    # Construire les listes par catégorie pour les phases 2/3/4
    rooms_with_lights: list[tuple[str, int]] = []
    rooms_with_sockets: list[tuple[str, int]] = []
    rooms_with_convectors: list[tuple[str, int]] = []
    n_towel_warmers = 0
    spec_counts: dict[EquipmentType, int] = {}

    cat_seen: dict[str, int] = {}
    cat_total: dict[str, int] = {}
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_total[cat] = cat_total.get(cat, 0) + 1
    for d in devis_global.per_room:
        cat = d.nfc_category.value
        cat_seen[cat] = cat_seen.get(cat, 0) + 1
        room_label = f"{cat} {cat_seen[cat]}" if cat_total[cat] > 1 else cat

        n_light = d.items.get(EquipmentType.LIGHT_POINT, 0)
        if n_light > 0:
            rooms_with_lights.append((room_label, n_light))

        n_sock = d.items.get(EquipmentType.SOCKET, 0)
        if n_sock > 0:
            rooms_with_sockets.append((room_label, n_sock))

        n_conv = d.items.get(EquipmentType.CONVECTOR, 0)
        if n_conv > 0:
            rooms_with_convectors.append((room_label, n_conv))

        n_tw = d.items.get(EquipmentType.TOWEL_WARMER, 0)
        n_towel_warmers += n_tw

        for eq_type in (EquipmentType.OVEN, EquipmentType.COOKTOP,
                        EquipmentType.DISHWASHER,
                        EquipmentType.WASHING_MACHINE, EquipmentType.DRYER,
                        EquipmentType.BOILER):
            n_eq = d.items.get(eq_type, 0)
            if n_eq > 0:
                spec_counts[eq_type] = spec_counts.get(eq_type, 0) + n_eq

    # Phase 2-5 : générer circuits
    circuits: list[Circuit] = []
    circuits.extend(_build_lighting_circuits(rooms_with_lights))
    circuits.extend(_build_socket_circuits(rooms_with_sockets))
    if heating_enabled:
        circuits.extend(_build_heating_circuits(rooms_with_convectors,
                                                 n_towel_warmers))
    circuits.extend(_build_specialized_circuits(spec_counts))

    # Phase 6 : nombre min de RCD
    n_rcds = _compute_min_rcds(typology, surface_m2, len(circuits))

    # Phase 7 : répartition sur RCD + calcul calibres
    rcds = _distribute_circuits_to_rcds(circuits, n_rcds)

    # Compteurs visuels
    total_modules = (
        len(circuits)
        + sum(4 for _ in rcds)  # 4 modules par RCD (bloc large)
    )
    n_rails = math.ceil(total_modules / 13)

    return Tableau(
        typology=typology,
        typology_source=typology_source,
        surface_m2=surface_m2,
        heating_enabled=heating_enabled,
        rcds=rcds,
        total_modules=total_modules,
        n_rails=n_rails,
        notes=notes,
        warnings=warnings,
    )
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -v 2>&1 | tail -5`
Expected: tous les tests Phase 2 PASS (~18 tests).

- [ ] **Step 5: Commit**

```bash
git add src/planrec/nfc_tableau.py tests/test_nfc_tableau.py
git commit -m "$(cat <<'EOF'
feat(tableau): generate_tableau() — orchestrateur 7-phase complet

Phases 1-7 du spec V1 :
1. RJ45 hors tableau → notes
2. Bin-packing éclairage 5/circuit 10A
3. Bin-packing prises 12/circuit 20A
4. Chauffage : 2 conv/circuit + 1 SS/circuit (gated heating_enabled)
5. Spécialisés : 1 par appareil (Plaque 32A Type A)
6. Min RCD = max(typo, surface, ceil(N/8))
7. Type A obligatoire pour Plaque+LL, AC pour reste, calibre normalisé

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2.11 — Edge cases : T1 + no kitchen + Phase 2 bilan

**Files:**
- Modify: `src/planrec/nfc_tableau.py` (si bug détecté)
- Test: `tests/test_nfc_tableau.py`
- Modify: `docs/journal/2026-06-02.md`

- [ ] **Step 1: Write failing tests pour edge cases**

Append to `tests/test_nfc_tableau.py`:

```python
def test_edge_case_T1_studio_one_rcd_type_A():
    """T1 studio (séjour seul + cuisine + SdB) → 1 RCD Type A unique contenant
    Plaque + LL + tout le reste."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tableau = generate_tableau(devis_global=devis, heating_enabled=True)
    assert tableau.typology == "T1"
    # >8 circuits forcent +1 RCD au-delà du min
    assert len(tableau.rcds) >= 1
    assert tableau.rcds[0].rcd_type == "A"


def test_edge_case_no_kitchen_no_type_a_required():
    """Logement sans cuisine ni LL → pas de circuit requires_type_a → RCD1
    reste Type A mais vide de circuits obligatoires."""
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0}]
    devis = compute_devis_global(rooms, heating_enabled=False)
    tableau = generate_tableau(devis_global=devis, heating_enabled=False)
    type_a_circuits = [c for r in tableau.rcds for c in r.circuits
                       if c.requires_type_a]
    assert type_a_circuits == []
```

- [ ] **Step 2: Run tests, verify PASS or fix**

Run: `.venv/bin/python -m pytest tests/test_nfc_tableau.py -k "edge_case" -v`
Si FAIL : identifier le bug dans `generate_tableau()` ou `_distribute_circuits_to_rcds()` et corriger. Sinon PASS.

- [ ] **Step 3: Run full pytest suite**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -5`
Expected: ~88 tests PASS (62 existants + ~18 nouveaux Phase 2 + ~8 Phase 1).

- [ ] **Step 4: Append Phase 2 summary au journal**

Append to `docs/journal/2026-06-02.md`:

```markdown

## Tableau électrique V1 — Phase 2 livrée (algo nfc_tableau)

**Contexte** : module Python pur `src/planrec/nfc_tableau.py` implémentant
les 7 phases du spec (typologie, circuits, RCD, calibrage).

**Mise en œuvre** : 11 tasks TDD strict, ~18 tests pytest verts.

| Task | Sujet | Tests cumulés |
|------|-------|---------------|
| 2.1 | CircuitType enum + Circuit dataclass | 2 |
| 2.2 | RCD + Tableau dataclasses | 4 |
| 2.3 | detect_typology() | 8 |
| 2.4 | _build_lighting_circuits() | 10 |
| 2.5 | _build_socket_circuits() | 13 |
| 2.6 | _build_heating_circuits() | 16 |
| 2.7 | _build_specialized_circuits() | 19 |
| 2.8 | _compute_min_rcds() | 22 |
| 2.9 | _distribute + _compute_rcd_amps | 26 |
| 2.10 | generate_tableau() orchestration | 29 |
| 2.11 | Edge cases T1 + no kitchen | 31 |

**Résultat** : Phase 2 ✅ — ~88 tests verts total. Module testable pytest
pur prêt pour intégration rendu Phase 3.
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_nfc_tableau.py src/planrec/nfc_tableau.py docs/journal/2026-06-02.md
git commit -m "$(cat <<'EOF'
feat(tableau): edge cases T1/no-kitchen + bilan Phase 2

Phase 2 livrée : nfc_tableau.py complet, 7 phases d'algo testées par
~18 tests pytest. ~88 tests total dans la suite (Phase 1 + Phase 2 +
baseline).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — `tableau_renderer.py` (SVG inline + liste HTML)

### Task 3.1 — Setup module + `CIRCUIT_COLORS` + signature `render_svg()`

**Files:**
- Create: `src/planrec/tableau_renderer.py`
- Create: `tests/test_tableau_renderer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_tableau_renderer.py
"""Tests pour tableau_renderer (rendu SVG + HTML + PDF du tableau)."""
from __future__ import annotations


def test_render_svg_returns_str_starting_with_svg():
    """render_svg sortie commence par '<svg' (string XML)."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import Tableau
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0,
                    n_rails=0, notes=[], warnings=[])
    out = render_svg(empty)
    assert isinstance(out, str)
    assert out.startswith("<svg") or out.startswith("<div")


def test_circuit_colors_constants_present():
    """CIRCUIT_COLORS contient les 7 CircuitType avec hex couleur."""
    from src.planrec.tableau_renderer import CIRCUIT_COLORS
    from src.planrec.nfc_tableau import CircuitType
    for ct in CircuitType:
        assert ct in CIRCUIT_COLORS
        assert CIRCUIT_COLORS[ct].startswith("#")
        assert len(CIRCUIT_COLORS[ct]) == 7
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Créer le module**

Créer `src/planrec/tableau_renderer.py` :

```python
"""Rendu visuel du Tableau électrique : SVG inline (Streamlit st.markdown) +
liste HTML descriptive + export PDF A4 (reportlab).

Aucun import Streamlit ou React — module testable pytest seul.
"""
from __future__ import annotations

from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType


# Couleurs par fonction de circuit (cohérent palette équipements)
CIRCUIT_COLORS: dict[CircuitType, str] = {
    CircuitType.LIGHTING:        "#FFD54F",  # jaune
    CircuitType.SOCKET:          "#42A5F5",  # bleu
    CircuitType.KITCHEN_SPECIAL: "#AB47BC",  # violet
    CircuitType.LAUNDRY:         "#FF7043",  # orange
    CircuitType.BOILER:          "#C62828",  # rouge sombre
    CircuitType.HEATING:         "#EF5350",  # rouge clair
    CircuitType.TOWEL_WARMER:    "#EF9A9A",  # rose clair
}


# Dimensions SVG (cf. spec section 5)
MODULE_W = 60
MODULE_H = 100
RCD_BLOCK_W = 240  # 4 modules de large
RCD_AVAILABLE_SLOTS = 18  # max modules par rangée


def render_svg(tableau: Tableau) -> str:
    """Génère le SVG complet du tableau comme string XML.

    Sortie embarquable dans `st.markdown(svg_xml, unsafe_allow_html=True)`.
    """
    if not tableau.rcds:
        return '<div style="padding:1em;color:#888">Aucun circuit à afficher.</div>'

    n_rcds = len(tableau.rcds)
    width = RCD_BLOCK_W + RCD_AVAILABLE_SLOTS * MODULE_W
    height = n_rcds * MODULE_H + 30  # 30 px header

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'style="background:#FAFAFA; font-family:Inter,sans-serif">',
        f'<text x="10" y="20" font-size="14" font-weight="bold">'
        f'Tableau électrique — Logement {tableau.typology}</text>',
    ]

    for i, rcd in enumerate(tableau.rcds):
        y = 30 + i * MODULE_H
        parts.append(_render_rcd_row(rcd, y))

    parts.append('</svg>')
    return "".join(parts)


def _render_rcd_row(rcd: RCD, y: int) -> str:
    """Une rangée RCD = bloc ID + N modules disjoncteur."""
    parts: list[str] = []

    # Bloc RCD (gauche, fond blanc bord noir épais)
    parts.append(
        f'<rect x="0" y="{y}" width="{RCD_BLOCK_W}" height="{MODULE_H}" '
        f'fill="white" stroke="#000" stroke-width="2"/>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 25}" font-size="12" '
        f'font-weight="bold" text-anchor="middle">ID {rcd.amps} A</text>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 45}" font-size="11" '
        f'text-anchor="middle">Type {rcd.rcd_type}</text>'
        f'<text x="{RCD_BLOCK_W // 2}" y="{y + 62}" font-size="10" '
        f'text-anchor="middle">{rcd.sensitivity_ma} mA</text>'
    )

    # Modules disjoncteur (droite)
    for j, circuit in enumerate(rcd.circuits):
        x = RCD_BLOCK_W + j * MODULE_W
        parts.append(_render_module(circuit, x, y))

    return "".join(parts)


def _render_module(circuit: Circuit, x: int, y: int) -> str:
    """Un module disjoncteur."""
    color = CIRCUIT_COLORS.get(circuit.type, "#CCCCCC")
    type_a_marker = "*" if circuit.requires_type_a else ""
    short_label = (circuit.label[:9] + "…") if len(circuit.label) > 10 else circuit.label
    return (
        f'<rect x="{x}" y="{y}" width="{MODULE_W}" height="{MODULE_H}" '
        f'fill="{color}" stroke="#37474F" stroke-width="1"/>'
        f'<text x="{x + MODULE_W // 2}" y="{y + 20}" font-size="14" '
        f'font-weight="bold" text-anchor="middle" fill="#000">'
        f'{circuit.breaker_amps}A{type_a_marker}</text>'
        f'<text x="{x + MODULE_W // 2}" y="{y + 55}" font-size="9" '
        f'text-anchor="middle" fill="#000">{short_label}</text>'
        f'<text x="{x + MODULE_W // 2}" y="{y + 80}" font-size="8" '
        f'font-style="italic" text-anchor="middle" fill="#37474F">'
        f'{circuit.cable_section_mm2} mm²</text>'
    )
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -v`
Expected: 2/2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planrec/tableau_renderer.py tests/test_tableau_renderer.py
git commit -m "feat(tableau): tableau_renderer setup + render_svg() base

Module pur Python : CIRCUIT_COLORS + render_svg() + _render_rcd_row +
_render_module. Sortie string XML embarquable st.markdown.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3.2 — `render_svg()` contient bien tous les circuits

**Files:**
- Test: `tests/test_tableau_renderer.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_tableau_renderer.py`:

```python
def test_render_svg_contains_all_circuits_as_rect():
    """Tous les circuits sont rendus comme rect colorés."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    svg = render_svg(tab)

    total_circuits = sum(len(r.circuits) for r in tab.rcds)
    # 1 rect par module + 1 rect par bloc RCD = total_circuits + n_rcds rect "principaux"
    n_rect = svg.count("<rect")
    assert n_rect >= total_circuits + len(tab.rcds)


def test_render_svg_well_formed_xml():
    """SVG output parseable comme XML."""
    import xml.etree.ElementTree as ET
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0}]
    devis = compute_devis_global(rooms)
    tab = generate_tableau(devis_global=devis, heating_enabled=False)
    svg = render_svg(tab)
    # Parse — si malformed, ParseError
    ET.fromstring(svg)


def test_render_svg_dimensions_scale_with_n_rcds():
    """Hauteur SVG croît avec le nombre de RCD."""
    from src.planrec.tableau_renderer import render_svg
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    small_rooms = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}]
    big_rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "B3", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "S1", "c2_class": "Bath"},
        {"id": "T1", "c2_class": "Storage"},
    ]
    svg_small = render_svg(generate_tableau(
        compute_devis_global(small_rooms, heating_enabled=False),
        heating_enabled=False,
    ))
    svg_big = render_svg(generate_tableau(
        compute_devis_global(big_rooms, heating_enabled=True),
        heating_enabled=True,
    ))
    h_small = int(svg_small.split('height="')[1].split('"')[0])
    h_big = int(svg_big.split('height="')[1].split('"')[0])
    assert h_big > h_small
```

- [ ] **Step 2: Run tests, verify PASS (implémentation Task 3.1 suffit)**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -v`
Expected: 5/5 PASS. Si fail, ajuster `render_svg()`.

- [ ] **Step 3: Commit (tests seuls si rien à modifier)**

```bash
git add tests/test_tableau_renderer.py
git commit -m "test(tableau): coverage rendu SVG (rect, XML well-formed, scaling)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3.3 — `render_html_table()` : liste descriptive circuits

**Files:**
- Modify: `src/planrec/tableau_renderer.py`
- Test: `tests/test_tableau_renderer.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_tableau_renderer.py`:

```python
def test_render_html_table_one_row_per_circuit():
    """Une ligne <tr> par circuit + 1 row header."""
    from src.planrec.tableau_renderer import render_html_table
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    html = render_html_table(tab)

    total_circuits = sum(len(r.circuits) for r in tab.rcds)
    # header + total_circuits rows
    n_tr = html.count("<tr")
    assert n_tr == total_circuits + 1


def test_render_html_table_contains_breaker_amps_and_section():
    """Le HTML mentionne calibre + section câble."""
    from src.planrec.tableau_renderer import render_html_table
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global

    rooms = [{"id": "K1", "c2_class": "Kitchen"}]
    devis = compute_devis_global(rooms)
    tab = generate_tableau(devis_global=devis)
    html = render_html_table(tab)
    assert "32 A" in html or "32A" in html  # Plaque
    assert "6 mm²" in html or "6.0 mm²" in html or "6.0mm" in html
```

- [ ] **Step 2: Run tests, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -k "render_html" -v`
Expected: FAIL.

- [ ] **Step 3: Implémenter `render_html_table()`**

Append to `src/planrec/tableau_renderer.py`:

```python
def render_html_table(tableau: Tableau) -> str:
    """Liste HTML descriptive de tous les circuits."""
    parts: list[str] = [
        '<table style="width:100%; border-collapse:collapse; '
        'font-family:Inter,sans-serif; font-size:13px">',
        '<tr style="background:#37474F; color:white">'
        '<th style="padding:6px; text-align:left">ID</th>'
        '<th style="padding:6px; text-align:left">Type</th>'
        '<th style="padding:6px; text-align:right">Calibre</th>'
        '<th style="padding:6px; text-align:right">Section</th>'
        '<th style="padding:6px; text-align:left">Pièces alimentées</th>'
        '</tr>',
    ]

    row_idx = 0
    type_labels_fr = {
        CircuitType.LIGHTING: "Éclairage",
        CircuitType.SOCKET: "Prises",
        CircuitType.KITCHEN_SPECIAL: "Cuisine spé",
        CircuitType.LAUNDRY: "Buanderie",
        CircuitType.BOILER: "Chaudière",
        CircuitType.HEATING: "Chauffage",
        CircuitType.TOWEL_WARMER: "Sèche-serv.",
    }
    for rcd in tableau.rcds:
        for circuit in rcd.circuits:
            bg = "#F5F5F5" if row_idx % 2 == 0 else "white"
            type_label = type_labels_fr.get(circuit.type, "—")
            rooms_str = ", ".join(circuit.rooms_served) or "—"
            type_a_marker = " *" if circuit.requires_type_a else ""
            parts.append(
                f'<tr style="background:{bg}">'
                f'<td style="padding:6px">ID {tableau.rcds.index(rcd)+1} '
                f'Type {rcd.rcd_type}</td>'
                f'<td style="padding:6px">{circuit.label}{type_a_marker}</td>'
                f'<td style="padding:6px; text-align:right">'
                f'{circuit.breaker_amps} A</td>'
                f'<td style="padding:6px; text-align:right">'
                f'{circuit.cable_section_mm2} mm²</td>'
                f'<td style="padding:6px">{rooms_str}</td>'
                f'</tr>'
            )
            row_idx += 1

    parts.append('</table>')
    parts.append(
        '<p style="font-size:11px; color:#888; margin-top:4px">'
        '* = Type A obligatoire</p>'
    )
    return "".join(parts)
```

- [ ] **Step 4: Run tests, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -v`
Expected: tous PASS (~5-6 tests Phase 3).

- [ ] **Step 5: Commit**

```bash
git add src/planrec/tableau_renderer.py tests/test_tableau_renderer.py
git commit -m "feat(tableau): render_html_table() descriptif circuits

Une ligne par circuit avec ID/Type/Calibre/Section/Pièces, alternance
de fond pour lisibilité, marqueur * pour Type A.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 3.4 — Bilan Phase 3 + journal

**Files:**
- Modify: `docs/journal/2026-06-02.md`

- [ ] **Step 1: Append Phase 3 summary au journal**

Append to `docs/journal/2026-06-02.md`:

```markdown

## Tableau électrique V1 — Phase 3 livrée (rendu SVG + HTML)

**Contexte** : module `tableau_renderer.py` produit string SVG embarquable
dans st.markdown + tableau HTML descriptif.

**Mise en œuvre** : 4 tasks TDD strict, ~6 tests pytest verts.

| Task | Sujet |
|------|-------|
| 3.1 | Setup module + CIRCUIT_COLORS + render_svg base |
| 3.2 | Tests coverage rendu SVG |
| 3.3 | render_html_table() descriptif circuits |
| 3.4 | Bilan + journal |

**Résultat** : Phase 3 ✅ — rendu visuel prêt à intégrer Streamlit en Phase 5.
```

- [ ] **Step 2: Commit**

```bash
git add docs/journal/2026-06-02.md
git commit -m "docs(journal): bilan Phase 3 tableau électrique — rendu SVG + HTML

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 4 — `tableau_renderer.py` (export PDF reportlab)

### Task 4.1 — `export_pdf()` : structure A4 portrait

**Files:**
- Modify: `src/planrec/tableau_renderer.py`
- Test: `tests/test_tableau_renderer.py`

- [ ] **Step 1: Install reportlab + pypdf si manquants**

Run: `.venv/bin/pip show reportlab pypdf 2>&1 | grep -E "Name|not found"`
Si manquant : `.venv/bin/pip install reportlab pypdf`

- [ ] **Step 2: Write failing test**

Append to `tests/test_tableau_renderer.py`:

```python
def test_export_pdf_returns_valid_bytes():
    """export_pdf retourne des bytes parseables comme PDF."""
    from src.planrec.tableau_renderer import export_pdf
    from src.planrec.nfc_tableau import generate_tableau
    from src.planrec.nfc_rules import compute_devis_global
    import io
    from pypdf import PdfReader

    rooms = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "K1", "c2_class": "Kitchen"},
    ]
    devis = compute_devis_global(rooms, heating_enabled=True)
    tab = generate_tableau(devis_global=devis, heating_enabled=True)
    pdf_bytes = export_pdf(tab)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    text = reader.pages[0].extract_text()
    assert "Tableau" in text or "tableau" in text.lower()
```

- [ ] **Step 3: Run test, verify FAIL**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -k "export_pdf" -v`
Expected: FAIL `ImportError`.

- [ ] **Step 4: Implémenter `export_pdf()`**

Append to `src/planrec/tableau_renderer.py`:

```python
def export_pdf(tableau: Tableau) -> bytes:
    """Génère un PDF A4 portrait : header + schéma + liste circuits + footer."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20 * mm, page_h - 20 * mm,
                 f"batIA · Tableau électrique · {tableau.typology}")
    c.setFont("Helvetica", 9)
    from datetime import date
    c.drawString(20 * mm, page_h - 27 * mm,
                 f"Date : {date.today().isoformat()}  ·  "
                 f"Logement : {tableau.typology}  ·  "
                 f"Chauffage : {'oui' if tableau.heating_enabled else 'non'}")

    # Schéma simplifié (rectangles colorés)
    y_cursor = page_h - 45 * mm
    mod_w_mm = 8 * mm
    mod_h_mm = 14 * mm
    rcd_w_mm = 32 * mm
    for rcd in tableau.rcds:
        # Bloc RCD
        c.setStrokeColor(colors.black)
        c.setFillColor(colors.white)
        c.rect(20 * mm, y_cursor - mod_h_mm, rcd_w_mm, mod_h_mm,
               stroke=1, fill=1)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 5 * mm,
                            f"ID {rcd.amps} A")
        c.setFont("Helvetica", 7)
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 9 * mm,
                            f"Type {rcd.rcd_type}")
        c.drawCentredString(20 * mm + rcd_w_mm / 2, y_cursor - 12 * mm,
                            f"{rcd.sensitivity_ma} mA")

        # Modules
        for j, circ in enumerate(rcd.circuits):
            x = 20 * mm + rcd_w_mm + j * mod_w_mm
            hex_color = CIRCUIT_COLORS.get(circ.type, "#CCCCCC")
            c.setFillColor(colors.HexColor(hex_color))
            c.setStrokeColor(colors.HexColor("#37474F"))
            c.rect(x, y_cursor - mod_h_mm, mod_w_mm, mod_h_mm,
                   stroke=1, fill=1)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 7)
            c.drawCentredString(x + mod_w_mm / 2, y_cursor - 4 * mm,
                                f"{circ.breaker_amps}A")
            c.setFont("Helvetica", 6)
            short = circ.label[:8]
            c.drawCentredString(x + mod_w_mm / 2, y_cursor - 9 * mm, short)

        y_cursor -= mod_h_mm + 2 * mm

    # Liste circuits (textuelle)
    y_cursor -= 8 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y_cursor, "Détail des circuits")
    y_cursor -= 6 * mm
    c.setFont("Helvetica", 8)
    for rcd in tableau.rcds:
        for circ in rcd.circuits:
            line = (
                f"ID {tableau.rcds.index(rcd)+1} Type {rcd.rcd_type} | "
                f"{circ.label} | {circ.breaker_amps} A | "
                f"{circ.cable_section_mm2} mm² | "
                f"{', '.join(circ.rooms_served) or '—'}"
            )
            c.drawString(20 * mm, y_cursor, line[:120])
            y_cursor -= 4 * mm
            if y_cursor < 30 * mm:
                c.showPage()
                y_cursor = page_h - 20 * mm

    # Footer
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(20 * mm, 15 * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. "
                 "Sections câbles indicatives. L'artisan valide la conformité finale.")

    c.save()
    return buf.getvalue()
```

- [ ] **Step 5: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_tableau_renderer.py -k "export_pdf" -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/planrec/tableau_renderer.py tests/test_tableau_renderer.py
git commit -m "$(cat <<'EOF'
feat(tableau): export_pdf() A4 portrait reportlab

Schéma modulaire (rangées avec bloc RCD + modules colorés) + liste
textuelle des circuits + footer NFC. Bytes parseables pypdf.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4.2 — Bilan Phase 4 + journal

**Files:**
- Modify: `docs/journal/2026-06-02.md`

- [ ] **Step 1: Append Phase 4 summary**

Append to `docs/journal/2026-06-02.md`:

```markdown

## Tableau électrique V1 — Phase 4 livrée (export PDF)

**Contexte** : `export_pdf(tableau) → bytes` génère un PDF A4 portrait
avec schéma modulaire + liste textuelle des circuits + footer NFC.

**Mise en œuvre** : 2 tasks TDD strict, validation pypdf parsing.

**Résultat** : Phase 4 ✅ — Tableau renderer complet (SVG + HTML + PDF).
```

- [ ] **Step 2: Commit**

```bash
git add docs/journal/2026-06-02.md
git commit -m "docs(journal): bilan Phase 4 tableau électrique — PDF

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 5 — Intégration Streamlit + AppTest

### Task 5.1 — Sidebar : toggle chauffage + override typologie

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Identifier le bloc sidebar dans `streamlit_app.py`**

Run: `grep -n "with st.sidebar\|st.sidebar.subheader\|🔌 \|⚙️" app/streamlit_app.py | head -10`

Localiser la fin du bloc sidebar existant (probablement après la section équipements V1).

- [ ] **Step 2: Ajouter le bloc Sidebar Tableau électrique**

Après le dernier widget sidebar existant, insérer :

```python
    # ---- Sidebar V1.2 : Tableau électrique ----
    st.subheader("⚡ Tableau électrique")
    heating_enabled = st.toggle(
        "Chauffage électrique",
        value=True,
        key="tableau_heating_enabled",
        help="Si actif, batIA ajoute 1 convecteur 2000W par pièce "
             "principale et 1 sèche-serviettes par SdB."
    )
    with st.expander("Forcer typologie", expanded=False):
        typology_override = st.selectbox(
            "Typologie",
            [None, "T1", "T2", "T3", "T4", "T5"],
            index=0,
            key="tableau_typology_override",
            help="Par défaut auto-détectée depuis les pièces."
        )
```

Localiser ces variables dans le scope où elles seront utilisées par la section principale (idéalement en haut du `main()`).

- [ ] **Step 3: Run AppTest baseline pour vérifier non-régression**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py -v 2>&1 | tail -5`
Expected: tous tests anciens passent (sidebar ajoute des widgets mais ne casse rien).

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(streamlit): sidebar tableau électrique (toggle chauffage + override typo)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.2 — Section principale "Tableau électrique" en bas de page

**Files:**
- Modify: `app/streamlit_app.py`

- [ ] **Step 1: Identifier le bas de la page (après section devis)**

Run: `grep -n "Devis\|st.download_button\|st.dataframe.*devis\|generate_devis" app/streamlit_app.py | tail -10`

Trouver la fin du bloc devis (typiquement juste avant les commentaires d'imports résiduels ou après le dernier `st.markdown("---")`).

- [ ] **Step 2: Ajouter la section Tableau électrique gated**

Après la section devis, insérer :

```python
    # ---- Section V1.2 : Tableau électrique ----
    if st.session_state.get(_devis_triggered_key):
        from src.planrec import nfc_tableau as _nfc_tab
        from src.planrec import tableau_renderer as _tab_render

        st.markdown("---")
        st.subheader("⚡ Tableau électrique")

        tableau = _nfc_tab.generate_tableau(
            devis_global=devis_global,
            heating_enabled=heating_enabled,
            typology_override=typology_override,
        )

        # Bandeau de notes / warnings
        for note in tableau.notes:
            st.info(note)
        for warning in tableau.warnings:
            st.warning(warning)

        # Schéma modulaire SVG
        svg_xml = _tab_render.render_svg(tableau)
        st.markdown(svg_xml, unsafe_allow_html=True)

        # Liste circuits HTML
        st.markdown("**Détail des circuits**")
        html_circuits = _tab_render.render_html_table(tableau)
        st.markdown(html_circuits, unsafe_allow_html=True)

        # PDF download
        pdf_bytes = _tab_render.export_pdf(tableau)
        st.download_button(
            "📄 Télécharger le tableau (PDF A4)",
            data=pdf_bytes,
            file_name=f"tableau_electrique_{tableau.typology}_{img_hash[:8]}.pdf",
            mime="application/pdf",
            key="dl_tableau_pdf",
        )
```

Assure-toi que `devis_global`, `heating_enabled`, `typology_override`, `img_hash`, `_devis_triggered_key` sont accessibles dans le scope.

- [ ] **Step 3: Run AppTest baseline**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py -v 2>&1 | tail -5`
Expected: tests anciens passent.

- [ ] **Step 4: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(streamlit): section tableau électrique en bas de page (gated trigger devis)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.3 — AppTest T1 : le tableau apparaît après "Générer devis"

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py`:

```python
def test_T1_tableau_appears_after_devis_trigger(patch_pipeline):
    """T1 : après click 'Générer devis', la subheader '⚡ Tableau électrique'
    apparaît."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    headers = [h.value for h in at.subheader]
    assert any("Tableau électrique" in h for h in headers)
```

- [ ] **Step 2: Run test, verify PASS (la section est gated correctement)**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py::test_T1_tableau_appears_after_devis_trigger -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_devis_apptest.py
git commit -m "test(apptest): T1 tableau apparaît après trigger devis

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.4 — AppTest T2 : toggle heating OFF supprime circuits chauffage

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py`:

```python
def test_T2_toggle_heating_off_no_heating_circuits(patch_pipeline):
    """T2 : désactiver chauffage → l'HTML de la liste ne contient pas
    'Convecteur' ni 'Sèche-serviettes'."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    toggle = next(t for t in at.toggle
                  if "Chauffage" in t.label)
    toggle.set_value(False).run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    # Concat tous les markdown pour grep
    all_md = "\n".join(m.value for m in at.markdown if m.value)
    assert "Convecteur" not in all_md
    assert "Sèche-serviettes" not in all_md
```

- [ ] **Step 2: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py::test_T2_toggle_heating_off_no_heating_circuits -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_devis_apptest.py
git commit -m "test(apptest): T2 toggle chauffage OFF supprime circuits chauffage

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.5 — AppTest T3 : un T3 a au moins 3 RCD dans le HTML

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py`:

```python
def test_T3_logement_has_at_least_3_rcds(patch_pipeline):
    """T3 (séjour + 2 chambres) → au moins 3 RCD distincts dans la liste
    HTML des circuits."""
    # Patch pipeline pour fournir 3 pièces (LivingRoom + 2 BedRoom)
    fixture = [
        {"id": "L1", "c2_class": "LivingRoom", "surface_m2": 25.0},
        {"id": "B1", "c2_class": "BedRoom"},
        {"id": "B2", "c2_class": "BedRoom"},
        {"id": "K1", "c2_class": "Kitchen"},
        {"id": "T1", "c2_class": "Storage"},
        {"id": "S1", "c2_class": "Bath"},
    ]
    patch_pipeline(rooms=fixture)
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    all_md = "\n".join(m.value for m in at.markdown if m.value)
    # Compter occurrences ID 1, ID 2, ID 3 dans le HTML
    import re
    ids_found = set(re.findall(r"ID\s+(\d+)\s+Type", all_md))
    assert {"1", "2", "3"}.issubset(ids_found)
```

- [ ] **Step 2: Vérifier que `patch_pipeline` supporte `rooms=` param**

Si `tests/conftest.py` ne le supporte pas, adapter la fixture pour accepter un override des rooms (ou utiliser un fixture séparé). Sinon, hardcoder dans le test en utilisant un fixture patché localement.

- [ ] **Step 3: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py::test_T3_logement_has_at_least_3_rcds -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_devis_apptest.py tests/conftest.py
git commit -m "test(apptest): T3 logement a >=3 RCD dans la liste HTML

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.6 — AppTest T4 : bouton "Télécharger PDF" présent et fonctionnel

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py`:

```python
def test_T4_pdf_download_button_present_and_returns_bytes(patch_pipeline):
    """T4 : bouton download PDF existe et son data est bien des bytes PDF."""
    patch_pipeline()
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()
    find_button_by_label(at, "générer devis").click()
    at.run()

    dl_buttons = at.download_button
    pdf_btn = next(b for b in dl_buttons
                   if "PDF" in b.label or "tableau" in b.label.lower())
    assert pdf_btn is not None
    assert pdf_btn.data is not None
    assert isinstance(pdf_btn.data, bytes)
    assert pdf_btn.data.startswith(b"%PDF-")
```

- [ ] **Step 2: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py::test_T4_pdf_download_button_present_and_returns_bytes -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_devis_apptest.py
git commit -m "test(apptest): T4 bouton download PDF présent et fonctionnel

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.7 — AppTest T5 : override typologie change le nb de RCD

**Files:**
- Modify: `tests/test_devis_apptest.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_devis_apptest.py`:

```python
def test_T5_typology_override_changes_n_rcds(patch_pipeline):
    """T5 : forcer typology=T4 sur un logement T1 (séjour seul) augmente le
    nombre de RCD affichés."""
    fixture = [{"id": "L1", "c2_class": "LivingRoom", "surface_m2": 30.0}]
    patch_pipeline(rooms=fixture)
    at = AppTest.from_file(APP_FILE, default_timeout=TIMEOUT)
    at.run()

    # Override typologie à T4
    selectbox = next(s for s in at.selectbox
                     if s.key == "tableau_typology_override")
    selectbox.set_value("T4").run()

    find_button_by_label(at, "générer devis").click()
    at.run()

    all_md = "\n".join(m.value for m in at.markdown if m.value)
    import re
    ids = set(re.findall(r"ID\s+(\d+)\s+Type", all_md))
    # T4 force au moins 4 RCD
    assert len(ids) >= 4 or {"1", "2", "3", "4"}.issubset(ids)
```

- [ ] **Step 2: Run test, verify PASS**

Run: `.venv/bin/python -m pytest tests/test_devis_apptest.py::test_T5_typology_override_changes_n_rcds -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_devis_apptest.py
git commit -m "test(apptest): T5 override typologie change nb RCD

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5.8 — Bilan Phase 5 + verify all tests + journal

**Files:**
- Modify: `docs/journal/2026-06-02.md`

- [ ] **Step 1: Run full pytest suite**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -5`
Expected: ~95 tests PASS (62 baseline + 8 Phase 1 + 18 Phase 2 + 6 Phase 3 + 1 Phase 4 + 5 Phase 5).

- [ ] **Step 2: Append Phase 5 summary au journal**

Append to `docs/journal/2026-06-02.md`:

```markdown

## Tableau électrique V1 — Phase 5 livrée (intégration Streamlit + AppTest)

**Contexte** : intégration UI complète + 5 AppTest E2E.

**Mise en œuvre** : 8 tasks (2 UI + 5 AppTest + 1 bilan).

| Task | Sujet |
|------|-------|
| 5.1 | Sidebar : toggle chauffage + override typo |
| 5.2 | Section principale en bas de page |
| 5.3 | AppTest T1 : tableau apparaît |
| 5.4 | AppTest T2 : toggle chauffage OFF |
| 5.5 | AppTest T3 : T3 = 3 RCD |
| 5.6 | AppTest T4 : PDF download |
| 5.7 | AppTest T5 : override typologie |
| 5.8 | Bilan + tests verts |

**Résultat** : Phase 5 ✅ — ~95 tests verts total. UI démo prête.
```

- [ ] **Step 3: Commit**

```bash
git add docs/journal/2026-06-02.md
git commit -m "docs(journal): bilan Phase 5 tableau électrique — intégration + AppTest

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Phase 6 — Polish + journal final + spec coverage

### Task 6.1 — Vérification visuelle en local (streamlit run)

**Files:** aucune

- [ ] **Step 1: Démarrer l'app Streamlit**

Run: `.venv/bin/streamlit run app/streamlit_app.py`
Ouvrir http://localhost:8501.

- [ ] **Step 2: Test golden path**

1. Upload un plan (utiliser un PNG de `data/raw/plans_fr/`)
2. Activer toggle "Chauffage électrique" dans sidebar
3. Cliquer "Générer devis"
4. Scroller en bas
5. Vérifier que la section "⚡ Tableau électrique" apparaît avec :
   - Schéma SVG visible (rangées colorées)
   - Note RJ45 hors tableau
   - Liste descriptive des circuits
   - Bouton "Télécharger PDF"
6. Cliquer le bouton, ouvrir le PDF dans Preview/Chrome, vérifier le rendu

- [ ] **Step 3: Test edge cases**

1. Désactiver chauffage → vérifier disparition Convecteur/Sèche-serv. dans la liste
2. Forcer typologie T5 sur un studio → vérifier 5 RCD au moins
3. Re-activer chauffage → vérifier réapparition

- [ ] **Step 4: Si bug visuel → fix + commit**

Si quelque chose ne s'affiche pas comme attendu, identifier le bug, fix, run pytest, re-test.

---

### Task 6.2 — Spec coverage check

**Files:** aucune

- [ ] **Step 1: Re-lire la spec**

Run: `cat docs/superpowers/specs/2026-06-02-tableau-electrique-design.md | wc -l`
Lire chaque section et vérifier qu'une task correspondante existe dans ce plan :

- ✅ Vue d'ensemble : Phase 1 + Phase 2 + Phase 3 + Phase 4
- ✅ Refactor EquipmentType : Phase 1 (tasks 1.1-1.8)
- ✅ Algo greedy 7-phase : Phase 2 (tasks 2.3-2.11)
- ✅ Règles métier (calibres, sections, max appareils) : implicites dans tasks 2.4-2.7
- ✅ Rendu SVG + couleurs : Phase 3 (tasks 3.1-3.3)
- ✅ Export PDF : Phase 4 (task 4.1)
- ✅ UI Streamlit : Phase 5 (tasks 5.1-5.2)
- ✅ Tests pytest + AppTest : couvert par chaque phase
- ✅ 8 nouveaux SVG icônes : task 1.9

- [ ] **Step 2: Si gap identifié → ajouter task de rattrapage**

Si une section de la spec n'a pas de task → écrire une mini-task de rattrapage.

---

### Task 6.3 — Bilan final + journal + push

**Files:**
- Modify: `docs/journal/2026-06-02.md`

- [ ] **Step 1: Run full pytest suite final**

Run: `.venv/bin/python -m pytest -v 2>&1 | tail -3`
Expected: ~95+ tests PASS, 0 FAIL, 0 ERROR.

- [ ] **Step 2: Append bilan final au journal**

Append to `docs/journal/2026-06-02.md`:

```markdown

## Tableau électrique V1 — Bilan global

**Phases 1-6 livrées** :
- Phase 1 ✅ Refactor EquipmentType (8 nouveaux types) + 8 SVG icônes
- Phase 2 ✅ Module nfc_tableau (algo greedy 7-phase, 18 tests)
- Phase 3 ✅ Rendu SVG + liste HTML
- Phase 4 ✅ Export PDF reportlab
- Phase 5 ✅ Intégration Streamlit + 5 AppTest E2E
- Phase 6 ✅ Vérif visuelle + spec coverage + bilan

**Résultat** : Feature livrée. ~95 tests verts. Démo prête pour artisan FR.

**Prochaines pistes V2** :
- Schéma unifilaire NFC §10
- Estimation longueurs câble + chute tension (nécessite position tableau sur plan)
- Coffret VDI (RJ45) représenté
- Édition utilisateur (drag modules entre RCD, renommage labels)
- Borne IRVE, parafoudre, contacteur HC/HP
- Triphasé 400V
```

- [ ] **Step 3: Commit + push**

```bash
git add docs/journal/2026-06-02.md
git commit -m "$(cat <<'EOF'
docs(journal): bilan global tableau électrique V1 livré

6 phases complètes (~40 tasks), ~95 tests verts. Module Python pur +
rendu SVG/PDF + intégration Streamlit + AppTest T1-T5. Démo prête.

Prochaines pistes V2 listées : schéma unifilaire, longueurs câble,
coffret VDI, édition user, IRVE, parafoudre, triphasé.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)" && git push origin main
```

---

## Annexe — checklist de revue avant ship

- [ ] 95+ tests pytest tous verts
- [ ] Démo manuelle : golden path + 2 edge cases OK
- [ ] PDF généré ouvert dans Preview macOS + Chrome
- [ ] SVG rendu correctement dans Streamlit (pas de sanitization HTML)
- [ ] Journal `docs/journal/2026-06-02.md` à jour
- [ ] Working tree clean, push origin/main
- [ ] Spec coverage check : chaque section spec a une task correspondante
