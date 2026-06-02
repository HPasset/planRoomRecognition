# Évaluation modèles wall detection — Rapport

**Date** : 2026-06-01
**Auteur** : H. Passet (batIA) + analyse assistée
**Plans testés** : 8 plans FR résidentiels (data/raw/plans_fr)

---

## TL;DR

**Recommandation : ne PAS investir dans FloorplanTransformation maintenant.**

Le Mask2Former actuel de batIA produit des résultats **nettement supérieurs** à FT en zero-shot sur les plans FR. Le coût d'intégration de FT (porting Torch 2018 + fine-tune nécessaire) n'est pas justifié.

**Priorité produit recommandée** : investir d'abord dans l'**édition de polygones user-side** (human-in-the-loop), qui amène une amélioration *garantie* de la qualité finale + collecte de données de correction pour fine-tuner M2F au fil du temps.

---

## Candidats évalués

| Modèle | Input | Licence | Statut |
|--------|-------|---------|--------|
| **FloorplanTransformation** (Liu 2017) | Image 2D raster | ✅ MIT | **Évalué zero-shot** |
| RoomFormer (CVPR 2023) | ❌ Density map 3D | MIT | Éliminé : input incompatible |
| HEAT (CVPR 2022) | ❌ Density map 3D | ❌ GPL-3.0 | Éliminé : input + license |
| maikpaixao (re-impl Zeng 2019) | Image 2D | ❌ GPL-3.0 | Éliminé : license SaaS |

Seul FT était à la fois techniquement compatible (input 2D raster) ET juridiquement compatible (MIT).

---

## Méthodologie

### Test set
- **8 plans FR résidentiels** sélectionnés depuis `data/raw/plans_fr/` :
  - 3 plans "maison contemporaine" (style architecte FR moderne)
  - 5 plans variés (mbf-eucalyptus, mbf-sweet, sources web fr)

### Pipelines comparés
- **M2F batIA** : `runs/segmentation/stage_b_finetune_v1/checkpoints/best.pt` (Mask2Former Swin-S, 10 classes, fine-tuné sur Cubicasa)
- **FT zero-shot** : checkpoint Google Drive officiel (entraîné sur LIFULL Japon, sortie vectorielle via solver IP)

### Outputs générés
- 8 dashboards par plan : original + M2F overlay + FT vectorisé + FT raw_corners heatmap
- 1 grille comparative `comparison_grid.png` 3 cols × 8 rows
- Outputs FT bruts (corners, rooms, icons heatmaps + IP debug)

---

## Résultats

### Quantitatif

| Métrique | M2F batIA | FT zero-shot |
|----------|-----------|--------------|
| Plans inférés avec succès | 8/8 | 7/8 (1 plan : IP solver fail) |
| Temps inférence moyen (M5 Pro MPS) | 0.39 s/plan | 0.8 s/plan |
| Polygones par plan (moy) | 12 | n/a (sortie vectorielle, pas polygones) |
| Rooms détectées sémantiquement | ✅ 9-16 par plan | ❌ Pas de label sémantique room |

### Qualitatif (observations clés du grid)

**M2F batIA** :
- Couvre la quasi-totalité de chaque plan
- Labels sémantiques cohérents (Cuisine, Chambre, Bath, LivingRoom, etc.)
- Polygones légèrement imprécis aux murs intérieurs (cf usecase édition user-side)
- **Le bon outil pour batIA aujourd'hui**

**FT zero-shot** :
- Détecte principalement les **contours extérieurs** du bâtiment
- Murs intérieurs **largement manqués** (3-5 par plan vs 15-25 attendus)
- "Icons" (portes/fenêtres) souvent **placés sur des meubles** (table, lit)
- Heatmap raw_corners : signal clair mais sparse
- 1 plan total fail (IP solver produit aucune ligne)

**Cause racine** : FT entraîné sur des plans japonais (LIFULL) — conventions de dessin différentes (traits fins, peu de hachures, layout compact). Les plans FR avec leurs murs hachurés épais, portes en arcs, et style architecte sont hors distribution.

---

## Décision

### ❌ Pourquoi NE PAS intégrer FT maintenant

1. **Performance zero-shot insuffisante** : FT ne bat pas M2F sans fine-tune
2. **Coût de fine-tune** : nécessiterait annotation manuelle de ~500-1000 plans FR au format LIFULL (jonctions + edges) — effort de plusieurs semaines
3. **Pas de sémantique de room** : FT donne des polygones structurels mais pas le type de pièce → on aurait quand même besoin de M2F par-dessus pour le devis NFC
4. **Stack obsolète** : Torch 2018, code partiellement non testé par les auteurs originaux (cf README PyTorch port)
5. **Maintenance limitée** : repo dernier commit 2022, 32 issues ouvertes, aucun successeur ETH/CVPR

### ✅ Ce que cette éval nous a appris

1. **M2F batIA est déjà honnête** sur les plans FR — il faut juste corriger ses imprécisions
2. **L'enjeu n'est pas le modèle de détection, c'est l'UX de correction** par l'user
3. **Les futures données annotées par les artisans pendant leur usage** seront le meilleur signal pour améliorer M2F (data flywheel)

---

## Recommandations stratégiques

### Court terme (4-6 semaines) — investir ici

1. **Édition de polygones user-side** (priorité absolue) :
   - **D** : suppression polygone + changement type (1j)
   - **A** : drag de sommets existants (3-4j)
   - **C** : création polygone from scratch (4j)
   - Stack : `react-konva` ou SVG natif

2. **Capture des corrections** :
   - Stocker chaque polygone modifié (avant + après) dans une base
   - Sera la source de fine-tune M2F au volume suffisant

### Moyen terme (3-6 mois) — explorer

1. **Fine-tune M2F** avec les corrections accumulées via le data flywheel
2. **Ré-évaluer FT** si on atteint > 1000 plans FR annotés (peut-être fine-tuner FT alors pour avoir la structure murs vectorielle)
3. **Considérer un modèle de détection de murs dédié** entraîné sur tes plans FR + masques walls — séparer "où sont les murs" (structure) de "quelle pièce" (sémantique), comme propose la littérature 2017+

### Long terme (12+ mois) — vision

- Modèle multi-tâche fine-tuné sur FR : sémantique pièces + structure murs/portes/fenêtres + équipements pré-placés
- Le data flywheel des corrections artisans devient avantage compétitif (chaque devis = sample labellé gratuit)

---

## Annexes

### Fichiers générés (1.4 GB total)

- `experiments/wall_detection_eval/test_plans/` : 8 plans d'éval
- `experiments/wall_detection_eval/outputs/comparison_grid.png` : grille 3×8 PNG (1.3 MB)
- `experiments/wall_detection_eval/outputs/per_plan/*_dashboard.png` : 8 dashboards individuels
- `experiments/wall_detection_eval/outputs/m2f/<plan>/segmentation.png` : prédictions M2F brutes
- `experiments/wall_detection_eval/outputs/ft/<plan>/{vectorized,raw_corners,raw_rooms,raw_icons}.png` : sorties FT
- `experiments/wall_detection_eval/run_ft_inference.py` : script inference FT
- `experiments/wall_detection_eval/run_comparison.py` : script génération grid

### Modèles téléchargés (~315 MB)

- `models_src/FloorplanTransformation/pytorch/checkpoint/checkpoint.pth` (154 MB)
- M2F : checkpoint batIA déjà dans `runs/segmentation/...`

### Pour rerun

```bash
cd /Users/hadrienpasset/Developer/planRoomRecognition

# FT inference
.venv/bin/python experiments/wall_detection_eval/run_ft_inference.py

# M2F + grid
PYTHONPATH=. .venv/bin/python experiments/wall_detection_eval/run_comparison.py
```

### Notes sur les dépendances ajoutées

- `gdown` : téléchargement Google Drive (poids FT)
- `pulp` : solver IP pour FT (post-processing heatmaps → vectoriel)

---

## Update V1.1 — 2026-06-02 : eval mix Cubicasa + DWG fine-tune

### TL;DR

Tentative d'un fine-tune Mask2Former Swin-T sur `cubicasa_wall_only` (4745 plans
Japon) **mixé** avec les 50 plans DWG curés (oversample DWG ×30 → ~22% des
steps d'entraînement). Résultat : **plus mauvais que le baseline DWG-only**
sur les 8 plans FR de test, malgré 6h de A10G cloud (~$6.50).

### Setup

- Dataset combiné `data/processed/walls_combined/` (4745 cc + 50 dwg = 4795)
- Sampler `WeightedRandomSampler` avec poids cc:1.0 / dwg:30.0
- Config `configs/segmentation/wall_only_stage_a.yaml` : image_size 640,
  batch_size 4, grad_accum 2, 30 epochs, early_stop patience 5
- GPU : Modal Labs A10G 24 GB (~$1.10/hr × ~5.5h)
- Run wandb `18lndo8m`, app Modal `ap-u2xT8tAfPDclpIom8kMDGT`

### Résultats numériques (val set 475 = 467 cc + 8 dwg)

| Métrique | Mix CC+DWG (best ~epoch 6-7) | DWG-only baseline |
|---|---|---|
| val/mIoU | 0.585 | 0.78 |
| val/IoU_class_0 (BG) | 0.93 | 0.97 |
| val/IoU_class_1 (Wall) | **0.265** | **0.60** |

Le val set étant dominé par Cubicasa (98%), ces chiffres mesurent
principalement la perf sur Cubicasa, pas sur DWG.

### Résultats visuels sur 8 plans FR (vrai test)

**Verdict** : DWG-only est **nettement meilleur** que mix CC+DWG sur tous
les 8 plans FR de test. Le mix capte le périmètre extérieur mais rate
systématiquement la majorité des cloisons intérieures. DWG-only détecte
murs ext + int de manière cohérente.

Overlays comparatifs (locaux, non commités) :
- `experiments/wall_detection_eval/outputs/dwg_only/overlays/` (baseline)
- `experiments/wall_detection_eval/outputs/mix_cc_dwg/overlays/` (V1.1)

### Diagnostic

Hypothèse : l'oversample DWG ×30 force le modèle à apprendre le style de
rendu matplotlib DWG (traits noirs nets) au détriment du style Cubicasa
(plans Japon LIFULL avec hachures et traits fins). Le modèle finit par
être moyen partout au lieu de bon nulle part.

Signaux confirmant :
- `val/IoU_class_0` (BG) **descend** sur la fin du training (0.93 → 0.86)
  — signe de dégradation et non plateau
- Wall IoU plateau à 0.25 → 0.27 sans franchir
- Early_stop déclenché à epoch ~10

### Décision

**DWG-only `wall_only_dwg_v1/best.pt` reste le checkpoint Brique B de
référence** pour l'inference batIA. Le mix n'est PAS adopté en V1.

### Enseignements pour V2

1. **Oversample beaucoup plus modéré** : DWG ×3-5 au lieu de ×30 — laisser
   Cubicasa dominer le training tout en exposant le modèle au style DWG.
2. **Val set split par origine** : `val_cc/` et `val_dwg/` séparés pour
   pouvoir mesurer la dégradation par domaine (nécessite mod trainer).
3. **Plus de DWG curés** : la stratégie mix ne portera qu'avec ~200-500 DWG
   (1 cabinet d'archi unique pour cohérence stylistique) — pas 50.
4. **Domain adversarial training** ou **fine-tune en 2 stages** (Cubicasa
   d'abord, DWG ensuite, fusion contrôlée) à explorer.

### Coût Modal cumulé

- Storage volumes : 4.1 GB dataset + ~7 GB checkpoints persistants
  (gratuit, dans les 1024 GiB inclus)
- Compute A10G : ~$6.50
- Compute A100-80GB (tentatives ratées) : ~$0.93
- Total : **~$10 sur $30 inclus mensuels**

### Scripts d'eval

```bash
# Inference + overlays mix CC+DWG sur 8 plans FR
.venv/bin/python experiments/wall_detection_eval/eval_mix_cc_dwg_on_fr.py

# Rappel : inference + overlays DWG-only (baseline)
.venv/bin/python experiments/wall_detection_eval/eval_dwg_only_on_fr.py
.venv/bin/python experiments/wall_detection_eval/render_overlays_dwg_only.py
```
