# Schéma unifilaire — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire un 3e livrable PDF — le schéma unifilaire du tableau électrique (cible dossier Consuel) — en complément des PDF tableau et étiquettes, avec un bouton de téléchargement dédié.

**Architecture:** Nouveau module pur `src/planrec/schema_unifilaire.py` (reportlab + svglib, aucun import Streamlit) consommant `Tableau/RCD/Circuit` tel quel. Les helpers de pictos partagés sont d'abord extraits dans `src/planrec/icon_assets.py` (DRY avec `etiquettes_renderer.py`). Mise en page : A4 portrait, une colonne par ID, AGCP générique + terre + barre de répartition en tête, pagination par ID, cartouche en pied.

**Tech Stack:** Python 3.11, reportlab (Canvas, `mm`, `renderPDF`), svglib (`svg2rlg`), pypdf (tests), pytest.

**Spec:** `docs/superpowers/specs/2026-06-15-schema-unifilaire-design.md`

---

## File Structure

- **Create** `src/planrec/icon_assets.py` — helpers partagés de chargement/résolution de pictos (`load_icon_as_drawing`, `resolve_svg_id_for_circuit`, mappings, `ICONS_DIR`).
- **Modify** `src/planrec/etiquettes_renderer.py` — importer ces helpers depuis `icon_assets` au lieu de les définir (comportement strictement inchangé).
- **Create** `src/planrec/schema_unifilaire.py` — renderer du schéma unifilaire ; API publique `render_schema_unifilaire_pdf(tableau) -> bytes`.
- **Modify** `app/streamlit_app.py` — 3e bouton de téléchargement dans la zone « ⚡ Tableau électrique ».
- **Create** `tests/test_icon_assets.py` — tests des helpers extraits.
- **Create** `tests/test_schema_unifilaire.py` — tests du renderer.

---

### Task 1: Extraire `icon_assets.py` (helpers de pictos partagés)

**Files:**
- Create: `src/planrec/icon_assets.py`
- Modify: `src/planrec/etiquettes_renderer.py:17-47` et `:140-179`
- Test: `tests/test_icon_assets.py`

- [ ] **Step 1: Écrire les tests des helpers extraits**

Create `tests/test_icon_assets.py`:

```python
"""Tests pour icon_assets (helpers partagés de pictos tableau électrique)."""
from __future__ import annotations


def test_load_icon_as_drawing_returns_drawing():
    from reportlab.graphics.shapes import Drawing
    from src.planrec.icon_assets import load_icon_as_drawing
    d = load_icon_as_drawing("socket")
    assert isinstance(d, Drawing)
    assert d.width > 0 and d.height > 0


def test_load_icon_as_drawing_unknown_raises():
    import pytest
    from src.planrec.icon_assets import load_icon_as_drawing
    with pytest.raises(FileNotFoundError):
        load_icon_as_drawing("nonexistent_svg_id")


def test_resolve_svg_id_prefers_label_prefix():
    """Plaque/Four/LV partagent CircuitType KITCHEN_SPECIAL mais pictos distincts."""
    from src.planrec.icon_assets import resolve_svg_id_for_circuit
    from src.planrec.nfc_tableau import Circuit, CircuitType
    four = Circuit(id="c1", type=CircuitType.KITCHEN_SPECIAL, label="Four",
                   breaker_amps=20, cable_section_mm2=2.5)
    plaque = Circuit(id="c2", type=CircuitType.KITCHEN_SPECIAL, label="Plaque cuisson",
                     breaker_amps=32, cable_section_mm2=6.0)
    assert resolve_svg_id_for_circuit(four) == "oven"
    assert resolve_svg_id_for_circuit(plaque) == "cooktop"


def test_resolve_svg_id_falls_back_to_circuit_type():
    from src.planrec.icon_assets import resolve_svg_id_for_circuit
    from src.planrec.nfc_tableau import Circuit, CircuitType
    light = Circuit(id="c3", type=CircuitType.LIGHTING, label="",
                    breaker_amps=10, cable_section_mm2=1.5)
    assert resolve_svg_id_for_circuit(light) == "light"


def test_etiquettes_renderer_reexports_load_icon():
    """Régression : l'ancien point d'import doit continuer de fonctionner."""
    from src.planrec.etiquettes_renderer import load_icon_as_drawing
    assert load_icon_as_drawing("light") is not None
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_icon_assets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.planrec.icon_assets'`

- [ ] **Step 3: Créer `src/planrec/icon_assets.py`**

```python
"""Helpers partagés pour charger les pictogrammes d'usage (assets/icons/) et
résoudre le picto le plus adapté à un circuit. Utilisé par etiquettes_renderer
et schema_unifilaire — logique pure, aucun import Streamlit/React.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.graphics.shapes import Drawing
from svglib.svglib import svg2rlg

from src.planrec.nfc_tableau import CircuitType

ICONS_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def load_icon_as_drawing(svg_id: str) -> Drawing:
    """Charge assets/icons/<svg_id>.svg en reportlab Drawing.

    Substitue 'currentColor' par '#000000' (svglib ne sait pas l'évaluer).

    Raises:
        FileNotFoundError: si le fichier n'existe pas.
    """
    svg_path = ICONS_DIR / f"{svg_id}.svg"
    if not svg_path.is_file():
        raise FileNotFoundError(
            f"Icône introuvable : {svg_path}. "
            f"Liste autorisée = {sorted(p.stem for p in ICONS_DIR.glob('*.svg'))}"
        )
    raw = svg_path.read_text(encoding="utf-8")
    raw = raw.replace("currentColor", "#000000")
    return svg2rlg(BytesIO(raw.encode("utf-8")))


# Mapping CircuitType -> svg_id (fallback large).
CIRCUIT_TYPE_TO_SVG_ID: dict[CircuitType, str] = {
    CircuitType.LIGHTING: "light",
    CircuitType.SOCKET: "socket",
    CircuitType.KITCHEN_SPECIAL: "cooktop",
    CircuitType.LAUNDRY: "washing_machine",
    CircuitType.BOILER: "boiler",
    CircuitType.HEATING: "convector",
    CircuitType.TOWEL_WARMER: "towel_warmer",
}

# Mapping prioritaire sur le préfixe du label (sous-types cuisine/buanderie).
LABEL_PREFIX_TO_SVG_ID: dict[str, str] = {
    "Plaque cuisson": "cooktop",
    "Four": "oven",
    "Lave-vaisselle": "dishwasher",
    "Lave-linge": "washing_machine",
    "Sèche-linge": "dryer",
    "Chaudière": "boiler",
    "Cumulus": "boiler",
    "Sèche-serviettes": "towel_warmer",
    "Chauffage": "convector",
    "Éclairage": "light",
    "Prises": "socket",
}


def resolve_svg_id_for_circuit(circuit) -> str:
    """Picto le plus adapté : priorité au préfixe du label, fallback CircuitType."""
    label = circuit.label or ""
    for prefix, svg_id in LABEL_PREFIX_TO_SVG_ID.items():
        if label.startswith(prefix):
            return svg_id
    return CIRCUIT_TYPE_TO_SVG_ID.get(circuit.type, "special_feed")
```

- [ ] **Step 4: Refactorer `etiquettes_renderer.py` pour importer depuis `icon_assets`**

Dans `src/planrec/etiquettes_renderer.py`, **supprimer** la définition locale de `load_icon_as_drawing` (lignes 20-47), la constante `ICONS_DIR` (ligne 17), et les blocs `CIRCUIT_TYPE_TO_SVG_ID` / `LABEL_PREFIX_TO_SVG_ID` / `_resolve_svg_id_for_circuit` (lignes 140-179). Remplacer par un import en tête de fichier (juste après `from svglib.svglib import svg2rlg`) :

```python
from src.planrec.icon_assets import (
    ICONS_DIR,
    load_icon_as_drawing,
    resolve_svg_id_for_circuit as _resolve_svg_id_for_circuit,
    CIRCUIT_TYPE_TO_SVG_ID,
    LABEL_PREFIX_TO_SVG_ID,
)
```

L'alias `_resolve_svg_id_for_circuit` préserve l'appel existant à la ligne ~409. L'import de `load_icon_as_drawing` et `ICONS_DIR` les re-expose comme attributs du module (les anciens imports `from src.planrec.etiquettes_renderer import load_icon_as_drawing` et l'usage de `ICONS_DIR` par `_draw_batia_logo_cartouche` continuent de fonctionner). `BytesIO` et `svg2rlg` restent importés (utilisés par `_draw_batia_logo_cartouche`).

- [ ] **Step 5: Lancer tous les tests pictos/étiquettes, vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_icon_assets.py tests/test_etiquettes_renderer.py -q`
Expected: PASS (nouveaux tests + régression étiquettes verts)

- [ ] **Step 6: Commit**

```bash
git add src/planrec/icon_assets.py src/planrec/etiquettes_renderer.py tests/test_icon_assets.py
git commit -m "refactor(icons): extraire icon_assets.py partagé (DRY etiquettes/schema)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Constantes AGCP + repère de circuit (helpers purs)

**Files:**
- Create: `src/planrec/schema_unifilaire.py`
- Test: `tests/test_schema_unifilaire.py`

- [ ] **Step 1: Écrire les tests des helpers purs**

Create `tests/test_schema_unifilaire.py`:

```python
"""Tests pour schema_unifilaire (rendu PDF schéma unifilaire tableau)."""
from __future__ import annotations


def test_circuit_repere_format():
    from src.planrec.schema_unifilaire import circuit_repere
    assert circuit_repere(1, 1) == "1.1"
    assert circuit_repere(2, 3) == "2.3"


def test_agcp_constants_present():
    from src.planrec import schema_unifilaire as su
    assert su.AGCP_SENSITIVITY_MA == 500
    assert su.DEFAULT_CURVE == "C"
    assert "artisan" in su.AGCP_CONFIRM_NOTE.lower()
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.planrec.schema_unifilaire'`

- [ ] **Step 3: Créer `src/planrec/schema_unifilaire.py` avec l'en-tête, les constantes et `circuit_repere`**

```python
"""Renderer du schéma unifilaire du tableau électrique (cible dossier Consuel).

Symboles d'appareillage EN 60617 dessinés en primitives reportlab (AGCP, DDR,
disjoncteur, terre) + pictos d'usage maison (icon_assets) en bout de départ.
Mise en page A4 portrait, une colonne par ID, pagination par ID, cartouche.

Logique pure : aucun import Streamlit/React. Voir
docs/superpowers/specs/2026-06-15-schema-unifilaire-design.md
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A4, portrait
from reportlab.lib.units import mm
from reportlab.graphics import renderPDF
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau
from src.planrec.icon_assets import load_icon_as_drawing, resolve_svg_id_for_circuit
from src.planrec.etiquettes_renderer import paginate_rcds, _draw_batia_logo_cartouche

# --- AGCP générique (tête d'installation, valeurs à confirmer par l'artisan) ---
AGCP_DESIGNATION = "Disjoncteur de branchement"
AGCP_CALIBRE = "15/45 A"
AGCP_SENSITIVITY_MA = 500          # sélectif (S)
DEFAULT_CURVE = "C"                 # courbe disjoncteurs divisionnaires (résidentiel)
AGCP_CONFIRM_NOTE = "Valeurs amont (AGCP, terre) à confirmer par l'artisan"

# --- Géométrie page (mm, A4 portrait) ---
A4_PORTRAIT_W_MM = 210.0
A4_PORTRAIT_H_MM = 297.0
PAGE_MARGIN_MM = 15.0
USABLE_W_MM = A4_PORTRAIT_W_MM - 2 * PAGE_MARGIN_MM   # 180
IDS_PER_PAGE = 3
HEAD_ZONE_H_MM = 38.0              # zone AGCP + terre + barre
ID_HEADER_H_MM = 22.0
DEPARTURE_H_MM = 22.0
CARTOUCHE_H_MM = 18.0


def circuit_repere(id_idx: int, depart_idx: int) -> str:
    """Repère lisible d'un départ : 'N°ID.N°départ' (ex. '1.3')."""
    return f"{id_idx}.{depart_idx}"


def _yp(y_top_mm: float) -> float:
    """Coord 'depuis le haut de page' (mm) → points reportlab (origine bas-gauche)."""
    return (A4_PORTRAIT_H_MM - y_top_mm) * mm
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/planrec/schema_unifilaire.py tests/test_schema_unifilaire.py
git commit -m "feat(schema-unifilaire): module + constantes AGCP + repère

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Symboles, colonnes par ID et rendu PDF complet

**Files:**
- Modify: `src/planrec/schema_unifilaire.py`
- Test: `tests/test_schema_unifilaire.py`

- [ ] **Step 1: Écrire les tests du rendu PDF**

Ajouter à `tests/test_schema_unifilaire.py` :

```python
def _make_tableau(n_ids: int, departs_per_id: int = 3, typology: str = "T3"):
    """Construit un Tableau de test : n_ids RCD, departs_per_id circuits chacun."""
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    rcds = []
    for i in range(n_ids):
        circuits = [
            Circuit(
                id=f"c{i}_{j}",
                type=CircuitType.SOCKET,
                label=f"Prises pièce {j}",
                breaker_amps=20,
                cable_section_mm2=2.5,
                rooms_served=[f"Pièce {j}"],
                n_devices=4,
            )
            for j in range(departs_per_id)
        ]
        rcds.append(RCD(id=f"rcd{i}", rcd_type="A" if i == 0 else "AC",
                        amps=40, sensitivity_ma=30, circuits=circuits))
    return Tableau(typology=typology, typology_source="auto", surface_m2=80.0,
                   heating_enabled=True, rcds=rcds, total_modules=0, n_rails=0,
                   notes=[], warnings=[])


def test_pdf_header_and_nonempty():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2))
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_empty_tableau_produces_valid_single_page_pdf():
    from pypdf import PdfReader
    import io
    from src.planrec.nfc_tableau import Tableau
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0, n_rails=0,
                    notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(empty)
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_multipage_when_many_ids():
    """7 ID → ceil(7/3) = 3 pages."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(7, departs_per_id=2))
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 3


def test_saturated_id_8_departures_does_not_crash():
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(1, departs_per_id=8))
    assert pdf.startswith(b"%PDF-")


def test_repere_and_agcp_text_in_pdf():
    """Le repère '1.1' et la désignation AGCP figurent dans le texte du PDF."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(1, departs_per_id=2))
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "1.1" in text
    assert "branchement" in text.lower()


def test_all_circuit_types_render_without_crash():
    """Chaque CircuitType doit résoudre un picto et rendre sans exception."""
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    circuits = [
        Circuit(id=f"c{i}", type=ct, label=ct.value, breaker_amps=16,
                cable_section_mm2=1.5, rooms_served=["X"], n_devices=1)
        for i, ct in enumerate(CircuitType)
    ]
    rcd = RCD(id="r", rcd_type="AC", amps=40, sensitivity_ma=30, circuits=circuits)
    tab = Tableau(typology="T4", typology_source="auto", surface_m2=90.0,
                  heating_enabled=True, rcds=[rcd], total_modules=0, n_rails=0,
                  notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(tab)
    assert pdf.startswith(b"%PDF-")
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'render_schema_unifilaire_pdf'`

- [ ] **Step 3: Implémenter les symboles, les colonnes et le rendu PDF**

Ajouter à la fin de `src/planrec/schema_unifilaire.py` :

```python
def _draw_picto(canvas, svg_id: str, x_mm: float, y_top_mm: float, size_mm: float) -> None:
    """Place un picto d'usage (viewBox 40×40) scalé dans size_mm, coin haut-gauche
    en (x_mm, y_top_mm depuis le haut)."""
    try:
        drawing = load_icon_as_drawing(svg_id)
    except FileNotFoundError:
        return
    ref = max(drawing.width, drawing.height) or 40.0
    scale = (size_mm * mm) / ref
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, canvas, x_mm * mm, _yp(y_top_mm + size_mm))


def _draw_head(canvas, busbar_y_top_mm: float) -> None:
    """AGCP (disjoncteur de branchement) + prise de terre + barre de répartition."""
    x_left = PAGE_MARGIN_MM
    box_w, box_h = 14.0, 16.0
    box_top = busbar_y_top_mm - box_h - 8.0

    # Boîtier AGCP + contact diagonal
    canvas.setLineWidth(1.2)
    canvas.rect(x_left * mm, _yp(box_top + box_h), box_w * mm, box_h * mm)
    canvas.line((x_left + 3) * mm, _yp(box_top + box_h - 3),
                (x_left + box_w - 3) * mm, _yp(box_top + 3))
    # Amont (vers le haut) + aval (vers la barre)
    canvas.line((x_left + box_w / 2) * mm, _yp(box_top),
                (x_left + box_w / 2) * mm, _yp(box_top - 6))
    canvas.line((x_left + box_w / 2) * mm, _yp(box_top + box_h),
                (x_left + box_w / 2) * mm, _yp(busbar_y_top_mm))
    # Annotations
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 5), AGCP_DESIGNATION)
    canvas.setFont("Helvetica", 7)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 9.5),
                      f"{AGCP_CALIBRE} · {AGCP_SENSITIVITY_MA} mA · sélectif")
    canvas.setFont("Helvetica-Oblique", 6)
    canvas.drawString((x_left + box_w + 3) * mm, _yp(box_top + 13.5), AGCP_CONFIRM_NOTE)

    # Prise de terre (droite) : descente + 3 traits décroissants
    tx = A4_PORTRAIT_W_MM - PAGE_MARGIN_MM - 10.0
    canvas.setLineWidth(1.0)
    canvas.line(tx * mm, _yp(box_top), tx * mm, _yp(box_top + 8))
    canvas.line((tx - 5) * mm, _yp(box_top + 8), (tx + 5) * mm, _yp(box_top + 8))
    canvas.line((tx - 3.3) * mm, _yp(box_top + 9.6), (tx + 3.3) * mm, _yp(box_top + 9.6))
    canvas.line((tx - 1.6) * mm, _yp(box_top + 11.2), (tx + 1.6) * mm, _yp(box_top + 11.2))
    canvas.setFont("Helvetica", 6)
    canvas.drawCentredString(tx * mm, _yp(box_top + 14.5), "Terre")

    # Barre de répartition
    canvas.setLineWidth(2.0)
    canvas.line(PAGE_MARGIN_MM * mm, _yp(busbar_y_top_mm),
                (A4_PORTRAIT_W_MM - PAGE_MARGIN_MM) * mm, _yp(busbar_y_top_mm))
    canvas.setLineWidth(1.0)


def _draw_departure(canvas, circuit, repere: str, spine_x_mm: float,
                    col_x_mm: float, y_top_mm: float) -> None:
    """Un départ : branche + disjoncteur + repère/calibre/section + picto + label."""
    branch_y = y_top_mm + 3
    dj_x = spine_x_mm + 3
    dj_w, dj_h = 6.0, 5.0
    # Branche depuis l'épine vers le disjoncteur
    canvas.setLineWidth(1.0)
    canvas.line(spine_x_mm * mm, _yp(branch_y), dj_x * mm, _yp(branch_y))
    # Symbole disjoncteur divisionnaire (boîtier + contact)
    canvas.rect(dj_x * mm, _yp(branch_y + dj_h / 2), dj_w * mm, dj_h * mm)
    canvas.line((dj_x + 1) * mm, _yp(branch_y + dj_h / 2 - 1),
                (dj_x + dj_w - 1) * mm, _yp(branch_y - dj_h / 2 + 1))
    # Texte : repère + calibre/courbe + section
    tx = dj_x + dj_w + 2
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(tx * mm, _yp(branch_y - 0.5), repere)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(tx * mm, _yp(branch_y + 3), f"{circuit.breaker_amps}A {DEFAULT_CURVE}")
    canvas.drawString(tx * mm, _yp(branch_y + 6), f"{circuit.cable_section_mm2} mm²")
    # Picto d'usage + label court
    svg_id = resolve_svg_id_for_circuit(circuit)
    _draw_picto(canvas, svg_id, col_x_mm + 3, y_top_mm + 11, 7.0)
    canvas.setFont("Helvetica", 6)
    label = (circuit.label or "")[:22]
    canvas.drawString((col_x_mm + 12) * mm, _yp(y_top_mm + 15), label)


def _draw_id_column(canvas, rcd, id_idx: int, col_x_mm: float, col_w_mm: float,
                    busbar_y_top_mm: float) -> None:
    """Une colonne = symbole ID en tête + peigne de disjoncteurs en dessous."""
    cx = col_x_mm + col_w_mm / 2
    # Descente barre → ID
    canvas.line(cx * mm, _yp(busbar_y_top_mm), cx * mm, _yp(busbar_y_top_mm + 6))
    id_top = busbar_y_top_mm + 6
    id_w, id_h = 26.0, ID_HEADER_H_MM - 6
    id_x = cx - id_w / 2
    # Symbole DDR (boîtier + contact diagonal + tore)
    canvas.setLineWidth(1.2)
    canvas.rect(id_x * mm, _yp(id_top + id_h), id_w * mm, id_h * mm)
    canvas.line((id_x + 4) * mm, _yp(id_top + id_h - 3),
                (id_x + id_w - 4) * mm, _yp(id_top + 3))
    canvas.circle(cx * mm, _yp(id_top + id_h / 2), 1.6 * mm, stroke=1, fill=0)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawCentredString(cx * mm, _yp(id_top + 4.5), f"ID {id_idx}")
    canvas.setFont("Helvetica", 7)
    canvas.drawCentredString(cx * mm, _yp(id_top + id_h + 4),
                             f"{rcd.amps}A · Type {rcd.rcd_type} · {rcd.sensitivity_ma} mA")
    # Peigne vertical (épine)
    dep_top = id_top + id_h + 8
    canvas.setLineWidth(1.0)
    if rcd.circuits:
        spine_bottom = dep_top + (len(rcd.circuits) - 1) * DEPARTURE_H_MM + 3
        canvas.line(cx * mm, _yp(id_top + id_h), cx * mm, _yp(spine_bottom))
    for j, circuit in enumerate(rcd.circuits):
        y0 = dep_top + j * DEPARTURE_H_MM
        _draw_departure(canvas, circuit, circuit_repere(id_idx, j + 1),
                        cx, col_x_mm, y0)


def _draw_cartouche(canvas, tableau: Tableau, page_idx: int, total_pages: int) -> None:
    """Bandeau bas : logo batIA + titre + date + page + mention de réserve."""
    margin = PAGE_MARGIN_MM
    band_h = CARTOUCHE_H_MM
    y0 = margin  # bas de bande, mesuré depuis le bas
    canvas.setLineWidth(0.8)
    canvas.rect(margin * mm, y0 * mm, USABLE_W_MM * mm, band_h * mm)
    _draw_batia_logo_cartouche(canvas, margin, y0, 28.0, band_h)
    canvas.line((margin + 28) * mm, y0 * mm, (margin + 28) * mm, (y0 + band_h) * mm)
    tx = margin + 31
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(tx * mm, (y0 + band_h - 5) * mm,
                      f"Schéma unifilaire — Logement {tableau.typology}")
    canvas.setFont("Helvetica", 7)
    canvas.drawString(tx * mm, (y0 + band_h - 9.5) * mm,
                      f"Date : {date.today().isoformat()}   ·   "
                      f"Page {page_idx + 1}/{total_pages}")
    canvas.setFont("Helvetica-Oblique", 6)
    canvas.drawString(tx * mm, (y0 + 2.5) * mm,
                      "Calculé selon NFC 15-100 §10 + règles cabinet. Sections câbles "
                      "indicatives. L'artisan valide la conformité finale.")


def render_schema_unifilaire_pdf(tableau: Tableau) -> bytes:
    """Rend le PDF complet du schéma unifilaire (A4 portrait, multi-pages).

    Une colonne par ID (RCD), IDS_PER_PAGE colonnes par page. AGCP générique +
    terre + barre de répartition rappelés en tête de chaque page ; cartouche en
    pied. Tableau vide → une page minimale valide.
    """
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=portrait(A4))
    pages = paginate_rcds(tableau.rcds, per_page=IDS_PER_PAGE) or [[]]
    total_pages = max(len(pages), 1)
    busbar_y = PAGE_MARGIN_MM + HEAD_ZONE_H_MM
    col_w = USABLE_W_MM / IDS_PER_PAGE

    for page_idx, rcds_in_page in enumerate(pages):
        _draw_head(c, busbar_y)
        base_id_idx = page_idx * IDS_PER_PAGE
        for local_idx, rcd in enumerate(rcds_in_page):
            id_idx = base_id_idx + local_idx + 1
            col_x = PAGE_MARGIN_MM + local_idx * col_w
            _draw_id_column(c, rcd, id_idx, col_x, col_w, busbar_y)
        _draw_cartouche(c, tableau, page_idx, total_pages)
        c.showPage()

    c.save()
    return buf.getvalue()
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: PASS (tous les tests, y compris repère, multipage, ID saturé, tous CircuitType)

- [ ] **Step 5: Vérifier visuellement le PDF (sanity)**

Run:
```bash
.venv/bin/python -c "
from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
rcds=[RCD(id=f'r{i}',rcd_type='A' if i==0 else 'AC',amps=40,sensitivity_ma=30,
      circuits=[Circuit(id=f'c{i}{j}',type=CircuitType.SOCKET,label=f'Prises {j}',
      breaker_amps=20,cable_section_mm2=2.5,rooms_served=[f'P{j}'],n_devices=4)
      for j in range(4)]) for i in range(3)]
t=Tableau(typology='T3',typology_source='auto',surface_m2=80.0,heating_enabled=True,
      rcds=rcds,total_modules=0,n_rails=0,notes=[],warnings=[])
open('/tmp/schema_unifilaire_demo.pdf','wb').write(render_schema_unifilaire_pdf(t))
print('écrit /tmp/schema_unifilaire_demo.pdf')
"
open /tmp/schema_unifilaire_demo.pdf
```
Expected: un PDF s'ouvre, AGCP + terre + barre en haut, 3 colonnes ID avec disjoncteurs et pictos, cartouche en bas. (Ajustements fins de coordonnées tolérés ici.)

- [ ] **Step 6: Commit**

```bash
git add src/planrec/schema_unifilaire.py tests/test_schema_unifilaire.py
git commit -m "feat(schema-unifilaire): symboles EN 60617 + colonnes ID + rendu PDF

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Bouton de téléchargement dans Streamlit

**Files:**
- Modify: `app/streamlit_app.py:3320-3344`

- [ ] **Step 1: Ajouter l'import et le rendu du schéma**

Dans `app/streamlit_app.py`, dans le bloc d'imports de la section tableau (après la ligne `from src.planrec import etiquettes_renderer as _etiq_render`, ligne ~3260), ajouter :

```python
        from src.planrec import schema_unifilaire as _schema_uni
```

- [ ] **Step 2: Passer à 3 colonnes et ajouter le 3e bouton**

Remplacer le bloc `_col_dl_1, _col_dl_2 = st.columns(2)` … jusqu'à la fin du `with _col_dl_2:` (lignes ~3320-3344) par :

```python
            try:
                pdf_schema = _schema_uni.render_schema_unifilaire_pdf(tableau)
                schema_err = None
            except Exception as e:
                pdf_schema = None
                schema_err = str(e)

            _col_dl_1, _col_dl_2, _col_dl_3 = st.columns(3)
            with _col_dl_1:
                st.download_button(
                    "📄 Télécharger le tableau (PDF A4)",
                    data=pdf_bytes,
                    file_name=f"tableau_electrique_{tableau.typology}_{img_hash[:8]}.pdf",
                    mime="application/pdf",
                    key="dl_tableau_pdf",
                )
            with _col_dl_2:
                if pdf_etiquettes is not None:
                    st.download_button(
                        "📎 Télécharger les étiquettes (PDF)",
                        data=pdf_etiquettes,
                        file_name=f"etiquettes_{tableau.typology}_{img_hash[:8]}.pdf",
                        mime="application/pdf",
                        key="dl_etiquettes_pdf",
                        help="A4 paysage 1:1. Imprimer à 100 % pour qu'elles "
                             "rentrent dans le porte-étiquettes physique.",
                    )
                else:
                    st.error(
                        f"⚠ Étiquettes indisponibles : {etiquettes_err}",
                        icon="⚠️",
                    )
            with _col_dl_3:
                if pdf_schema is not None:
                    st.download_button(
                        "📐 Télécharger le schéma unifilaire (PDF)",
                        data=pdf_schema,
                        file_name=f"schema_unifilaire_{tableau.typology}_{img_hash[:8]}.pdf",
                        mime="application/pdf",
                        key="dl_schema_unifilaire_pdf",
                        help="A4 portrait. Pièce destinée au dossier Consuel "
                             "(AGCP générique à confirmer par l'artisan).",
                    )
                else:
                    st.error(
                        f"⚠ Schéma unifilaire indisponible : {schema_err}",
                        icon="⚠️",
                    )
```

- [ ] **Step 3: Vérifier l'import et la non-régression des tests UI**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app/streamlit_app.py').read()); print('syntax OK')"`
Expected: `syntax OK`

Run: `.venv/bin/pytest tests/test_devis_apptest.py -q -m "not slow"`
Expected: PASS (les tests AppTest existants ne régressent pas)

- [ ] **Step 4: Vérification manuelle dans l'app**

Run: `.venv/bin/streamlit run app/streamlit_app.py`
Charger un plan, générer le devis, dérouler « ⚡ Tableau électrique » : 3 boutons côte à côte, le 3e télécharge `schema_unifilaire_*.pdf` ouvrable.

- [ ] **Step 5: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(ui): bouton téléchargement schéma unifilaire (3e PDF tableau)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage** : §1 module pur → Task 2/3 ; §1 `icon_assets` DRY → Task 1 ; §2 constantes AGCP → Task 2 ; §3 symboles EN 60617 → Task 3 (`_draw_head`, `_draw_id_column`, `_draw_departure`) ; §4 portrait/colonnes/multipage → Task 3 (`render_schema_unifilaire_pdf`, `IDS_PER_PAGE`, `paginate_rcds`) ; §5 cartouche → Task 3 (`_draw_cartouche` + `_draw_batia_logo_cartouche`) ; §6 intégration Streamlit → Task 4 ; §7 tests → Tasks 1-3. Toutes les sections couvertes.
- **Placeholders** : aucun TODO/TBD ; tout le code est fourni intégralement.
- **Type consistency** : `render_schema_unifilaire_pdf(tableau) -> bytes`, `circuit_repere(id_idx, depart_idx)`, `resolve_svg_id_for_circuit`, `load_icon_as_drawing`, `paginate_rcds`, `_draw_batia_logo_cartouche(canvas, x_mm, y_mm, w_mm, h_mm)` cohérents entre tasks et avec les signatures existantes vérifiées dans `etiquettes_renderer.py`.

## Hors périmètre (rappel spec)

Pas de saisie utilisateur du calibre d'abonnement, pas de PDF combiné, pas de pièces desservies sur le schéma, pas de modification du modèle `nfc_tableau.py`.
