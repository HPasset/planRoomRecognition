# Schéma unifilaire format Hager — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le schéma unifilaire portrait par un rendu **format Hager** (A4 paysage, bus horizontal, cadre normalisé A-G/1-14, cartouche client/projet/puissance/régime).

**Architecture:** Réécriture du corps de `src/planrec/schema_unifilaire.py` (module pur reportlab) avec une nouvelle dataclass `CartoucheInfo` passée par la couche Streamlit. L'infra existante (`icon_assets.py`, bouton de téléchargement) est conservée. Le formulaire cartouche (Projet, Client depuis le référentiel, Puissance, Régime) est ajouté dans `streamlit_app.py`.

**Tech Stack:** Python 3.11, reportlab (Canvas `landscape(A4)`, `mm`, `renderPDF`, `colors`), svglib (pictos via icon_assets), pypdf (tests), Streamlit + SQLAlchemy (référentiel clients).

**Spec:** `docs/superpowers/specs/2026-06-15-schema-unifilaire-hager-design.md`

---

## File Structure

- **Rewrite** `src/planrec/schema_unifilaire.py` — renderer Hager paysage : `CartoucheInfo`, dérivations puissance/DB, `circuit_repere`, cadre/grille, cartouche, contenu folio (bus + ID + départs + terre + pictos + localisation), `render_schema_unifilaire_pdf(tableau, cartouche)`.
- **Rewrite** `tests/test_schema_unifilaire.py` — tests dérivations + rendu Hager (le fichier de tests portrait est remplacé).
- **Modify** `app/streamlit_app.py` — construire `CartoucheInfo` (formulaire + sélecteur client) et appeler la nouvelle signature.

Le renderer reste un seul module (miroir de `etiquettes_renderer.py`), conformément au plan.

---

### Task 1: Squelette module Hager (cadre + cartouche + dérivations) + câblage Streamlit

Objectif : remplacer entièrement le module portrait par le squelette paysage **avec un rendu déjà valide** (cadre + grille + cartouche + pagination), le contenu électrique étant un stub rempli en Task 2. Le câblage Streamlit passe à la nouvelle signature pour que l'app et les AppTests restent verts.

**Files:**
- Rewrite: `src/planrec/schema_unifilaire.py`
- Rewrite: `tests/test_schema_unifilaire.py`
- Modify: `app/streamlit_app.py:3321-3326` (bloc try/except schéma) et `:3361` (help text)

- [ ] **Step 1: Écrire les tests (dérivations + cadre/cartouche)**

Remplacer intégralement `tests/test_schema_unifilaire.py` par :

```python
"""Tests pour schema_unifilaire (format Hager paysage)."""
from __future__ import annotations


def _cartouche(**over):
    from src.planrec.schema_unifilaire import CartoucheInfo
    base = dict(projet="Maison Dupont", client_nom="Dupont SARL",
                client_ville="Lyon", puissance_kva=9, regime_neutre="TT",
                date_iso="2026-06-15")
    base.update(over)
    return CartoucheInfo(**base)


def _make_tableau(n_ids: int, departs_per_id: int = 3, typology: str = "T3"):
    from src.planrec.nfc_tableau import Tableau, RCD, Circuit, CircuitType
    rcds = []
    for i in range(n_ids):
        circuits = [
            Circuit(id=f"c{i}_{j}", type=CircuitType.SOCKET,
                    label=f"Prises pièce {j}", breaker_amps=20,
                    cable_section_mm2=2.5, rooms_served=[f"P{j}"], n_devices=4)
            for j in range(departs_per_id)
        ]
        rcds.append(RCD(id=f"rcd{i}", rcd_type="A" if i == 0 else "AC",
                        amps=40, sensitivity_ma=30, circuits=circuits))
    return Tableau(typology=typology, typology_source="auto", surface_m2=80.0,
                   heating_enabled=True, rcds=rcds, total_modules=0, n_rails=0,
                   notes=[], warnings=[])


def test_derive_puissance_kva():
    from src.planrec.schema_unifilaire import derive_puissance_kva
    assert derive_puissance_kva("T1") == 6
    assert derive_puissance_kva("T3") == 9
    assert derive_puissance_kva("T5") == 12
    assert derive_puissance_kva("???") == 9


def test_derive_db_calibre():
    from src.planrec.schema_unifilaire import derive_db_calibre
    assert derive_db_calibre(6) == 30
    assert derive_db_calibre(9) == 45
    assert derive_db_calibre(12) == 60
    assert derive_db_calibre(7) == 30   # plus proche tier <= 7 => 6 => 30 A


def test_cartouche_info_fields():
    c = _cartouche()
    assert c.projet == "Maison Dupont"
    assert c.client_nom == "Dupont SARL"
    assert c.puissance_kva == 9
    assert c.regime_neutre == "TT"


def test_pdf_header_and_single_folio():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2), _cartouche())
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_empty_tableau_valid_single_folio():
    from pypdf import PdfReader
    import io
    from src.planrec.nfc_tableau import Tableau
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    empty = Tableau(typology="T1", typology_source="auto", surface_m2=None,
                    heating_enabled=False, rcds=[], total_modules=0, n_rails=0,
                    notes=[], warnings=[])
    pdf = render_schema_unifilaire_pdf(empty, _cartouche(puissance_kva=6))
    assert pdf.startswith(b"%PDF-")
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1


def test_cartouche_text_and_grid_present():
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2), _cartouche())
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Maison Dupont" in text
    assert "Dupont SARL" in text
    assert "kVA" in text
    assert "TT" in text
    assert "Folio" in text
    # repères de grille
    assert "14" in text
    for letter in ("A", "G"):
        assert letter in text


def test_multifolio_pagination():
    """4 RCD × (1 ID + 3 départs) = 16 slots > 12/folio => 2 folios."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(4, departs_per_id=3), _cartouche())
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: FAIL (ancien module portrait : `derive_puissance_kva` / `CartoucheInfo` absents, signature `render_schema_unifilaire_pdf` différente).

- [ ] **Step 3: Réécrire `src/planrec/schema_unifilaire.py` (squelette complet)**

Remplacer intégralement le fichier par :

```python
"""Renderer du schéma unifilaire — format Hager (A4 paysage, bus horizontal).

Cadre normalisé (repères A-G / 1-14), arrivée AGCP → jeu de barres → ID 30 mA →
disjoncteurs divisionnaires → barre de terre, bande pictogrammes (bibliothèque
batIA) et cartouche (projet / client / puissance / régime / folio).

Module pur : reportlab uniquement, aucun import Streamlit/React/DB. Voir
docs/superpowers/specs/2026-06-15-schema-unifilaire-hager-design.md
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.graphics import renderPDF
from reportlab.pdfgen.canvas import Canvas

from src.planrec.nfc_tableau import Tableau, RCD
from src.planrec.icon_assets import load_icon_as_drawing, resolve_svg_id_for_circuit
from src.planrec.etiquettes_renderer import _draw_batia_logo_cartouche

# --- AGCP / courbe ---
AGCP_SENSITIVITY_MA = 500
DEFAULT_CURVE = "C"

# --- Dérivations ---
_PUISSANCE_BY_TYPO = {"T1": 6, "T2": 6, "T3": 9, "T4": 12, "T5": 12}
_DB_CALIBRE_BY_KVA = {3: 15, 6: 30, 9: 45, 12: 60, 15: 60, 18: 90}


def derive_puissance_kva(typology: str) -> int:
    """Puissance prévisionnelle par défaut selon la typologie (kVA, monophasé)."""
    return _PUISSANCE_BY_TYPO.get(typology, 9)


def derive_db_calibre(puissance_kva: int) -> int:
    """Calibre du disjoncteur de branchement (A) dérivé de la puissance (kVA)."""
    if puissance_kva in _DB_CALIBRE_BY_KVA:
        return _DB_CALIBRE_BY_KVA[puissance_kva]
    best = min(_DB_CALIBRE_BY_KVA)
    for k in sorted(_DB_CALIBRE_BY_KVA):
        if k <= puissance_kva:
            best = k
    return _DB_CALIBRE_BY_KVA[best]


@dataclass
class CartoucheInfo:
    projet: str
    client_nom: str
    client_ville: str
    puissance_kva: int
    regime_neutre: str
    date_iso: str


def circuit_repere(q_idx: int) -> str:
    """Repère global d'un disjoncteur divisionnaire : 'Q{n}'."""
    return f"Q{q_idx}"


# --- Géométrie page (mm, A4 paysage) ---
PAGE_W_MM = 297.0
PAGE_H_MM = 210.0
FRAME_MARGIN_MM = 8.0
FRAME_LEFT = FRAME_MARGIN_MM
FRAME_RIGHT = PAGE_W_MM - FRAME_MARGIN_MM
FRAME_BOT = FRAME_MARGIN_MM
FRAME_TOP = PAGE_H_MM - FRAME_MARGIN_MM
N_GRID_COLS = 14
GRID_ROWS = "ABCDEFG"
SLOTS_PER_FOLIO = 12

# Zones verticales (y depuis le bas, mm)
MAIN_BUS_Y = 188.0
ID_SYM_Y = 176.0
SEC_BUS_Y = 166.0
Q_SYM_Y = 150.0
PE_Y = 86.0
PICTO_TOP_Y = 78.0
PICTO_SIZE_MM = 9.0
CARTOUCHE_TOP_Y = 44.0
LEGEND_RIGHT = 36.0
SLOTS_LEFT = 38.0


def _paginate_rcds_by_slots(rcds: list[RCD], cap: int = SLOTS_PER_FOLIO) -> list[list[RCD]]:
    """Empaquète des RCD entiers (ID + ses départs) par folio sans dépasser `cap`
    slots, pour qu'un RCD ne soit jamais coupé entre deux folios."""
    folios: list[list[RCD]] = []
    cur: list[RCD] = []
    used = 0
    for rcd in rcds:
        need = 1 + len(rcd.circuits)
        if cur and used + need > cap:
            folios.append(cur)
            cur = []
            used = 0
        cur.append(rcd)
        used += need
    if cur:
        folios.append(cur)
    return folios or [[]]


def _draw_grid_frame(c: Canvas) -> None:
    """Cadre extérieur + repères de grille (colonnes 1-14, lignes A-G)."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.0)
    c.rect(FRAME_LEFT * mm, FRAME_BOT * mm,
           (FRAME_RIGHT - FRAME_LEFT) * mm, (FRAME_TOP - FRAME_BOT) * mm)
    col_w = (FRAME_RIGHT - FRAME_LEFT) / N_GRID_COLS
    c.setFont("Helvetica", 6)
    for i in range(N_GRID_COLS):
        x = FRAME_LEFT + (i + 0.5) * col_w
        c.drawCentredString(x * mm, (FRAME_TOP - 4) * mm, str(i + 1))
        c.drawCentredString(x * mm, (FRAME_BOT + 1.5) * mm, str(i + 1))
        if i > 0:
            gx = (FRAME_LEFT + i * col_w) * mm
            c.setLineWidth(0.2)
            c.line(gx, FRAME_TOP * mm, gx, (FRAME_TOP - 2.5) * mm)
            c.line(gx, FRAME_BOT * mm, gx, (FRAME_BOT + 2.5) * mm)
            c.setLineWidth(1.0)
    row_h = (FRAME_TOP - FRAME_BOT) / len(GRID_ROWS)
    for j, letter in enumerate(GRID_ROWS):
        y = FRAME_TOP - (j + 0.5) * row_h
        c.drawCentredString((FRAME_LEFT + 2) * mm, y * mm, letter)
        c.drawCentredString((FRAME_RIGHT - 2) * mm, y * mm, letter)


def _draw_cartouche(c: Canvas, tableau: Tableau, cartouche: CartoucheInfo,
                    folio_idx: int, total: int) -> None:
    """Bandeau cartouche bas (style Hager) : logo + cases d'info."""
    x0, y0 = FRAME_LEFT, FRAME_BOT
    w = FRAME_RIGHT - FRAME_LEFT
    h = CARTOUCHE_TOP_Y - FRAME_BOT
    c.setLineWidth(0.8)
    c.rect(x0 * mm, y0 * mm, w * mm, h * mm)
    _draw_batia_logo_cartouche(c, x0 + 1, y0 + 1, 34.0, h - 2)
    lx = x0 + 36
    c.line(lx * mm, y0 * mm, lx * mm, (y0 + h) * mm)
    fields = [
        ("Projet", cartouche.projet or "—"),
        ("Client", (cartouche.client_nom or "—") +
                   (f" · {cartouche.client_ville}" if cartouche.client_ville else "")),
        ("Tableau", f"Tableau électrique — {tableau.typology}"),
        ("Date", cartouche.date_iso),
        ("Puissance prévisionnelle", f"{cartouche.puissance_kva} kVA"),
        ("Régime de neutre", cartouche.regime_neutre),
        ("Folio", f"{folio_idx + 1} / {total}"),
    ]
    col_x = [lx + 2, lx + 95, lx + 180]
    for k, (label, value) in enumerate(fields):
        cx = col_x[k % 3]
        row = k // 3
        cy = y0 + h - 7 - row * (h / 3)
        c.setFont("Helvetica", 5.5)
        c.drawString(cx * mm, (cy + 2.5) * mm, label)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(cx * mm, (cy - 1.5) * mm, str(value)[:38])
    c.setFont("Helvetica-Oblique", 5)
    c.drawString((lx + 2) * mm, (y0 + 1.5) * mm,
                 "Calculé selon NFC 15-100 §10 + règles cabinet. Sections "
                 "indicatives. L'artisan valide la conformité finale.")


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio (bus + ID + départs + terre + pictos +
    localisation). Implémenté en Task 2."""
    pass  # Task 2


def render_schema_unifilaire_pdf(tableau: Tableau, cartouche: CartoucheInfo) -> bytes:
    """Rend le PDF du schéma unifilaire (format Hager paysage, multi-folios)."""
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=landscape(A4))
    folios = _paginate_rcds_by_slots(tableau.rcds)
    total = len(folios)
    db_calibre = derive_db_calibre(cartouche.puissance_kva)
    id_offset = 0
    q_offset = 0
    for folio_idx, folio_rcds in enumerate(folios):
        _draw_grid_frame(c)
        _draw_folio_content(c, folio_rcds, folio_idx == 0, folio_idx, total,
                            id_offset, q_offset, db_calibre)
        _draw_cartouche(c, tableau, cartouche, folio_idx, total)
        c.showPage()
        id_offset += len(folio_rcds)
        q_offset += sum(len(r.circuits) for r in folio_rcds)
    c.save()
    return buf.getvalue()
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: PASS (8 tests : dérivations, CartoucheInfo, header, folio unique, vide, cartouche+grille, multi-folios).

- [ ] **Step 5: Câbler Streamlit sur la nouvelle signature (CartoucheInfo par défaut)**

Dans `app/streamlit_app.py`, remplacer le bloc actuel (lignes ~3321-3326) :

```python
            try:
                pdf_schema = _schema_uni.render_schema_unifilaire_pdf(tableau)
                schema_err = None
            except Exception as e:
                pdf_schema = None
                schema_err = str(e)
```

par :

```python
            from datetime import date as _date_su
            from src.planrec.schema_unifilaire import CartoucheInfo as _CartoucheInfo
            _cartouche = _CartoucheInfo(
                projet="",
                client_nom="",
                client_ville="",
                puissance_kva=_schema_uni.derive_puissance_kva(tableau.typology),
                regime_neutre="TT",
                date_iso=_date_su.today().isoformat(),
            )
            try:
                pdf_schema = _schema_uni.render_schema_unifilaire_pdf(tableau, _cartouche)
                schema_err = None
            except Exception as e:
                pdf_schema = None
                schema_err = str(e)
```

Puis, sur le bouton (ligne ~3361), remplacer le `help=` :

```python
                        help="A4 portrait. Pièce destinée au dossier Consuel "
                             "(AGCP générique à confirmer par l'artisan).",
```

par :

```python
                        help="A4 paysage — format Hager. Cartouche à compléter "
                             "dans le formulaire ci-dessus.",
```

(Lire le bloc exact avant d'éditer ; respecter l'indentation imbriquée.)

- [ ] **Step 6: Vérifier syntaxe + non-régression AppTests**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app/streamlit_app.py').read()); print('syntax OK')"`
Expected: `syntax OK`

Run: `.venv/bin/pytest tests/test_devis_apptest.py -q -m "not slow"`
Expected: PASS (la section tableau électrique, exercée par `test_T1_tableau_appears_after_devis_trigger`, ne casse pas avec la nouvelle signature).

- [ ] **Step 7: Commit**

```bash
git add src/planrec/schema_unifilaire.py tests/test_schema_unifilaire.py app/streamlit_app.py
git commit -m "feat(schema-unifilaire): squelette format Hager (cadre+cartouche) + CartoucheInfo

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Contenu électrique du folio (bus horizontal + ID + départs + terre + pictos)

**Files:**
- Modify: `src/planrec/schema_unifilaire.py` (implémenter `_draw_folio_content` + helpers de symboles)
- Modify: `tests/test_schema_unifilaire.py` (ajouter les tests de contenu)

- [ ] **Step 1: Ajouter les tests de contenu électrique**

Ajouter à la fin de `tests/test_schema_unifilaire.py` :

```python
def test_schematic_tokens_present():
    """Repères DB1/ID1/Q1, L1,N, PE1 présents dans le texte du folio 1."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(2, departs_per_id=2), _cartouche())
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "DB1" in text
    assert "ID1" in text
    assert "Q1" in text
    assert "L1,N" in text
    assert "PE1" in text


def test_global_q_numbering_across_folios():
    """La numérotation Q est globale et continue : un gros tableau multi-folios
    contient Q1 sur le folio 1 et un Q de numéro élevé sur le dernier folio."""
    from pypdf import PdfReader
    import io
    from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf
    pdf = render_schema_unifilaire_pdf(_make_tableau(4, departs_per_id=3), _cartouche())
    reader = PdfReader(io.BytesIO(pdf))
    assert "Q1" in reader.pages[0].extract_text()
    # 4 RCD × 3 départs = 12 départs ; le dernier (Q12) est sur le folio 2
    assert "Q12" in reader.pages[1].extract_text()


def test_all_circuit_types_render_without_crash():
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
    pdf = render_schema_unifilaire_pdf(tab, _cartouche(puissance_kva=12))
    assert pdf.startswith(b"%PDF-")
```

- [ ] **Step 2: Lancer les nouveaux tests, vérifier l'échec**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py::test_schematic_tokens_present -q`
Expected: FAIL (`_draw_folio_content` est un stub : ni `DB1` ni `Q1` dans le PDF).

- [ ] **Step 3: Implémenter les symboles + `_draw_folio_content`**

Dans `src/planrec/schema_unifilaire.py`, **remplacer** la fonction stub `_draw_folio_content` (le `def _draw_folio_content(...): pass  # Task 2`) par les fonctions suivantes :

```python
def _slot_x(local_slot_idx: int) -> float:
    """Centre x (mm) d'un slot dans la grille de départs."""
    slot_w = (FRAME_RIGHT - SLOTS_LEFT) / SLOTS_PER_FOLIO
    return SLOTS_LEFT + (local_slot_idx + 0.5) * slot_w


def _draw_source(c: Canvas, db_calibre: int) -> None:
    """Alim. BT + disjoncteur de branchement (folio 1), relié à la barre."""
    x = FRAME_LEFT + 16
    top = MAIN_BUS_Y + 12
    c.setLineWidth(1.0)
    c.line(x * mm, top * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.line((x - 1.5) * mm, (MAIN_BUS_Y + 8) * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.line((x + 1.5) * mm, (MAIN_BUS_Y + 8) * mm, x * mm, (MAIN_BUS_Y + 6) * mm)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x * mm, (top + 1) * mm, "Alim. BT")
    bw, bh = 11.0, 8.0
    c.setLineWidth(1.1)
    c.rect((x - bw / 2) * mm, (MAIN_BUS_Y - bh / 2) * mm, bw * mm, bh * mm)
    c.line((x - bw / 2 + 2) * mm, (MAIN_BUS_Y + bh / 2 - 2) * mm,
           (x + bw / 2 - 2) * mm, (MAIN_BUS_Y - bh / 2 + 2) * mm)
    c.setFont("Helvetica-Bold", 6)
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y + 2) * mm, "DB1")
    c.setFont("Helvetica", 5.5)
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y - 1.5) * mm, f"{db_calibre} A")
    c.drawString((x + bw / 2 + 1) * mm, (MAIN_BUS_Y - 4.5) * mm,
                 f"{AGCP_SENSITIVITY_MA} mA · S")
    c.setLineWidth(1.4)
    c.line((x + bw / 2) * mm, MAIN_BUS_Y * mm, SLOTS_LEFT * mm, MAIN_BUS_Y * mm)


def _draw_id_symbol(c: Canvas, x: float, rcd: RCD, id_idx: int) -> None:
    w, h = 12.0, 8.0
    c.setLineWidth(1.1)
    c.rect((x - w / 2) * mm, (ID_SYM_Y - h / 2) * mm, w * mm, h * mm)
    c.line((x - w / 2 + 2) * mm, (ID_SYM_Y + h / 2 - 2) * mm,
           (x + w / 2 - 2) * mm, (ID_SYM_Y - h / 2 + 2) * mm)
    c.circle(x * mm, ID_SYM_Y * mm, 1.4 * mm, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x * mm, (ID_SYM_Y + h / 2 + 2) * mm, f"ID{id_idx}")
    c.setFont("Helvetica", 5)
    c.drawCentredString(x * mm, (ID_SYM_Y - h / 2 - 3) * mm, f"{rcd.amps}A 30mA")
    c.drawCentredString(x * mm, (ID_SYM_Y - h / 2 - 6) * mm, f"Type {rcd.rcd_type}")


def _draw_q_symbol(c: Canvas, x: float, circ, q_idx: int) -> None:
    w, h = 7.0, 6.0
    c.setLineWidth(1.0)
    c.rect((x - w / 2) * mm, (Q_SYM_Y - h / 2) * mm, w * mm, h * mm)
    c.line((x - w / 2 + 1) * mm, (Q_SYM_Y + h / 2 - 1) * mm,
           (x + w / 2 - 1) * mm, (Q_SYM_Y - h / 2 + 1) * mm)
    c.setFont("Helvetica-Bold", 6)
    c.drawCentredString(x * mm, (Q_SYM_Y + h / 2 + 5) * mm, circuit_repere(q_idx))
    c.setFont("Helvetica", 5)
    c.drawCentredString(x * mm, (Q_SYM_Y + h / 2 + 1.5) * mm,
                        f"{DEFAULT_CURVE} {circ.breaker_amps}A")
    c.drawCentredString(x * mm, (Q_SYM_Y - h / 2 - 3) * mm, "L1,N")


def _draw_earth_drop(c: Canvas, x: float, y: float) -> None:
    c.setStrokeColor(colors.green)
    c.setLineWidth(0.8)
    c.line((x - 2) * mm, y * mm, (x + 2) * mm, y * mm)
    c.line((x - 1.3) * mm, (y - 0.9) * mm, (x + 1.3) * mm, (y - 0.9) * mm)
    c.line((x - 0.6) * mm, (y - 1.8) * mm, (x + 0.6) * mm, (y - 1.8) * mm)
    c.setStrokeColor(colors.black)


def _draw_picto_slot(c: Canvas, circ, x: float) -> None:
    svg_id = resolve_svg_id_for_circuit(circ)
    try:
        d = load_icon_as_drawing(svg_id)
    except FileNotFoundError:
        return
    ref = max(d.width, d.height) or 40.0
    s = (PICTO_SIZE_MM * mm) / ref
    d.width *= s
    d.height *= s
    d.scale(s, s)
    renderPDF.draw(d, c, (x - PICTO_SIZE_MM / 2) * mm, (PICTO_TOP_Y - PICTO_SIZE_MM) * mm)


def _draw_localisation(c: Canvas, circ, x: float) -> None:
    c.saveState()
    c.translate(x * mm, (CARTOUCHE_TOP_Y + 2) * mm)
    c.rotate(90)
    c.setFont("Helvetica", 5.5)
    c.drawString(0, -1.5 * mm, (circ.label or "")[:22])
    c.restoreState()


def _draw_folio_content(c: Canvas, folio_rcds: list[RCD], is_first: bool,
                        folio_idx: int, total: int, id_offset: int,
                        q_offset: int, db_calibre: int) -> None:
    """Contenu électrique d'un folio : bus principal, source/continuation, ID +
    bus secondaires, départs Q, barre de terre, pictos, localisation."""
    # Barre principale
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.4)
    c.line(SLOTS_LEFT * mm, MAIN_BUS_Y * mm, FRAME_RIGHT * mm, MAIN_BUS_Y * mm)

    # Barre de terre PE (verte, pointillés)
    c.setStrokeColor(colors.green)
    c.setLineWidth(1.2)
    c.setDash(4, 2)
    c.line(SLOTS_LEFT * mm, PE_Y * mm, FRAME_RIGHT * mm, PE_Y * mm)
    c.setDash()
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.green)
    c.drawRightString((SLOTS_LEFT - 1) * mm, (PE_Y + 1) * mm, "PE1")
    c.setFillColor(colors.black)
    c.setStrokeColor(colors.black)

    # Source (folio 1) ou continuation
    if is_first:
        _draw_source(c, db_calibre)
    else:
        c.setFont("Helvetica-Oblique", 6)
        c.drawString(SLOTS_LEFT * mm, (MAIN_BUS_Y + 2) * mm,
                     f"suite du folio {folio_idx}")
    if folio_idx < total - 1:
        c.setFont("Helvetica-Oblique", 6)
        c.drawRightString((FRAME_RIGHT - 1) * mm, (MAIN_BUS_Y + 2) * mm,
                          f"suite folio {folio_idx + 2}")

    # Légendes colonne gauche
    c.saveState()
    c.translate((FRAME_LEFT + 5) * mm, (CARTOUCHE_TOP_Y + 4) * mm)
    c.rotate(90)
    c.setFont("Helvetica", 6)
    c.drawString(0, 0, "Application / Localisation des départs")
    c.restoreState()
    c.setFont("Helvetica", 6)
    c.drawString((FRAME_LEFT + 2) * mm, (PICTO_TOP_Y - PICTO_SIZE_MM / 2) * mm,
                 "Pictogramme")

    # Slots : ID puis ses départs
    local = 0
    id_idx = id_offset
    q_idx = q_offset
    for rcd in folio_rcds:
        id_idx += 1
        id_x = _slot_x(local)
        c.setLineWidth(1.0)
        c.line(id_x * mm, MAIN_BUS_Y * mm, id_x * mm, (ID_SYM_Y + 4) * mm)
        _draw_id_symbol(c, id_x, rcd, id_idx)
        local += 1
        n_q = len(rcd.circuits)
        if n_q:
            last_q_x = _slot_x(local + n_q - 1)
            c.setLineWidth(1.2)
            c.line(id_x * mm, (ID_SYM_Y - 4) * mm, id_x * mm, SEC_BUS_Y * mm)
            c.line(id_x * mm, SEC_BUS_Y * mm, last_q_x * mm, SEC_BUS_Y * mm)
        for circ in rcd.circuits:
            q_idx += 1
            qx = _slot_x(local)
            c.setLineWidth(1.0)
            c.line(qx * mm, SEC_BUS_Y * mm, qx * mm, (Q_SYM_Y + 4) * mm)
            _draw_q_symbol(c, qx, circ, q_idx)
            c.line(qx * mm, (Q_SYM_Y - 4) * mm, qx * mm, PE_Y * mm)
            _draw_earth_drop(c, qx, PE_Y)
            _draw_picto_slot(c, circ, qx)
            _draw_localisation(c, circ, qx)
            local += 1
```

- [ ] **Step 4: Lancer toute la suite du module, vérifier qu'elle passe**

Run: `.venv/bin/pytest tests/test_schema_unifilaire.py -q`
Expected: PASS (tous : squelette + tokens DB1/ID1/Q1/L1,N/PE1 + numérotation Q globale + tous CircuitType).

- [ ] **Step 5: Vérification visuelle (sanity, sans display)**

Run:
```bash
.venv/bin/python -c "
from src.planrec.nfc_tableau import generate_tableau
from src.planrec.nfc_rules import DevisGlobal, DevisPiece, EquipmentType, NFCCategory
from src.planrec.schema_unifilaire import render_schema_unifilaire_pdf, CartoucheInfo, derive_puissance_kva
p=[DevisPiece(room_id='p1',nfc_category=NFCCategory.LIVINGROOM,surface_m2=28.0,
   items={EquipmentType.LIGHT_POINT:3,EquipmentType.SOCKET:8,EquipmentType.CONVECTOR:2}),
   DevisPiece(room_id='p2',nfc_category=NFCCategory.KITCHEN,surface_m2=12.0,
   items={EquipmentType.SOCKET:6,EquipmentType.OVEN:1,EquipmentType.COOKTOP:1,EquipmentType.DISHWASHER:1}),
   DevisPiece(room_id='p3',nfc_category=NFCCategory.BEDROOM,surface_m2=14.0,
   items={EquipmentType.LIGHT_POINT:2,EquipmentType.SOCKET:5,EquipmentType.CONVECTOR:1})]
t=generate_tableau(DevisGlobal(per_room=p))
cart=CartoucheInfo(projet='Maison Test',client_nom='Dupont',client_ville='Lyon',
   puissance_kva=derive_puissance_kva(t.typology),regime_neutre='TT',date_iso='2026-06-15')
b=render_schema_unifilaire_pdf(t,cart)
open('/tmp/schema_hager_demo.pdf','wb').write(b)
print('OK bytes=',len(b),'typology=',t.typology)
"
```
Expected: `OK bytes= <>1000> typology= T2` (ou similaire).

- [ ] **Step 6: Commit**

```bash
git add src/planrec/schema_unifilaire.py tests/test_schema_unifilaire.py
git commit -m "feat(schema-unifilaire): contenu folio Hager (bus, ID, départs, terre, pictos)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Formulaire cartouche Streamlit (Projet + sélecteur Client + Puissance + Régime)

**Files:**
- Modify: `app/streamlit_app.py` (remplacer le bloc `_cartouche` par défaut de Task 1 par un vrai formulaire)

- [ ] **Step 1: Remplacer le `CartoucheInfo` par défaut par le formulaire**

Dans `app/streamlit_app.py`, remplacer le bloc ajouté en Task 1 :

```python
            from datetime import date as _date_su
            from src.planrec.schema_unifilaire import CartoucheInfo as _CartoucheInfo
            _cartouche = _CartoucheInfo(
                projet="",
                client_nom="",
                client_ville="",
                puissance_kva=_schema_uni.derive_puissance_kva(tableau.typology),
                regime_neutre="TT",
                date_iso=_date_su.today().isoformat(),
            )
```

par :

```python
            from datetime import date as _date_su
            from src.planrec.schema_unifilaire import CartoucheInfo as _CartoucheInfo

            _default_kva = _schema_uni.derive_puissance_kva(tableau.typology)
            _client_nom, _client_ville = "", ""
            with st.expander("📐 Schéma unifilaire — cartouche", expanded=False):
                _projet = st.text_input("Projet", key="schema_projet")
                try:
                    from src.facturation.db import get_session_factory
                    from src.facturation.services.artisan import get_default_artisan
                    from src.facturation.services.clients import list_clients
                    _sess = get_session_factory()()
                    try:
                        _artisan = get_default_artisan(_sess)
                        _clients = list_clients(_sess, _artisan.id) if _artisan else []
                    finally:
                        _sess.close()
                    _opts = ["— Aucun —"] + [
                        f"{c.nom_ou_raison} ({c.adresse_ville})" for c in _clients
                    ]
                    _sel = st.selectbox("Client", _opts, key="schema_client")
                    _ci = _opts.index(_sel) - 1
                    if _ci >= 0:
                        _client_nom = _clients[_ci].nom_ou_raison
                        _client_ville = _clients[_ci].adresse_ville
                except Exception:
                    _client_nom = st.text_input(
                        "Client", key="schema_client_text",
                        help="Référentiel clients indisponible — saisie libre.",
                    )
                _puissance = st.number_input(
                    "Puissance prévisionnelle (kVA)", min_value=3, max_value=36,
                    value=int(_default_kva), step=3, key="schema_puissance",
                )
                _regime = st.selectbox(
                    "Régime de neutre", ["TT", "TN", "IT"], index=0,
                    key="schema_regime",
                )
            _cartouche = _CartoucheInfo(
                projet=_projet or "",
                client_nom=_client_nom or "",
                client_ville=_client_ville or "",
                puissance_kva=int(_puissance),
                regime_neutre=_regime,
                date_iso=_date_su.today().isoformat(),
            )
```

(Lire le bloc exact avant d'éditer ; respecter l'indentation à 12 espaces.)

- [ ] **Step 2: Vérifier la syntaxe**

Run: `.venv/bin/python -c "import ast; ast.parse(open('app/streamlit_app.py').read()); print('syntax OK')"`
Expected: `syntax OK`

- [ ] **Step 3: Non-régression AppTests**

Run: `.venv/bin/pytest tests/test_devis_apptest.py -q -m "not slow"`
Expected: PASS (le nouvel expander + selectbox ne cassent pas les tests existants).

- [ ] **Step 4: Vérification manuelle**

Run: `.venv/bin/streamlit run app/streamlit_app.py`
Charger un plan → **💡 Générer devis** → section **⚡ Tableau électrique** → l'expander « 📐 Schéma unifilaire — cartouche » contient Projet / Client (sélecteur) / Puissance (préremplie) / Régime ; le bouton **📐 Télécharger le schéma unifilaire** produit un PDF paysage Hager avec le cartouche renseigné.

- [ ] **Step 5: Commit**

```bash
git add app/streamlit_app.py
git commit -m "feat(ui): formulaire cartouche schéma unifilaire (projet + client + puissance + régime)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage** : §1 archi/CartoucheInfo/signature → Task 1 ; §2 cadre normalisé → Task 1 (`_draw_grid_frame`) ; §3 bus horizontal/ID/Q/terre/pictos/localisation → Task 2 (`_draw_folio_content` + helpers) ; §4 dérivations puissance/DB → Task 1 (`derive_puissance_kva`/`derive_db_calibre`, utilisées dans `_draw_source`) ; §5 pagination « suite folio » → Task 1 (`_paginate_rcds_by_slots`) + Task 2 (mentions) ; §6 cartouche → Task 1 (`_draw_cartouche`) ; §7 formulaire Streamlit + sélecteur client → Task 3 ; §8 tests → Tasks 1-3. Couverture complète.
- **Placeholder scan** : le `pass  # Task 2` de `_draw_folio_content` est explicitement remplacé au Step 3 de Task 2 (pas un placeholder résiduel). Aucun TODO/TBD ailleurs ; tout le code est fourni.
- **Type consistency** : `render_schema_unifilaire_pdf(tableau, cartouche) -> bytes`, `CartoucheInfo` (projet, client_nom, client_ville, puissance_kva, regime_neutre, date_iso), `circuit_repere(q_idx)`, `_draw_folio_content(..., db_calibre)` (signature identique entre le stub Task 1 et l'implémentation Task 2), `derive_puissance_kva`/`derive_db_calibre`, `_draw_batia_logo_cartouche(c, x_mm, y_mm, w_mm, h_mm)` — cohérents entre tasks et avec le code existant.

## Hors périmètre (rappel spec)

Pas de renvois CR appariés (mention « suite folio N »), pas de sigles produit Hager (notations génériques), pas de pictos volet/VMC/PAC/GTL (non générés par le moteur NFC), pas de modification du modèle `nfc_tableau.py`, pas de conservation du format portrait.
