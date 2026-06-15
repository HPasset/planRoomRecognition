> ⚠️ **REMPLACÉE** par [2026-06-15-schema-unifilaire-hager-design.md](2026-06-15-schema-unifilaire-hager-design.md) (format Hager paysage). Ce document décrit la première version portrait colonnes-par-ID, livrée puis abandonnée. Conservé pour l'historique.

# Schéma unifilaire du tableau électrique — Design

**Date** : 2026-06-15
**Branche** : `feat/placement-chambre`
**Statut** : validé (brainstorming)

## Objectif

Produire le **schéma unifilaire** du tableau électrique, en complément des 2 PDF déjà
livrés (`tableau_renderer.py` → vue tableau type Hager, `etiquettes_renderer.py` →
étiquettes A4 1:1). Usage cible : **pièce de dossier Consuel / attestation de
conformité** (cible (a)) — donc symboles normés et tête d'installation représentée,
tout en restant un livrable généré automatiquement (un cran en dessous d'un schéma
de bureau d'études fait main).

Le schéma consomme la structure `Tableau / RCD / Circuit` produite par
`src/planrec/nfc_tableau.py`, **sans modification du modèle**.

## Décisions de design (issues du brainstorming)

| Sujet | Décision |
|-------|----------|
| Usage cible | (a) Document Consuel / attestation de conformité |
| Tête d'installation (AGCP, terre) | (a) AGCP générique paramétré en constantes, mention « à confirmer par l'artisan ». Pas de changement modèle ni UI. |
| Style des symboles | (c) Hybride : symboles EN 60617 pour les organes de protection (AGCP, ID, disjoncteurs, terre) + pictos d'usage maison en bout de départ |
| Topologie | (b) Colonnes par ID (chaque RCD = une colonne verticale) |
| Format de page | (c) A4 portrait, multi-pages avec pagination par ID (largeur de colonne constante) |
| Niveau de détail par départ | (c) Repère + calibre/courbe + section + picto d'usage. **Pas** de liste des pièces. |
| Packaging | (a) PDF séparé, 3e bouton de téléchargement |
| Cartouche | (a) Cartouche complet en pied de page (logo batIA + titre + typologie + date + n° page + mention de réserve) |

## 1. Architecture & module

Nouveau module **`src/planrec/schema_unifilaire.py`** calqué sur
`etiquettes_renderer.py` :

- Logique pure, **aucun import Streamlit/React** → testable pytest seul.
- Stack identique : `reportlab` (Canvas, origine bas-gauche) + `svglib` (`svg2rlg`)
  pour les pictos d'usage.
- **API publique unique** :
  ```python
  def render_schema_unifilaire_pdf(tableau: Tableau) -> bytes: ...
  ```
- Consomme `Tableau` tel quel — **aucune modification de `nfc_tableau.py`**.

### Réutilisation DRY — `icon_assets.py`

`load_icon_as_drawing` et la résolution `Circuit → svg_id`
(`LABEL_PREFIX_TO_SVG_ID` / `_resolve_svg_id_for_circuit`) vivent aujourd'hui dans
`etiquettes_renderer.py`. Pour éviter d'importer du code privé d'un renderer dans
l'autre (couplage sale), on les **extrait dans un petit module partagé
`src/planrec/icon_assets.py`** :

- `load_icon_as_drawing(svg_id: str) -> Drawing`
- `resolve_svg_id_for_circuit(circuit) -> str` (rendue publique)
- `LABEL_PREFIX_TO_SVG_ID` (constante de mapping)

`etiquettes_renderer.py` est mis à jour pour importer depuis `icon_assets`
(comportement inchangé ; ses tests existants doivent rester verts). Le nouveau
module `schema_unifilaire.py` importe les mêmes helpers.

## 2. Constantes AGCP génériques (tête d'installation)

Bloc de constantes en tête de module, façon « règles cabinet » :

```python
AGCP_DESIGNATION    = "Disjoncteur de branchement"
AGCP_CALIBRE        = "15/45 A"   # réglable selon abonnement — générique
AGCP_SENSITIVITY_MA = 500          # sélectif (S)
AGCP_SELECTIVE      = True
DEFAULT_CURVE       = "C"           # courbe disjoncteurs divisionnaires (résidentiel)
AGCP_CONFIRM_NOTE   = "Valeurs amont (AGCP, terre) à confirmer par l'artisan"
```

## 3. Symboles EN 60617 (primitives reportlab)

Dessinés vectoriellement (pas de fichier SVG externe pour les organes de
protection) :

- **AGCP** — disjoncteur de branchement (boîtier + contact), annoté
  `15/45 A · 500 mA · sélectif`.
- **Prise de terre** — les 3 traits horizontaux décroissants, reliée à la barre.
- **ID / DDR 30 mA** — symbole différentiel + sensibilité, avec **Type A / AC**
  (selon `rcd.rcd_type`) et calibre (`rcd.amps`), `30 mA`.
- **Disjoncteur divisionnaire** — symbole disjoncteur, annoté
  `{breaker_amps}A {courbe}`.
- **Liaisons** : AGCP → barre de répartition horizontale → chaque ID → peigne
  de disjoncteurs divisionnaires.

Les **pictos d'usage** (prise, four, convecteur…) viennent en bout de chaque
départ via `icon_assets.load_icon_as_drawing` (hybride).

## 4. Mise en page (portrait, colonnes par ID, multi-pages)

- **A4 portrait**.
- Haut de page : **AGCP + prise de terre + barre de répartition** horizontale.
- Sous la barre : **une colonne par ID** (RCD). En tête de colonne, le symbole
  ID (type / calibre / 30 mA) ; empilés dessous ses disjoncteurs divisionnaires
  (jusqu'à 8, `MAX_BREAKERS_PER_RCD`).
- Chaque départ affiche :
  - symbole disjoncteur (EN 60617)
  - **repère `N°ID.N°départ`** (ex. `1.3` = ID 1, départ 3)
  - `calibre + courbe` (ex. `16A C`)
  - `section mm²` (`circuit.cable_section_mm2`)
  - **picto d'usage** + label court (`circuit.label`)
- **Pagination** : N ID par page (cap pour garder une largeur de colonne lisible ;
  réutilise la logique de `paginate_rcds`/`split_rcd_into_rows` d'`etiquettes_renderer`
  comme inspiration). AGCP + terre + barre **rappelés en tête de chaque page**.
  Cas nominal (2–4 ID) = 1 page ; le multi-pages est un filet de sécurité.

## 5. Cartouche (pied de page)

Réutilise `_draw_batia_logo_cartouche` (logo batIA officiel) :

- logo batIA
- titre `Schéma unifilaire — Logement {typology}`
- date du jour
- `page X / N`
- mention de réserve déjà utilisée par les autres PDF :
  « Calculé selon NFC 15-100 §10 + règles cabinet. Sections câbles indicatives.
  L'artisan valide la conformité finale. »

## 6. Intégration Streamlit

Dans `app/streamlit_app.py`, zone « ⚡ Tableau électrique » (~ligne 3320) :

- Passer `st.columns(2)` → `st.columns(3)`.
- Ajouter un 3e `st.download_button` :
  « 📐 Télécharger le schéma unifilaire (PDF) ».
- Même pattern `try/except` que les étiquettes : si le rendu échoue, dégrader en
  `st.error(...)` plutôt que crasher la page.
- Nom de fichier : `schema_unifilaire_{tableau.typology}_{img_hash[:8]}.pdf`.

## 7. Tests (`tests/test_schema_unifilaire.py`)

Module pur → tests directs (pas d'AppTest nécessaire pour le renderer) :

- en-tête `%PDF` présent + bytes non vides ;
- nombre de pages cohérent avec le nombre d'ID (1 page en cas nominal ;
  multi-pages forcé avec un grand nombre d'ID) ;
- **tableau vide** géré proprement (pas de crash, PDF valide minimal) ;
- tous les `CircuitType` résolvent vers un picto via `resolve_svg_id_for_circuit` ;
- repères corrects (`1.1`, `1.2`, … `2.1` …) ;
- pas de crash sur ID saturé (8 départs) ni sur l'AGCP générique ;
- `icon_assets` : régression — `etiquettes_renderer` continue de produire son PDF
  après extraction des helpers (les tests existants `test_tableau_renderer.py` /
  étiquettes restent verts).

## Hors périmètre (YAGNI)

- Pas de saisie utilisateur du calibre d'abonnement / type de branchement
  (option (b) écartée pour cette version — AGCP reste générique).
- Pas de PDF combiné « dossier complet » (tableau + schéma + étiquettes) — les 3
  livrables restent indépendants.
- Pas d'affichage des pièces desservies sur le schéma (elles vivent déjà dans le
  PDF tableau et les étiquettes).
- Pas de modification du modèle `nfc_tableau.py` (`Tableau` / `RCD` / `Circuit`).
