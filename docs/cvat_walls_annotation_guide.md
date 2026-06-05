# Annotation murs FR via CVAT — guide pas-à-pas

> Document de référence pour annoter les plans architectes FR et fine-tuner
> le modèle `wall_only_dwg_v2` → `wall_only_dwg_v3`.

## 0 — Pré-requis

- Compte CVAT actif (https://app.cvat.ai) — Hadrien l'a déjà avec d'autres projets (mobilier, pièces)
- 8 plans FR existants à `experiments/wall_detection_eval/test_plans/`
- Plan : viser ~25-30 plans FR au total → annoter ~17-22 nouveaux + les 8 existants

---

## 1 — Setup project CVAT

1. Login sur https://app.cvat.ai
2. Vérifier le sélecteur d'organisation en haut à gauche (rester dans la
   même org que les projets pièces/mobilier pour cohérence)
3. **+ Create new project** → name = `batia-walls-fr`
4. **Labels** :
   - Add label → name = **`Wall`** → type = **any** (autorise polygon ET brush) → color = rouge (#FF0000) → save
5. **Submit**

## 2 — Préparer les images à annoter

Sources possibles pour les ~17-22 plans FR supplémentaires :
- Maisons Bati France (MBF) — site catalogue
- maison-larchitecte.com
- Plans constructeur fournis par tes contacts artisans
- Sites archi indépendants (.fr) : maisonarchi.com, Constructeur Maison etc.
- **Diversifier** : T1, T2/T3, T4/T5, maison vs appartement, neuf vs rénovation, styles
  contemporains vs traditionnels

**Format** : PNG ou JPG, résolution >= 1024px sur le plus grand côté.

## 3 — Upload et création task

1. Dans le project `batia-walls-fr` → **+ Create new task**
2. Name : `batch-1-{date}` (ex: `batch-1-2026-06-05`)
3. **Select files** → upload tes images (drag-drop ou bouton)
4. Submit → la task est en cours de création
5. Une fois prête, click **Open** sur la task

## 4 — Workflow d'annotation par plan (~20-30 min/plan avec SAM)

### Setup SAM-assist (1x par session)

1. Dans le viewer d'annotation, sidebar gauche → icône **AI tools** (étoile/baguette)
2. Onglet **Interactors** → sélectionner **Segment Anything 2** (ou SAM v1)
3. Le modèle se charge (premier coup ~30s) puis devient utilisable

### Annoter un mur

1. Tool SAM activé → **clic au centre d'un mur** → CVAT propose un masque
2. Si bon → **Tab** (ou bouton Done) pour valider
3. Si imprécis → clics additionnels (positifs = vert, négatifs = rouge avec Maj)
4. Affecter au label `Wall`
5. **N** pour démarrer un nouveau mur

### Affiner avec polygon/brush

- **Brush** : touche **F** → tracer/effacer pixel à pixel avec mollette pour taille
- **Polygon** : pour murs droits, clics aux coins → fermer le polygone
- **Edit polygon** : Z = annuler dernier clic, Esc = annuler tout

### Conventions d'annotation

| Inclure dans `Wall` | Ne pas inclure |
|---|---|
| Murs porteurs et cloisons | Mobilier (lits, canapés, sanitaires) |
| Murs des placards et coffrages | Lignes de cotes |
| Bordures de balcons/terrasses (cloisons hautes) | Hachures sols (carrelage, parquet) |
| Doubles murs (épaisseur visible) | Lignes de mobilier intérieur |
| Murs séparant intérieur/extérieur | Texte (noms de pièces, surfaces) |
| Murs d'escaliers/cages | Pictogrammes (rose des vents, échelle) |

Note : **pas besoin d'être pixel-perfect**. Le modèle apprend la
statistique. Vise une cohérence d'annotation entre les plans plutôt
qu'une précision absolue.

### Sauvegarder

- **Ctrl+S** régulièrement pendant l'annotation
- À la fin d'un plan : Tab/Save puis flèche droite pour passer au suivant

## 5 — Export depuis CVAT

Une fois tous les plans annotés :

1. Dans le project → **Actions** → **Export project dataset**
2. **Export format** → **Segmentation mask 1.1**
3. Cocher "Save images" si tu veux récupérer aussi les originaux dans
   l'export (recommandé)
4. **OK** → CVAT prépare un ZIP qu'il t'envoie en email ou propose en
   download direct
5. Dézipper le ZIP en local, par exemple à `~/Downloads/batia-walls-fr-export/`

Structure attendue après dézip :

```
batia-walls-fr-export/
├── ImageSets/Segmentation/default.txt
├── JPEGImages/
│   ├── plan-1.png
│   ├── plan-2.png
│   └── ...
├── SegmentationClass/
│   ├── plan-1.png  (masque RGB où Wall = couleur définie dans labelmap)
│   ├── plan-2.png
│   └── ...
└── labelmap.txt
```

## 6 — Conversion vers le format dataset batIA

```bash
.venv/bin/python scripts/cvat_to_walls_dataset.py \
    --cvat-export ~/Downloads/batia-walls-fr-export \
    --out data/processed/fr_walls \
    --split-mode stratified \
    --id-prefix fr_ \
    --overwrite
```

→ Produit `data/processed/fr_walls/{train,val,test}/{img_NNNN.png, mask_NNNN.png}` + meta.json.

## 7 — Build dataset v3 (DWG v2 + FR)

```bash
.venv/bin/python scripts/build_dwg_walls_v3.py
```

→ Produit `data/processed/dwg_walls_v3/` cumulant 149 paires DWG + N paires FR
(IDs globalement uniques 1..149+N).

## 8 — Repackage au format consommable par le trainer

```bash
.venv/bin/python scripts/build_walls_dwg_only_dataset.py \
    --src data/processed/dwg_walls_v3 \
    --out data/processed/walls_dwg_only_v3 \
    --overwrite
```

→ Produit `data/processed/walls_dwg_only_v3/` (format Cubicasa-like avec
`images/`, `semantic/`, `instance/`, `splits.json`, `dataset.yaml`).

## 9 — Upload Modal + lancement fine-tune v3

```bash
# Upload dataset
.venv/bin/modal volume create batia-walls-dwg-v3
.venv/bin/modal volume put batia-walls-dwg-v3 \
    data/processed/walls_dwg_only_v3 /walls_dwg_only_v3

# Téléchargement v2 best.pt (si pas déjà fait)
.venv/bin/modal volume get batia-walls-runs \
    /wall_only_dwg_v2/checkpoints/best.pt \
    runs/segmentation/wall_only_dwg_v2/checkpoints/best.pt

# Training (--detach OBLIGATOIRE, cf feedback_modal_run_detach memory)
.venv/bin/modal run --detach scripts/modal_train_walls_v3.py::train
```

Estim : ~30-45 min sur A10G, ~0.7 €.

## 10 — Évaluation v3 vs v2

Une fois v3 entraîné, refaire les évals visuelles pour comparaison :

```bash
# Download v3 best.pt
.venv/bin/modal volume get batia-walls-runs \
    /wall_only_dwg_v3/checkpoints/best.pt \
    runs/segmentation/wall_only_dwg_v3/checkpoints/best.pt

# Eval test set v3 (script à dupliquer depuis eval_v2_on_test_set.py
# en remplaçant le chemin du checkpoint)
# Eval plans FR v3 (idem depuis eval_v2_on_fr_plans.py)
```

Comparer côte à côte :
- IoU mur sur test set v3 (qui inclut quelques FR maintenant)
- Qualité visuelle sur les plans FR architectes
- Si gain > +0.05 IoU et qualitatif clairement meilleur → v3 devient
  le checkpoint de production

## Points d'attention

- **Volume FR à viser** : 25-30 plans permet déjà un bon transfert. En dessous
  de 15 le gain peut être marginal ; au-dessus de 50 les rendements
  diminuent (sauf si on diversifie fortement les styles).
- **Cohérence inter-annotateur** : si quelqu'un d'autre annote en parallèle,
  établir une convention écrite (déjà esquissée section 4) et faire un
  spot-check pour aligner.
- **Re-train régulier** : à chaque batch d'annotations supplémentaires,
  on peut relancer un fine-tune incrémental (init depuis le dernier
  best.pt, faible LR, peu d'epochs).
