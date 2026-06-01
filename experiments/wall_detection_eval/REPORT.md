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
