# Spec — Segmentation des pièces (brique B)

**Date** : 2026-05-07
**Projet** : planRoomRecognition / batIA
**Auteur** : Hadrien Passet (avec Claude)
**Statut** : Design validé, prêt pour plan d'implémentation

## 1. Objectif

Détecter et typer chaque pièce d'un plan d'étage 2D en sortie polygonale exploitable, comme colonne vertébrale du pipeline batIA (OCR labels, métré, application des règles NF C 15-100).

**Sortie cible** : pour chaque plan, un JSON `{rooms: [{type, polygon, confidence, ...}], walls: {mask}}` consommable par les briques aval.

## 2. Périmètre

**Inclus** : segmentation sémantique + instance des pièces (10 classes), masque global des murs, post-process en polygones, JSON contractuel, eval.

**Exclus** (briques séparées, specs ultérieures) : détection objets meubles/sanitaires (brique A existante), OCR labels pièces, calcul d'échelle, moteur règles NFC.

## 3. Taxonomie (10 classes)

| ID | Classe | Mappage CubiCasa |
|---|---|---|
| 0 | Background | Background |
| 1 | Wall | Wall |
| 2 | Kitchen | Kitchen |
| 3 | LivingRoom | LivingRoom |
| 4 | BedRoom | BedRoom |
| 5 | Bath | Bath (WC fusionné) |
| 6 | Entry | Hall, Entry |
| 7 | Storage | Storage, Closet, Pantry |
| 8 | Garage | Garage |
| 9 | Outdoor | Outdoor |

`Railing`, `Undefined`, `Other` CubiCasa → ignorés (mappés Background).

## 4. Architecture modèle

- **Modèle** : `Mask2Former` (mode panoptique), backbone **Swin-S**
- **Init** : `facebook/mask2former-swin-small-coco-panoptic`
- **Stack** : HuggingFace `transformers` + PyTorch 2.x + MPS backend
- **Résolution training/inference** : 768×768 avec letterbox (préserve aspect ratio)
- **Stack rejetée** : MMDetection (xmarva), trop de friction sur MPS

## 5. Données

### 5.1 Sources

| Source | Volume | Rôle | Statut |
|---|---|---|---|
| CubiCasa5K rooms | ~5000 plans | Pré-entraînement | À convertir SVG→panoptic |
| Plans FR annotés | 150 cible | Fine-tuning + test gold | À constituer (annotation manuelle CVAT) |

### 5.2 Splits

```
CubiCasa : 4000 train / 500 val / 500 test_cubicasa
FR       : 80 fine-tune / 20 val_fr / 50 test_fr (jamais touché)
```

### 5.3 Conversion CubiCasa

Nouveau script `scripts/cubicasa5k_export_segmentation.py` (sœur de `cubicasa5k_export_yolo.py`) :
- Parse SVG → mappe classes vers C2 (10 classes)
- Rasterise polygones → masque sémantique (class_id par pixel) + masque instance (room_uid par pixel)
- Réutilise alignement viewBox existant (`F1_scaled`, `max_aspect_diff`)
- Sortie format **panoptic COCO**

### 5.4 Augmentations (Albumentations)

```python
# Géométriques (préservent angles 90°)
RandomRotate90(p=0.5), Rotate(±10°, p=0.3),
HorizontalFlip(p=0.5), VerticalFlip(p=0.5),
RandomScale(0.8-1.2, p=0.3), Affine(shear ±5°, p=0.2)

# Photométriques
RandomBrightnessContrast(p=0.4), CLAHE(p=0.2), ColorJitter(p=0.3)

# Dégradations (réalisme scan)
GaussNoise(p=0.2), GaussianBlur(p=0.15),
ImageCompression(50-95, p=0.2), CoarseDropout(p=0.2)
```

**Exclus** : élastique, mosaic, mixup (détruisent la géométrie sémantique des plans).

## 6. Training en 2 stages

### Stage A — Pré-entraînement CubiCasa

| Paramètre | Valeur |
|---|---|
| Epochs | 80 (early stop patience=10 sur val mIoU) |
| Batch | 4 (effectif 16, grad accumulation ×4) |
| Optim | AdamW, weight_decay=0.05 |
| LR backbone / head | 1e-5 / 1e-4 |
| Scheduler | Cosine + warmup 1000 steps |
| Loss | Mask2Former default (CE 2.0 + MaskCE 5.0 + Dice 5.0) |
| Mixed precision | BF16 (FP16 instable sur MPS) |
| Grad clip | L2 norm 0.01 |
| Sélection | best mIoU val CubiCasa |

Durée estimée : 3-5 jours sur M5 Pro.

### Stage B — Fine-tuning domain adaptation

| Paramètre | Valeur |
|---|---|
| Init | best Stage A |
| Données | 4000 CubiCasa + 80 FR avec WeightedRandomSampler (poids FR ×8) |
| Epochs | 30 (early stop patience=5 sur val_fr mIoU) |
| LR backbone / head | 5e-6 / 5e-5 (10× plus bas) |
| Scheduler | Cosine sans warmup |
| Sélection | best mIoU val_fr |

Durée estimée : 12-24h.

### Gestion déséquilibre classes

Pas de pondération dans la loss (incompatible Mask2Former). À la place : oversampling au niveau plan (plans avec Garage/Storage tirés ×2). Suivi mIoU **par classe**.

### Checkpointing et auto-resume

- Sauvegarde : `best.pt` (meilleur mIoU), `last.pt` (chaque fin d'epoch), `epoch_NN.pt` tous les 10 epochs
- État sauvé : poids modèle + optimizer state + scheduler state + epoch + best metric + RNG states
- CLI `--resume latest` détecte automatiquement le dernier checkpoint et reprend
- Robuste aux crashes thermique / OOM / Ctrl+C : reprise sans perte d'epoch entière

## 7. Suivi entraînement

- **W&B** (cloud) : scalars (loss components, mIoU global + par classe, LR, grad norm), 5 prédictions val + 5 val_fr par epoch en images, configs YAML, best checkpoint en Artifact.
- **Frontière de confidentialité** : training only. Inférence prod ne logge JAMAIS sur W&B (plans clients).
- Configs en YAML dans `configs/segmentation/<run_name>.yaml`.

## 8. Inférence et post-processing

### 8.1 Pipeline

```
image → preprocess (resize 768 + letterbox + normalize)
      → Mask2Former panoptic
      → segments_info + panoptic_seg
      → post-process
      → JSON
```

Mode **single-pass 768×768** en v1. Tile-based en v2 si plans > 2500px souffrent.

### 8.2 Post-process rooms

1. Désappliquer letterbox (remap vers résolution source)
2. Filtrer segments : score < 0.5 drop, aire < 0.1% image drop
3. Pour chaque segment "room" (classes 2-9) :
   - `cv2.findContours` → garde plus grand contour
   - `cv2.approxPolyDP` avec epsilon = 0.005 × arcLength
4. Sanity : `shapely.is_valid` ; fallback bbox si invalide

### 8.3 Post-process walls

- Sortie **masque binaire global** (pas de polygones individuels)
- Format double : RLE COCO dans le JSON + PNG sur disque

### 8.4 Schéma JSON (Pydantic)

```json
{
  "plan_id": "string",
  "image_size": [w, h],
  "model_version": "mask2former-swin-s-batia-vX.Y",
  "inference_time_ms": int,
  "rooms": [
    {
      "id": "room_NNN",
      "type": "Kitchen",
      "type_id": 2,
      "polygon": [[x, y], ...],
      "bbox": [xmin, ymin, xmax, ymax],
      "area_pixels": int,
      "confidence": float
    }
  ],
  "walls": {
    "mask_rle": "...",
    "mask_path": "string",
    "skeleton_paths_count": int
  },
  "warnings": []
}
```

Validation Pydantic = contrat d'interface vers OCR/NFC.

## 9. Architecture code

```
src/segmentation/
├── __init__.py
├── model.py           # chargement Mask2Former + preprocess
├── postprocess.py     # masque panoptique → polygones + JSON
├── schema.py          # Pydantic schemas
├── inference.py       # pipeline complet
└── cli.py             # CLI predict_segmentation.py

scripts/
└── cubicasa5k_export_segmentation.py   # nouveau

configs/segmentation/
└── <run_name>.yaml

tests/segmentation/
├── test_export.py
├── test_postprocess.py
├── test_schema.py
└── test_inference.py
```

## 10. Évaluation

### Métriques principales (sur test_fr, 50 plans gold)

| Métrique | MVP | Production |
|---|---|---|
| mIoU global | ≥ 0.55 | ≥ 0.70 |
| mIoU rooms only (6 classes pièces) | ≥ 0.60 | ≥ 0.75 |
| Panoptic Quality | ≥ 0.50 | ≥ 0.65 |
| Pixel accuracy | ≥ 0.85 | ≥ 0.92 |
| Per-class IoU min | ≥ 0.30 | ≥ 0.50 |
| Room recall | ≥ 80% | ≥ 90% |
| Room precision | ≥ 85% | ≥ 92% |
| Type accuracy conditional | ≥ 75% | ≥ 88% |

### Eval qualitative

`scripts/eval_visualize.py` : génère HTML/PDF avec image, GT, prédiction, overlay erreurs, trié par worst mIoU.

### Tests automatisés

- Unit : conversion SVG→masque, post-process polygones, schémas Pydantic
- Integration : pipeline e2e sur 3 fixtures
- Regression : chute mIoU > 2 points sur micro-test-set → CI fail

## 11. Intégration pipeline batIA

```
Plan → [B segmentation rooms.json + walls_mask]
     → [A YOLO objects.json]
     → assign objects ↔ rooms (spatial intersection)
     → OCR labels → confirme/affine type pièce
     → calcul échelle (m/pixel)
     → Room enriched {type, polygon, surface_m², objects[], label}
     → Moteur NFC → composants placés
     → Devis
```

**Modularité** : B est shippable avant OCR/échelle/NFC, avec UX manuelle correctrice intermédiaire (validation/correction des types et échelle par l'utilisateur électricien).

## 12. Roadmap d'itération

1. **MVP** : conversion CubiCasa + Stage A + inférence + JSON. 🎯 mIoU CubiCasa ≥ 0.65
2. **Domain adaptation** : annotation 80 plans FR + Stage B. 🎯 mIoU test_fr ≥ 0.55
3. **Robustesse** : analyse worst cases + augmentations ciblées + annotation supplémentaire. 🎯 mIoU test_fr ≥ 0.65
4. **Production** : optim latence (ONNX si besoin), tile-based si nécessaire. 🎯 mIoU test_fr ≥ 0.70

## 13. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Domain gap CubiCasa↔FR persiste malgré Stage B | Annotation FR supplémentaire (itération 3), augmentations ciblées sur modes d'échec |
| Mémoire MPS insuffisante pour Mask2Former Swin-S à 768 | Repli batch=2 + grad accumulation ×8, ou fallback Swin-T |
| Mask2Former MPS memory leak (PyTorch <2.3) | Vérifier version, `torch.mps.empty_cache()` entre validations |
| Albumentations sur masques panoptiques | Configurer `additional_targets={'instance_mask': 'mask'}` |
| Annotation FR longue / coûteuse | Étaler sur plusieurs semaines, prioriser plans diversifiés (typologies, époques) |

## 14. Critères de validation MVP

- [ ] mIoU global test_fr ≥ 0.55
- [ ] Aucune classe < 0.30 IoU
- [ ] Room recall ≥ 80%
- [ ] Inférence < 5s par plan sur M5 Pro
- [ ] JSON output validé Pydantic, schéma stable
- [ ] Tests automatisés passent
- [ ] Documentation README usage CLI + API Python
