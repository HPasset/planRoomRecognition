# `src/segmentation/` — Brique B (segmentation des pièces)

Voir [spec design](../../docs/superpowers/specs/2026-05-07-segmentation-pieces-design.md)
et [plan d'implémentation](../../docs/superpowers/plans/2026-05-07-segmentation-pieces-mvp.md).

## Quickstart

### 1. Préparer le dataset CubiCasa

```bash
python scripts/cubicasa5k_export_segmentation.py \
  --root data/raw/cubicasa5k \
  --out data/processed/cubicasa_panoptic
```

### 2. Entraîner Stage A (CubiCasa, 80 epochs, 3-5 jours sur M5 Pro)

```bash
python scripts/train_segmentation.py \
  --config configs/segmentation/stage_a_cubicasa.yaml
```

Auto-resume après crash :

```bash
python scripts/train_segmentation.py \
  --config configs/segmentation/stage_a_cubicasa.yaml \
  --resume latest
```

### 3. Inférence sur un plan

```bash
python scripts/predict_segmentation.py \
  --image data/samples/plan_fr.png \
  --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \
  --out result.json
```

### 4. Dashboard d'évaluation

```bash
python scripts/eval_visualize.py \
  --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \
  --dataset_root data/processed/cubicasa_panoptic \
  --split val \
  --out runs/segmentation/stage_a_cubicasa_v1/eval_val.html
```

## API Python

```python
from src.segmentation.inference import SegmentationInference

inf = SegmentationInference(checkpoint_path="path/to/best.pt")
result = inf.predict("plan.png")
print(result.rooms)  # list[RoomDetection]
print(result.walls.mask_path)
```

## 10 classes (taxonomie C2)

| ID | Classe |
|---|---|
| 0 | Background |
| 1 | Wall |
| 2 | Kitchen |
| 3 | LivingRoom |
| 4 | BedRoom |
| 5 | Bath (WC fusionné) |
| 6 | Entry |
| 7 | Storage |
| 8 | Garage |
| 9 | Outdoor |

## Contrat JSON (consommé par OCR / NFC)

Voir `src/segmentation/schema.py` (Pydantic). Champs garantis : `rooms[]` avec `polygon`/`type`/`confidence`, `walls.mask_path`, `walls.mask_rle`.
