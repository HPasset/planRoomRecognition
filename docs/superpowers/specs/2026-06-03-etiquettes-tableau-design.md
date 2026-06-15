# Étiquettes PDF imprimables pour tableau électrique — Design

**Date** : 2026-06-03
**Statut** : approuvé, prêt pour writing-plans
**Scope** : étiquettes seules (le schéma unifilaire fera l'objet d'une session dédiée ultérieure)

## Contexte et motivation

batIA produit aujourd'hui (livré 2026-06-02) un tableau électrique avec :
- un rendu SVG modulaire visualisable dans l'app Streamlit
- un détail des circuits en table HTML
- un export PDF A4 portrait combinant les deux

Manque : les **étiquettes physiques imprimables** que l'artisan colle dans le porte-étiquettes du tableau réel, à côté de chaque RCD et disjoncteur, pour identifier visuellement chaque module. Format de référence : porte-étiquettes Hager 13 modules × 17.5 mm, équivalent universel en France pour la majorité des marques DIN (Schneider, Legrand, etc.).

## Objectif

Ajouter un bouton "📎 Télécharger les étiquettes (PDF)" dans la section "⚡ Tableau électrique" de l'app Streamlit qui télécharge un PDF A4 paysage 1:1 imprimable, contenant les strips d'étiquettes (header + body) pour chaque RCD et disjoncteur du tableau généré.

## Décisions cadrées en brainstorming

- **Scope** : étiquettes seules cette session ; le schéma unifilaire (multi-pages format CAD style Hager) reportera à une session dédiée
- **UX** : un bouton à côté du bouton "Télécharger le tableau (PDF)" existant, dans la même section
- **Pictogrammes** : approche hybride C — symboles électriques NF EN 60617 redessinés d'après leurs conventions normatives publiques, et silhouettes d'appareils dessinées en custom batIA. Aucune copie d'œuvre tierce
- **Layout** : structure type porte-étiquettes Hager — header strip avec `IDx` + `Q1, Q2…` + cartouche batIA en fin de ligne ; body strip avec libellé "Interrupteur différentiel" + picto + libellé application par disjoncteur
- **Sizing** : 17.5 mm par module DIN, A4 paysage, impression 1:1 forcée (sans quoi les étiquettes ne rentreraient pas dans le porte-étiquettes physique)

## Architecture

### Arborescence

```
src/planrec/
├── assets/
│   └── icons/                          (nouveau)
│       ├── socket.svg                  (NF EN 60617 §11-09-01 redessiné)
│       ├── switch.svg                  (NF EN 60617 §07-02-01 redessiné)
│       ├── light.svg                   (NF EN 60617 §11-15-01 redessiné)
│       ├── rj45.svg                    (NF C 15-100 art.771 custom)
│       ├── differential.svg            (NF EN 60617 §07-21 redessiné)
│       ├── oven.svg                    (silhouette custom)
│       ├── cooktop.svg                 (silhouette custom 4 feux)
│       ├── dishwasher.svg              (silhouette custom)
│       ├── washing_machine.svg         (silhouette custom)
│       ├── dryer.svg                   (silhouette custom)
│       ├── boiler.svg                  (silhouette custom)
│       ├── convector.svg               (silhouette custom)
│       ├── towel_warmer.svg            (silhouette custom)
│       ├── special_feed.svg            (générique "alim spé", silhouette custom)
│       ├── LICENSES.md                 (provenance + licences)
│       └── _README.md                  (charte stylistique)
├── etiquettes_renderer.py              (nouveau)
└── tableau_renderer.py                 (inchangé)

app/components/pastille_canvas/frontend/
├── vite.config.ts                      (alias @icons ajouté)
└── src/PastilleCanvas.tsx              (refacto SvgEquipIcon)

app/streamlit_app.py                    (bouton ajouté)

tests/
├── test_etiquettes_renderer.py         (nouveau)
└── test_pastille_canvas_icons.py       (nouveau, validation SVG)
```

### Source unique des pictogrammes

`src/planrec/assets/icons/` devient la source unique consommée par :
- Le renderer Python `etiquettes_renderer.py` via svglib pour parser et embarquer dans le PDF reportlab
- Le composant React `PastilleCanvas.tsx` via alias Vite `@icons` qui pointe vers le même dossier

Cette source unique élimine le risque de drift entre les deux contextes et prépare le terrain pour le futur schéma unifilaire.

### Module `etiquettes_renderer.py`

API publique :
```python
def render_etiquettes_pdf(tableau: Tableau) -> bytes:
    """Génère un PDF A4 paysage 1:1 imprimable contenant les strips
    d'étiquettes pour chaque RCD/disjoncteur du tableau.

    Returns: bytes du PDF (parsable %PDF-)
    """
```

API interne :
```python
def compute_strip_widths(rcd: RCD) -> dict[str, float]:
    """Retourne les largeurs en mm de chaque cellule de la strip pour
    un RCD donné (index, ID, Q1..Qn, batIA logo)."""

def paginate_rcds(rcds: list[RCD], per_page: int = 5) -> list[list[RCD]]:
    """Découpe la liste de RCDs en pages contenant per_page RCDs max."""

def render_rcd_row(canvas, rcd: RCD, row_idx: int, y_cursor: float):
    """Dessine une rangée RCD (header + body strips) à y_cursor sur le canvas."""

def load_icon_as_drawing(svg_id: str) -> Drawing:
    """Charge un .svg depuis assets/icons/ et le convertit en reportlab Drawing
    via svglib, coloré en noir pour print."""
```

Implémentation avec `reportlab.pdfgen.canvas.Canvas` (placement absolu en mm), pas `reportlab.platypus`.

## Charte pictogrammes

Tous les SVG respectent :
- `viewBox="0 0 40 40"`
- `stroke="currentColor"` (permet styling dynamique côté React + reportlab)
- `stroke-width="2"` pour les lignes principales, `1.5` pour les détails
- `stroke-linecap="round"`, `stroke-linejoin="round"`
- `fill="white"` pour les corps, `none` pour les lignes détachées
- Pas de couleurs hardcodées dans les attributs `stroke`/`fill`
- Pas de `<rect>` de fond explicite (le fond du SVG est implicitement transparent ; sur l'étiquette, le fond blanc vient du PDF)

`LICENSES.md` contient une entrée par fichier au format :
```
## socket.svg
Source : Custom batIA 2026-06-03
Auteur : Hadrien Passet
Licence : CC0
Référence normative : NF EN 60617 §11-09-01
Notes : Symbole de prise de courant 2P+T réinterprété d'après la
convention normative publique ; aucune copie d'œuvre tierce.
```

## Layout PDF détaillé

### Format page

- **A4 paysage** : 297 mm × 210 mm
- Marges : 10 mm de chaque côté → zone imprimable **277 × 190 mm**

### Structure d'une rangée RCD

```
┌────┬─────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬─────────────────────┐
│ 1  │      ID 1       │    Q1    │    Q2    │    Q3    │    Q4    │    Q5    │    Q6    │    Q7    │       batIA         │  strip header h=8mm
├────┼─────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼──────────┼─────────────────────┤
│    │  ⤇             │ [picto]  │ [picto]  │ [picto]  │ [picto]  │ [picto]  │ [picto]  │ [picto]  │                     │
│ 1  │  Interrupteur   │  Plaque  │ Lave-    │ Chauf-   │ Chauf-   │ Éclairage│ Éclairage│ Prises   │   ⚡ batIA          │  strip body h=22mm
│    │  différentiel   │ cuisson  │ vaisselle│ fage 1   │ fage 2   │   ×4     │   ×5     │   ×3     │   Tableau labels    │
└────┴─────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴──────────┴─────────────────────┘
  6mm      35 mm        17.5 mm    17.5 mm    17.5 mm    17.5 mm    17.5 mm    17.5 mm    17.5 mm        ~40mm
```

### Dimensions précises

| Élément | Largeur | Justification |
|---|---|---|
| Colonne index rangée | 6 mm | Repère cross-référence avec numéro de rail physique |
| Cellule ID (Interrupteur différentiel) | 35 mm | 2 modules DIN (l'interrupteur différentiel occupe 2 modules physiques) |
| Cellule Qn (disjoncteur) | 17.5 mm | 1 module DIN standard |
| Cellule batIA (cartouche fin de rangée) | espace restant sur la rangée, min 30 mm | Comble la fin de ligne, contient le logo batIA + "Tableau électrique" + typologie. Largeur variable selon le nombre de disjoncteurs effectifs du RCD (cellules Qn manquantes laissent l'espace au cartouche) |
| Hauteur strip header | 8 mm | Texte "ID 1" / "Q1" en bold ~10pt |
| Hauteur strip body | 22 mm | Picto 12 mm + texte 2 lignes 8 pt |
| Espacement vertical inter-rangées RCD | 6 mm | Découpe propre + zone de pliage si nécessaire |

### Cellule body interne

- Picto centré horizontalement, 12 mm × 12 mm, en haut de la cellule
- Texte centré, police 7 pt, word-wrap sur 2 lignes max (réutilise `_wrap_label` adapté à ~8 chars/ligne)
- Label = `circuit.label` (ex. "Plaque cuisson", "Éclairage ×4") — pas de room_label (trop étroit)

### Capacité par rangée et débordement

- **7 cellules Qn max par rangée**
- Si un RCD a 8 disjoncteurs (limite NFC : `MAX_BREAKERS_PER_RCD = 8`), on ouvre une **2e rangée** pour le même RCD avec :
  - Index "1 bis" (ou "2 bis", etc. selon le RCD parent)
  - Cellule ID répétée mais grisée (visuellement secondaire pour signaler la continuation)
  - Q8 (numéro global) dans la première cellule disjoncteur
- Au plus 1 cas de débordement par RCD (8 < 7 × 2)
- Convention **Q-numbering global continu** : les Qn sont numérotés sur l'ensemble du tableau (Q1, Q2, … Qn) sans réinitialisation par RCD. Si RCD 1 a 7 disjoncteurs, le RCD 2 commence à Q8. Convention identique à Hager Resi9 et au schéma unifilaire futur

### Capacité par page

Une rangée RCD complète occupe (8 + 22 + 6) = **36 mm** verticalement.

Sur 190 mm de hauteur utile : **5 RCD par page A4 paysage**.

Pour plus de 5 RCDs : multi-pages automatique avec pied de page "Page n/N".

### Pied de page

Bande de 5 mm en bas de chaque page contenant :
- Gauche : `Date · Tableau électrique · Logement T{X} · Page n/N`
- Droite : `Imprimer à l'échelle 1:1 (option "Taille réelle" ou "100 %")`

L'instruction d'échelle est critique : sans elle, l'imprimante de l'utilisateur peut appliquer un fit-to-page qui rendrait les étiquettes inutilisables dans le porte-étiquettes physique.

## Intégration UI Streamlit

Bouton ajouté dans la section "⚡ Tableau électrique" existante (`app/streamlit_app.py`), à côté du bouton "📄 Télécharger le tableau (PDF)" :

```python
import io
from src.planrec import etiquettes_renderer as _etiq_render

pdf_etiquettes = _etiq_render.render_etiquettes_pdf(tableau)
st.download_button(
    "📎 Télécharger les étiquettes (PDF)",
    data=pdf_etiquettes,
    file_name=f"etiquettes_{tableau.typology}_{img_hash[:8]}.pdf",
    mime="application/pdf",
    key="dl_etiquettes_pdf",
)
```

Pas de paramètre utilisateur côté sidebar : 1:1 forcé, A4 paysage forcé, monochrome forcé. Si on a besoin de variations plus tard, on ajoute progressivement (YAGNI).

Gestion d'erreurs : `try`/`except` autour de l'appel, affichage `st.error()` avec message en cas d'échec, le bouton reste actif pour un retry après fix amont.

Cache : si la perf devient un problème (parsing SVG à chaque rerun), on ajoute `@st.cache_data(show_spinner=False)` sur le renderer avec hash sur la structure du `Tableau`. Pas inclus dans le MVP initial.

## Migration canvas React

`PastilleCanvas.tsx` est refactoré pour charger les SVG depuis `assets/icons/` via Vite, au lieu des SVG inline placeholders actuels :

```typescript
import socketSvg from '@icons/socket.svg?raw';
import switchSvg from '@icons/switch.svg?raw';
// ... 14 imports au total

const ICONS: Record<string, string> = {
  socket: socketSvg,
  switch: switchSvg,
  // ...
};

function SvgEquipIcon({ svgId, color, size = 22 }: SvgEquipIconProps) {
  const raw = ICONS[svgId] ?? FALLBACK_SVG;
  return (
    <span
      style={{ color, display: 'inline-flex', width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: raw }}
    />
  );
}
```

L'alias Vite `@icons` est configuré dans `vite.config.ts` :

```typescript
resolve: {
  alias: {
    '@icons': path.resolve(__dirname, '../../../../src/planrec/assets/icons')
  }
}
```

Cycle de migration prudent :
1. Créer tous les `.svg` dans `assets/icons/` sans toucher React (canvas continue d'afficher ses placeholders)
2. Ajouter l'alias Vite + import + remplacement du `switch(svgId)` par lookup `ICONS[svgId]`. Conserver le fallback `?` pour svg manquant
3. `npm run build` + commit du nouveau `dist/index-*.js`
4. Validation visuelle manuelle du canvas

## Tests

### Pytest

`tests/test_etiquettes_renderer.py` :

**Couche 1 — Layout fonctions pures**
- `compute_strip_widths()` : sommes des largeurs cellules ≤ 277 mm (zone imprimable), Qn = 17.5 mm, ID = 35 mm
- `paginate_rcds()` : N RCDs → N/5 pages arrondi sup
- Cas RCD à 8 disjoncteurs : retourne 2 rangées (1 + 1bis)

**Couche 2 — PDF output validity**
- `render_etiquettes_pdf(tableau)` retourne des bytes `%PDF-` parsables par pypdf
- Nombre de pages correct selon nombre de RCDs
- Texte extrait contient labels attendus ("Plaque cuisson", "Q1", "Q7", "ID 1", "Imprimer à l'échelle 1:1")

**Couche 3 — Dimensions 1:1**
- PDF en A4 paysage (297 × 210 mm)
- Cellule Qn fait bien 17.5 mm (mesurable via conventions reportlab)

**Couche 4 — Cas limites**
- 1 RCD avec 1 circuit → 1 page, 1 strip
- 8 RCDs (>5/page) → 2 pages avec "Page 1/2" + "Page 2/2"
- 1 RCD avec 8 disjoncteurs → 2 rangées (overflow)
- Tableau vide → PDF avec page d'avertissement, pas de crash

`tests/test_pastille_canvas_icons.py` :
- Tous les `.svg` du dossier parsent correctement (xml.etree)
- Chaque SVG a `viewBox="0 0 40 40"`
- Chaque SVG utilise `stroke="currentColor"` ou pas de couleur hardcodée
- Nombre de `.svg` = nombre d'`EquipmentType` actifs + 1 (interrupteur différentiel) — gate contre les oublis d'icône

### Pas de test React/Jest

Le frontend n'a pas de runner de test actuellement. La refacto `SvgEquipIcon` est triviale post-migration (~15 lignes). Validation visuelle manuelle au lancement de l'app suffit pour ce scope.

## Dépendances ajoutées

- **`svglib`** (Python) : parser SVG → reportlab Drawing. Mature, MIT, stable. Ajout à `pyproject.toml`/`requirements.txt`.
- `reportlab` est déjà présent (utilisé par `tableau_renderer.export_pdf`).
- Aucune dépendance JS ajoutée — l'alias Vite est natif.

## Hors scope (explicit)

- Schéma unifilaire multi-pages (pages 3-5 du PDF Hager exemple) : session dédiée ultérieure
- Prévisualisation inline SVG dans Streamlit (juste téléchargement direct)
- Variations de format pour porte-étiquettes d'autres marques (Schneider/Legrand) : 17.5 mm DIN universel suffit pour le marché français
- Couleur des pictos sur étiquettes (noir uniquement, lisibilité print)
- Customisation utilisateur : logo cabinet, couleur cartouche, taille de cellule différente

## Critères d'acceptation

- [ ] Toutes les icônes affichées sur le canvas batIA sont reconnaissables sans contexte (un électricien identifie la nature du circuit au premier coup d'œil)
- [ ] Le PDF généré s'ouvre correctement, est imprimable en A4 paysage 1:1
- [ ] Les étiquettes imprimées rentrent dans un porte-étiquettes Hager-compatible standard 17.5 mm
- [ ] L'instruction "Imprimer à 100 %" est visible dans le pied de page du PDF
- [ ] Les 177 tests pytest existants restent verts et les nouveaux tests étiquettes passent
- [ ] Build React `dist/` à jour, canvas affiche bien les nouveaux pictos après refacto
- [ ] `LICENSES.md` documente la provenance et licence de chaque SVG

## Estimation d'effort indicative

| Tâche | Effort |
|---|---|
| Création des 14 SVG (5 normés + 9 silhouettes) | ~3-4 h |
| Module `etiquettes_renderer.py` + tests | ~3 h |
| Intégration UI Streamlit | ~30 min |
| Refacto SvgEquipIcon + alias Vite + rebuild | ~1 h |
| Validation visuelle + ajustements pictos | ~1 h |
| **Total** | **~1 journée pleine** |

## Travaux ultérieurs (post-MVP)

- Schéma unifilaire multi-pages
- Prévisualisation inline du PDF étiquettes dans l'app
- Personnalisation cartouche batIA (logo cabinet client, projet, date émission)
- Support multi-marques porte-étiquettes (Schneider, Legrand) si demande terrain
- Couleurs pictos sur étiquettes en print couleur
