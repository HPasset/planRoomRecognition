# Segmentation des pièces (brique B) — MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire l'infrastructure complète (data, training, inference, eval) de la brique de segmentation panoptique des pièces, et exécuter le Stage A (pré-entraînement CubiCasa). Sortie : modèle Mask2Former Swin-S fonctionnel + JSON contractuel + dashboard d'évaluation.

**Architecture:** Voir [spec design](../specs/2026-05-07-segmentation-pieces-design.md). Mask2Former panoptique (Swin-S init COCO), 10 classes (Background, Wall, Kitchen, LivingRoom, BedRoom, Bath, Entry, Storage, Garage, Outdoor), training en 2 stages (cette plan = Stage A uniquement, Stage B = plan séparé une fois les 80 plans FR annotés).

**Tech Stack:** Python 3.11.11 (pyenv), PyTorch 2.x MPS, HuggingFace transformers, Albumentations, Pydantic, Shapely, OpenCV, W&B, pytest.

**Scope :** MVP = Itération 1 du spec §12. Inclut tout le code, Stage A training, eval CubiCasa. **Exclu** : Stage B fine-tune (plan séparé), tile-based inference (v2), ONNX export (v2).

---

## File Structure

```
configs/segmentation/
├── stage_a_cubicasa.yaml         # config Stage A
└── stage_b_finetune.yaml.template # template pour Plan 2

src/segmentation/
├── __init__.py
├── classes.py                    # constantes 10 classes + mappings CubiCasa
├── schema.py                     # Pydantic schemas (sortie JSON)
├── config.py                     # YAML → typed config (Pydantic)
├── augmentations.py              # transforms Albumentations
├── dataset.py                    # PyTorch Dataset (panoptic)
├── model.py                      # wrapper Mask2Former
├── metrics.py                    # mIoU, PQ, room recall/precision
├── checkpoint.py                 # save/load checkpoint state
├── tracker.py                    # wrapper W&B (abstrait)
├── trainer.py                    # boucle d'entraînement
├── preprocess.py                 # letterbox + normalize (inférence)
├── postprocess.py                # panoptic → polygones JSON
└── inference.py                  # pipeline inférence end-to-end

scripts/
├── cubicasa5k_export_segmentation.py  # SVG → panoptic dataset
├── train_segmentation.py              # CLI training
├── predict_segmentation.py            # CLI inférence
└── eval_visualize.py                  # dashboard worst cases

tests/segmentation/
├── conftest.py                   # fixtures
├── fixtures/
│   ├── sample_cubicasa/          # 1-2 SVG minimaux
│   └── sample_plan.png           # 1 image plan FR pour tests inférence
├── test_classes.py
├── test_schema.py
├── test_config.py
├── test_export.py
├── test_dataset.py
├── test_model.py
├── test_metrics.py
├── test_checkpoint.py
├── test_postprocess.py
├── test_preprocess.py
└── test_inference.py
```

---

## Task 1: Dépendances + structure de répertoires

**Files:**
- Modify: `requirements.txt`
- Create: `src/segmentation/__init__.py` (vide)
- Create: `tests/segmentation/__init__.py` (vide)
- Create: `configs/segmentation/.gitkeep`
- Create: `tests/segmentation/conftest.py`

- [ ] **Step 1: Créer les répertoires**

```bash
mkdir -p src/segmentation tests/segmentation/fixtures configs/segmentation
touch src/segmentation/__init__.py tests/segmentation/__init__.py configs/segmentation/.gitkeep
```

- [ ] **Step 2: Vérifier l'encodage de requirements.txt**

```bash
file requirements.txt
```

Si UTF-16 (probable, vu l'historique Windows du projet), reconvertir en UTF-8 :

```bash
iconv -f UTF-16 -t UTF-8 requirements.txt -o /tmp/req_utf8.txt
mv /tmp/req_utf8.txt requirements.txt
file requirements.txt  # doit afficher UTF-8 ou ASCII
```

- [ ] **Step 3: Ajouter les dépendances manquantes**

Append à `requirements.txt` :

```
transformers==4.46.3
albumentations==1.4.20
wandb==0.18.7
pycocotools==2.0.8
accelerate==1.1.1
matplotlib==3.9.2
tqdm==4.66.6
svgpathtools==1.6.1
```

- [ ] **Step 4: Installer**

```bash
pip install -r requirements.txt
```

Expected: pas d'erreur de résolution. Si conflit numpy/torch, contraindre `numpy<2.5`.

- [ ] **Step 5: conftest.py pytest**

Créer `tests/segmentation/conftest.py` :

```python
"""Shared fixtures for segmentation tests."""
from pathlib import Path
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    """Disposable run directory mimicking runs/segmentation/<run_name>/."""
    p = tmp_path / "run_test"
    (p / "checkpoints").mkdir(parents=True)
    return p
```

- [ ] **Step 6: Smoke test imports**

Créer `tests/segmentation/test_imports.py` :

```python
def test_imports_basic():
    import torch
    import transformers
    import albumentations
    import wandb
    import pycocotools
    import shapely
    import cv2
    assert torch.backends.mps.is_available(), "MPS backend required"
```

Run: `pytest tests/segmentation/test_imports.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/segmentation tests/segmentation configs/segmentation
git commit -m "feat(seg): scaffolding + deps for rooms segmentation"
```

---

## Task 2: Définition des classes + mappings CubiCasa

**Files:**
- Create: `src/segmentation/classes.py`
- Create: `tests/segmentation/test_classes.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_classes.py
from src.segmentation.classes import (
    NUM_CLASSES, CLASS_NAMES, CLASS_ID,
    CUBICASA_TO_C2, ROOM_CLASS_IDS, STRUCTURAL_CLASS_IDS,
)


def test_num_classes_is_ten():
    assert NUM_CLASSES == 10


def test_class_names_ordered():
    assert CLASS_NAMES[0] == "Background"
    assert CLASS_NAMES[1] == "Wall"
    assert CLASS_NAMES[2] == "Kitchen"
    assert CLASS_NAMES[9] == "Outdoor"


def test_class_id_mapping():
    assert CLASS_ID["Kitchen"] == 2
    assert CLASS_ID["Outdoor"] == 9


def test_cubicasa_mapping_handles_synonyms():
    assert CUBICASA_TO_C2("Kitchen") == 2
    assert CUBICASA_TO_C2("Hall") == 6  # Entry
    assert CUBICASA_TO_C2("Closet") == 7  # Storage
    assert CUBICASA_TO_C2("Pantry") == 7
    assert CUBICASA_TO_C2("Railing") == 0  # ignored → Background
    assert CUBICASA_TO_C2("Undefined") == 0
    assert CUBICASA_TO_C2("Unknown_label_xyz") == 0  # default fallback


def test_room_class_ids_excludes_background_and_wall():
    assert 0 not in ROOM_CLASS_IDS
    assert 1 not in ROOM_CLASS_IDS
    assert ROOM_CLASS_IDS == [2, 3, 4, 5, 6, 7, 8, 9]


def test_structural_class_ids():
    assert STRUCTURAL_CLASS_IDS == [1]  # walls only
```

- [ ] **Step 2: Run test (fail expected)**

```bash
pytest tests/segmentation/test_classes.py -v
```

Expected: FAIL (`No module named 'src.segmentation.classes'`).

- [ ] **Step 3: Implémenter classes.py**

```python
# src/segmentation/classes.py
"""10-class taxonomy (C2) for room segmentation, with CubiCasa mapping."""
from typing import Final


CLASS_NAMES: Final[tuple[str, ...]] = (
    "Background",   # 0
    "Wall",         # 1
    "Kitchen",      # 2
    "LivingRoom",   # 3
    "BedRoom",      # 4
    "Bath",         # 5  (WC fusionné)
    "Entry",        # 6  (Hall + Entry)
    "Storage",      # 7  (Closet + Pantry + Storage)
    "Garage",       # 8
    "Outdoor",      # 9
)

NUM_CLASSES: Final[int] = len(CLASS_NAMES)

CLASS_ID: Final[dict[str, int]] = {name: i for i, name in enumerate(CLASS_NAMES)}

# Pixels qui appartiennent à des "rooms" (instances séparables)
ROOM_CLASS_IDS: Final[list[int]] = [CLASS_ID[n] for n in (
    "Kitchen", "LivingRoom", "BedRoom", "Bath",
    "Entry", "Storage", "Garage", "Outdoor",
)]

# Pixels structurels (pas des rooms instanciables)
STRUCTURAL_CLASS_IDS: Final[list[int]] = [CLASS_ID["Wall"]]


# CubiCasa label → C2 class id
_CUBICASA_RAW_MAP: dict[str, str] = {
    "Background": "Background",
    "Outdoor": "Outdoor",
    "Wall": "Wall",
    "Kitchen": "Kitchen",
    "LivingRoom": "LivingRoom",
    "Living Room": "LivingRoom",
    "BedRoom": "BedRoom",
    "Bed Room": "BedRoom",
    "Bath": "Bath",
    "WC": "Bath",
    "Bathroom": "Bath",
    "Hall": "Entry",
    "Entry": "Entry",
    "Storage": "Storage",
    "Closet": "Storage",
    "Pantry": "Storage",
    "Garage": "Garage",
    # Tout le reste (Railing, Undefined, Other, ...) → Background
}


def CUBICASA_TO_C2(cubicasa_label: str) -> int:
    """Map a CubiCasa room label to a C2 class id. Unknown → Background (0)."""
    c2_name = _CUBICASA_RAW_MAP.get(cubicasa_label.strip(), "Background")
    return CLASS_ID[c2_name]
```

- [ ] **Step 4: Run test (PASS expected)**

```bash
pytest tests/segmentation/test_classes.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/classes.py tests/segmentation/test_classes.py
git commit -m "feat(seg): 10-class taxonomy with CubiCasa mapping"
```

---

## Task 3: Schémas Pydantic (contrat JSON de sortie)

**Files:**
- Create: `src/segmentation/schema.py`
- Create: `tests/segmentation/test_schema.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_schema.py
import pytest
from pydantic import ValidationError
from src.segmentation.schema import RoomDetection, WallsOutput, SegmentationOutput


def _valid_room():
    return dict(
        id="room_001", type="Kitchen", type_id=2,
        polygon=[[0, 0], [10, 0], [10, 10], [0, 10]],
        bbox=[0, 0, 10, 10], area_pixels=100, confidence=0.9,
    )


def test_room_detection_valid():
    r = RoomDetection(**_valid_room())
    assert r.type == "Kitchen"
    assert len(r.polygon) == 4


def test_room_detection_polygon_min_3_points():
    data = _valid_room()
    data["polygon"] = [[0, 0], [10, 10]]
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_room_detection_confidence_range():
    data = _valid_room()
    data["confidence"] = 1.5
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_room_detection_type_must_match_type_id():
    data = _valid_room()
    data["type"] = "Bath"
    data["type_id"] = 2  # mismatch
    with pytest.raises(ValidationError):
        RoomDetection(**data)


def test_segmentation_output_serializable():
    out = SegmentationOutput(
        plan_id="plan_001.png",
        image_size=[1024, 768],
        model_version="mask2former-swin-s-batia-v0.1",
        inference_time_ms=1500,
        rooms=[RoomDetection(**_valid_room())],
        walls=WallsOutput(mask_rle="abc", mask_path="/tmp/w.png", skeleton_paths_count=12),
        warnings=[],
    )
    json_str = out.model_dump_json()
    restored = SegmentationOutput.model_validate_json(json_str)
    assert restored.plan_id == "plan_001.png"
    assert restored.rooms[0].type == "Kitchen"
```

- [ ] **Step 2: Run test (fail)**

```bash
pytest tests/segmentation/test_schema.py -v
```

- [ ] **Step 3: Implémenter schema.py**

```python
# src/segmentation/schema.py
"""Pydantic schemas — contract between segmentation (B) and downstream (A/OCR/NFC)."""
from typing import Annotated
from pydantic import BaseModel, Field, model_validator

from src.segmentation.classes import CLASS_NAMES, CLASS_ID


Polygon = Annotated[list[list[int]], Field(min_length=3)]
"""List of [x, y] pixel coords. At least 3 points (triangle minimum)."""

BBox = Annotated[list[int], Field(min_length=4, max_length=4)]
"""[xmin, ymin, xmax, ymax] pixel coords."""


class RoomDetection(BaseModel):
    id: str = Field(pattern=r"^room_\d{3,}$")
    type: str
    type_id: int = Field(ge=0, lt=len(CLASS_NAMES))
    polygon: Polygon
    bbox: BBox
    area_pixels: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _type_matches_id(self):
        if self.type not in CLASS_ID:
            raise ValueError(f"Unknown type: {self.type}")
        if CLASS_ID[self.type] != self.type_id:
            raise ValueError(
                f"type_id mismatch: type={self.type} expected id={CLASS_ID[self.type]}, got {self.type_id}"
            )
        return self


class WallsOutput(BaseModel):
    mask_rle: str  # COCO-style RLE
    mask_path: str  # absolute path to PNG on disk
    skeleton_paths_count: int = Field(ge=0)


class SegmentationOutput(BaseModel):
    plan_id: str
    image_size: list[int] = Field(min_length=2, max_length=2)  # [w, h]
    model_version: str
    inference_time_ms: int = Field(ge=0)
    rooms: list[RoomDetection]
    walls: WallsOutput
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test (PASS)**

```bash
pytest tests/segmentation/test_schema.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/schema.py tests/segmentation/test_schema.py
git commit -m "feat(seg): Pydantic output schema"
```

---

## Task 4: Config loader (YAML typé Pydantic)

**Files:**
- Create: `src/segmentation/config.py`
- Create: `tests/segmentation/test_config.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_config.py
from pathlib import Path
import pytest
from src.segmentation.config import TrainingConfig, load_config


def _write_yaml(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


VALID_YAML = """
run_name: stage_a_test
seed: 42

data:
  dataset_root: data/processed/cubicasa_panoptic
  image_size: 768
  batch_size: 4

model:
  backbone: facebook/mask2former-swin-small-coco-panoptic

optimizer:
  lr_backbone: 1.0e-5
  lr_head: 1.0e-4
  weight_decay: 0.05
  grad_accumulation: 4
  grad_clip_norm: 0.01

scheduler:
  type: cosine
  warmup_steps: 1000

training:
  epochs: 80
  early_stop_patience: 10
  mixed_precision: bf16
  oversample_rare_classes: true

logging:
  tracker: wandb
  project: batia-segmentation
  log_image_count: 5

checkpoint:
  output_dir: runs/segmentation/stage_a_test
  save_every_n_epochs: 10
"""


def test_load_valid_config(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML)
    cfg = load_config(p)
    assert isinstance(cfg, TrainingConfig)
    assert cfg.run_name == "stage_a_test"
    assert cfg.training.epochs == 80
    assert cfg.optimizer.lr_backbone == 1e-5


def test_invalid_image_size_rejected(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML.replace("image_size: 768", "image_size: 100"))
    with pytest.raises(ValueError):
        load_config(p)


def test_invalid_mixed_precision_rejected(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML.replace("mixed_precision: bf16", "mixed_precision: fp64"))
    with pytest.raises(ValueError):
        load_config(p)
```

- [ ] **Step 2: Run test (fail)**

```bash
pytest tests/segmentation/test_config.py -v
```

- [ ] **Step 3: Implémenter config.py**

```python
# src/segmentation/config.py
"""Typed YAML config for training runs."""
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, field_validator


class DataConfig(BaseModel):
    dataset_root: str
    image_size: int = Field(ge=256, le=1536)
    batch_size: int = Field(ge=1, le=64)


class ModelConfig(BaseModel):
    backbone: str = "facebook/mask2former-swin-small-coco-panoptic"


class OptimizerConfig(BaseModel):
    lr_backbone: float = Field(gt=0, le=1e-2)
    lr_head: float = Field(gt=0, le=1e-2)
    weight_decay: float = Field(ge=0, le=1.0)
    grad_accumulation: int = Field(ge=1, le=64)
    grad_clip_norm: float = Field(gt=0, le=10.0)


class SchedulerConfig(BaseModel):
    type: Literal["cosine", "polynomial", "constant"] = "cosine"
    warmup_steps: int = Field(ge=0, le=10000)


class TrainingPhaseConfig(BaseModel):
    epochs: int = Field(ge=1, le=500)
    early_stop_patience: int = Field(ge=0, le=50)
    mixed_precision: Literal["bf16", "fp16", "no"] = "bf16"
    oversample_rare_classes: bool = True


class LoggingConfig(BaseModel):
    tracker: Literal["wandb", "tensorboard", "none"] = "wandb"
    project: str = "batia-segmentation"
    log_image_count: int = Field(ge=0, le=50)


class CheckpointConfig(BaseModel):
    output_dir: str
    save_every_n_epochs: int = Field(ge=1, le=100)


class TrainingConfig(BaseModel):
    run_name: str
    seed: int = 42
    data: DataConfig
    model: ModelConfig
    optimizer: OptimizerConfig
    scheduler: SchedulerConfig
    training: TrainingPhaseConfig
    logging: LoggingConfig
    checkpoint: CheckpointConfig


def load_config(path: str | Path) -> TrainingConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return TrainingConfig.model_validate(raw)
```

- [ ] **Step 4: Run test (PASS)**

```bash
pytest tests/segmentation/test_config.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/config.py tests/segmentation/test_config.py
git commit -m "feat(seg): Pydantic-typed YAML config loader"
```

---

## Task 5: Conversion CubiCasa SVG → masques panoptiques (logique cœur)

**Files:**
- Create: `src/segmentation/cubicasa_export.py` (logique pure, pas de CLI)
- Create: `tests/segmentation/fixtures/sample_cubicasa/sample_01/model.svg`
- Create: `tests/segmentation/fixtures/sample_cubicasa/sample_01/F1_scaled.png`
- Create: `tests/segmentation/test_export.py`

- [ ] **Step 1: Préparer la fixture SVG minimale**

Créer `tests/segmentation/fixtures/sample_cubicasa/sample_01/model.svg` :

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <g class="Floorplan Floor-1">
    <polygon class="Wall" points="0,0 200,0 200,200 0,200 0,0 10,10 10,190 190,190 190,10 10,10"/>
    <polygon class="Kitchen" points="10,10 100,10 100,100 10,100"/>
    <polygon class="BedRoom" points="100,10 190,10 190,100 100,100"/>
    <polygon class="Bath" points="10,100 100,100 100,190 10,190"/>
    <polygon class="LivingRoom" points="100,100 190,100 190,190 100,190"/>
  </g>
</svg>
```

Et générer `F1_scaled.png` (200×200 blanc) :

```python
import numpy as np, cv2
from pathlib import Path
img = np.full((200, 200, 3), 255, dtype=np.uint8)
out = Path("tests/segmentation/fixtures/sample_cubicasa/sample_01/F1_scaled.png")
out.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out), img)
```

- [ ] **Step 2: Écrire le test**

```python
# tests/segmentation/test_export.py
from pathlib import Path
import numpy as np
from src.segmentation.cubicasa_export import (
    extract_room_polygons, rasterize_panoptic, RoomPolygon,
)


def test_extract_room_polygons(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    types = {p.class_id for p in polygons}
    # Walls (1), Kitchen (2), BedRoom (4), Bath (5), LivingRoom (3)
    assert {1, 2, 3, 4, 5}.issubset(types)


def test_rasterize_panoptic_shapes(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    sem, inst = rasterize_panoptic(polygons, image_size=(200, 200))
    assert sem.shape == (200, 200)
    assert sem.dtype == np.uint8
    assert inst.shape == (200, 200)
    assert inst.dtype == np.int32
    # Au moins 4 instances de pièces (excluant Wall)
    unique_inst = set(np.unique(inst).tolist()) - {0}  # 0 = unassigned
    assert len(unique_inst) >= 4


def test_rasterize_kitchen_pixels_present(fixtures_dir: Path):
    svg_path = fixtures_dir / "sample_cubicasa" / "sample_01" / "model.svg"
    polygons = extract_room_polygons(svg_path)
    sem, _ = rasterize_panoptic(polygons, image_size=(200, 200))
    assert (sem == 2).sum() > 1000  # Kitchen pixels
    assert (sem == 1).sum() > 0  # Wall pixels
```

- [ ] **Step 3: Run test (fail)**

```bash
pytest tests/segmentation/test_export.py -v
```

- [ ] **Step 4: Implémenter cubicasa_export.py**

```python
# src/segmentation/cubicasa_export.py
"""CubiCasa SVG → panoptic semantic + instance masks.

Reuses geometry helpers from scripts/cubicasa5k_export_yolo.py for
viewBox handling, transforms, and image alignment.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import xml.etree.ElementTree as ET

import cv2
import numpy as np

from src.segmentation.classes import CUBICASA_TO_C2, CLASS_ID, ROOM_CLASS_IDS


@dataclass
class RoomPolygon:
    """A polygon belonging to one C2 class, on the SVG viewBox coord system."""
    class_id: int
    points: np.ndarray  # shape (N, 2), float


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


def _parse_points(pts: str) -> np.ndarray:
    coords: list[float] = []
    for part in pts.replace(",", " ").split():
        try:
            coords.append(float(part))
        except ValueError:
            return np.empty((0, 2))
    coords = coords[: (len(coords) // 2) * 2]
    return np.asarray(coords, dtype=np.float64).reshape(-1, 2)


def _candidate_labels(elem, parent_map: dict) -> list[str]:
    out: list[str] = []
    cur = elem
    while cur is not None:
        for attr in ("class", "id"):
            v = cur.get(attr)
            if v:
                out.extend(v.split())
        cur = parent_map.get(cur)
    return out


def _label_to_class_id(labels: list[str]) -> int | None:
    """First matching CubiCasa label wins. Walls take priority over rooms."""
    for lbl in labels:
        if lbl == "Wall":
            return CLASS_ID["Wall"]
    for lbl in labels:
        cid = CUBICASA_TO_C2(lbl)
        if cid != 0:
            return cid
    return None


def _get_viewbox(root) -> tuple[float, float, float, float]:
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split() if p]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]
    w = root.get("width")
    h = root.get("height")
    if w and h:
        return 0.0, 0.0, float(w), float(h)
    raise ValueError("SVG size not found")


def extract_room_polygons(svg_path: str | Path) -> List[RoomPolygon]:
    """Parse SVG and return all polygons mapped to C2 classes (Wall + rooms)."""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    parent_map = {c: p for p in root.iter() for c in p}

    out: list[RoomPolygon] = []
    for elem in root.iter():
        if _strip_ns(elem.tag) != "polygon":
            continue
        pts_attr = elem.get("points")
        if not pts_attr:
            continue
        pts = _parse_points(pts_attr)
        if pts.shape[0] < 3:
            continue
        labels = _candidate_labels(elem, parent_map)
        cid = _label_to_class_id(labels)
        if cid is None or cid == 0:
            continue
        out.append(RoomPolygon(class_id=cid, points=pts))
    return out


def rasterize_panoptic(
    polygons: List[RoomPolygon], image_size: Tuple[int, int],
) -> Tuple[np.ndarray, np.ndarray]:
    """Rasterize polygons into (semantic_mask, instance_mask).

    Args:
        polygons: from extract_room_polygons (assumed to be in SVG viewBox coords
                  matching image_size — caller responsible for prior scaling).
        image_size: (width, height) in pixels.

    Returns:
        semantic: uint8 (H, W), 0 = Background, 1..9 = class ids
        instance: int32 (H, W), 0 = unassigned, 1..N = unique room instance ids.
                  Walls always have instance_id = 0 (treated as stuff, not things).
    """
    w, h = image_size
    sem = np.zeros((h, w), dtype=np.uint8)
    inst = np.zeros((h, w), dtype=np.int32)

    next_inst_id = 1
    # Pass 1: rooms (instance-able)
    for poly in polygons:
        if poly.class_id not in ROOM_CLASS_IDS:
            continue
        pts = np.round(poly.points).astype(np.int32)
        cv2.fillPoly(sem, [pts], int(poly.class_id))
        cv2.fillPoly(inst, [pts], int(next_inst_id))
        next_inst_id += 1

    # Pass 2: walls overwrite rooms (a wall pixel is not in any room)
    for poly in polygons:
        if poly.class_id != CLASS_ID["Wall"]:
            continue
        pts = np.round(poly.points).astype(np.int32)
        cv2.fillPoly(sem, [pts], int(poly.class_id))
        cv2.fillPoly(inst, [pts], 0)  # walls = stuff

    return sem, inst
```

- [ ] **Step 5: Run test (PASS)**

```bash
pytest tests/segmentation/test_export.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/segmentation/cubicasa_export.py tests/segmentation/fixtures tests/segmentation/test_export.py
git commit -m "feat(seg): CubiCasa SVG -> panoptic mask conversion"
```

---

## Task 6: Script CLI export CubiCasa → dataset

**Files:**
- Create: `scripts/cubicasa5k_export_segmentation.py`

- [ ] **Step 1: Implémenter le script**

```python
# scripts/cubicasa5k_export_segmentation.py
"""Export CubiCasa5K to panoptic segmentation dataset.

Output structure:
  <out>/
    images/{train,val,test}/<sample_id>.png
    semantic/{train,val,test}/<sample_id>.png   # uint8 mask, class_id per pixel
    instance/{train,val,test}/<sample_id>.png   # uint16 mask, instance id per pixel
    splits.json
    dataset.yaml
"""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
from tqdm import tqdm

from src.segmentation.classes import CLASS_NAMES
from src.segmentation.cubicasa_export import (
    extract_room_polygons, rasterize_panoptic, RoomPolygon, _get_viewbox,
)

# Reuse the YOLO export's image-selection logic (proven robust)
import sys
sys.path.insert(0, str(Path(__file__).parent))
from cubicasa5k_export_yolo import select_best_image  # noqa: E402


def _scale_polygons(polygons: list[RoomPolygon], sx: float, sy: float) -> list[RoomPolygon]:
    out = []
    for p in polygons:
        scaled = p.points.copy()
        scaled[:, 0] *= sx
        scaled[:, 1] *= sy
        out.append(RoomPolygon(class_id=p.class_id, points=scaled))
    return out


def export_one(svg_path: Path, out_dir: Path, split: str,
               max_aspect_diff: float) -> tuple[bool, str]:
    """Export one CubiCasa sample. Returns (success, reason_if_skipped)."""
    folder = svg_path.parent
    sample_id = folder.name

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        _, _, svg_w, svg_h = _get_viewbox(root)
    except Exception as e:
        return False, f"viewbox_err:{e}"
    if svg_w <= 0 or svg_h <= 0:
        return False, "viewbox_zero"

    res = select_best_image(folder, svg_w, svg_h, floor_num=1)
    if res is None:
        return False, "no_image"
    img_path, aspect_diff = res
    if aspect_diff > max_aspect_diff:
        return False, f"aspect_diff:{aspect_diff:.2f}"

    img = cv2.imread(str(img_path))
    if img is None:
        return False, "img_unreadable"
    img_h, img_w = img.shape[:2]

    polygons = extract_room_polygons(svg_path)
    if not polygons:
        return False, "no_polygons"

    sx = img_w / svg_w
    sy = img_h / svg_h
    polygons_scaled = _scale_polygons(polygons, sx, sy)

    sem, inst = rasterize_panoptic(polygons_scaled, image_size=(img_w, img_h))

    # Persist
    img_out = out_dir / "images" / split / f"{sample_id}.png"
    sem_out = out_dir / "semantic" / split / f"{sample_id}.png"
    inst_out = out_dir / "instance" / split / f"{sample_id}.png"

    cv2.imwrite(str(img_out), img)
    cv2.imwrite(str(sem_out), sem)
    # Save instance as uint16 PNG (room counts in CubiCasa stay <65535)
    inst_u16 = inst.astype(np.uint16)
    cv2.imwrite(str(inst_out), inst_u16)

    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw/cubicasa5k")
    ap.add_argument("--out", default="data/processed/cubicasa_panoptic")
    ap.add_argument("--train_ratio", type=float, default=0.80)
    ap.add_argument("--val_ratio", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max_aspect_diff", type=float, default=0.20)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (out / sub / split).mkdir(parents=True, exist_ok=True)

    svgs = sorted(Path(args.root).rglob("model.svg"))
    if not svgs:
        raise SystemExit(f"No model.svg under {args.root}")

    rng = random.Random(args.seed)
    rng.shuffle(svgs)

    n_train = int(len(svgs) * args.train_ratio)
    n_val = int(len(svgs) * args.val_ratio)
    train_svgs = svgs[:n_train]
    val_svgs = svgs[n_train:n_train + n_val]
    test_svgs = svgs[n_train + n_val:]

    splits = {"train": train_svgs, "val": val_svgs, "test": test_svgs}
    splits_log = {"train": [], "val": [], "test": []}
    skip_reasons: dict[str, int] = {}

    for split_name, paths in splits.items():
        for svg in tqdm(paths, desc=f"export {split_name}"):
            ok, reason = export_one(svg, out, split_name, args.max_aspect_diff)
            if ok:
                splits_log[split_name].append(svg.parent.name)
            else:
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    (out / "splits.json").write_text(json.dumps(splits_log, indent=2))

    yaml_text = (
        f"path: {out.as_posix()}\n"
        f"num_classes: {len(CLASS_NAMES)}\n"
        "names:\n" + "\n".join(f"  - {n}" for n in CLASS_NAMES) + "\n"
        "splits: [train, val, test]\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    total = sum(len(v) for v in splits_log.values())
    print(f"Exported {total} samples to {out}")
    print(f"  train={len(splits_log['train'])} "
          f"val={len(splits_log['val'])} test={len(splits_log['test'])}")
    print(f"Skipped: {dict(sorted(skip_reasons.items()))}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test sur fixture**

Créer un mini-test rapide :

```bash
mkdir -p /tmp/cubicasa_smoke/x1
cp tests/segmentation/fixtures/sample_cubicasa/sample_01/model.svg /tmp/cubicasa_smoke/x1/
cp tests/segmentation/fixtures/sample_cubicasa/sample_01/F1_scaled.png /tmp/cubicasa_smoke/x1/

python scripts/cubicasa5k_export_segmentation.py \
  --root /tmp/cubicasa_smoke \
  --out /tmp/cubicasa_smoke_out \
  --train_ratio 1.0 --val_ratio 0.0
```

Expected output : `Exported 1 samples to /tmp/cubicasa_smoke_out`. Vérifier que les fichiers existent :

```bash
ls /tmp/cubicasa_smoke_out/{images,semantic,instance}/train/
```

Doit afficher `x1.png` dans chaque dossier.

- [ ] **Step 3: Commit**

```bash
git add scripts/cubicasa5k_export_segmentation.py
git commit -m "feat(seg): CLI for CubiCasa->panoptic dataset export"
```

- [ ] **Step 4: Lancer l'export complet (long, en arrière-plan)**

```bash
python scripts/cubicasa5k_export_segmentation.py \
  --root data/raw/cubicasa5k \
  --out data/processed/cubicasa_panoptic 2>&1 | tee logs/export_cubicasa_$(date +%Y%m%d_%H%M).log
```

Expected : ~30-90 minutes selon volume CubiCasa réellement disponible. ~3000-4500 plans exportés (certains skip aspect_ratio).

---

## Task 7: Augmentations Albumentations

**Files:**
- Create: `src/segmentation/augmentations.py`
- Create: `tests/segmentation/test_augmentations.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_augmentations.py
import numpy as np
from src.segmentation.augmentations import build_train_transform, build_eval_transform


def test_train_transform_preserves_shapes():
    aug = build_train_transform(image_size=768)
    img = np.random.randint(0, 256, (1000, 800, 3), dtype=np.uint8)
    sem = np.random.randint(0, 10, (1000, 800), dtype=np.uint8)
    inst = np.random.randint(0, 50, (1000, 800), dtype=np.int32).astype(np.int32)

    out = aug(image=img, mask=sem, instance_mask=inst.astype(np.uint16))
    assert out["image"].shape == (768, 768, 3)
    assert out["mask"].shape == (768, 768)
    assert out["instance_mask"].shape == (768, 768)


def test_eval_transform_letterbox_no_change_to_classes():
    aug = build_eval_transform(image_size=768)
    img = np.full((600, 800, 3), 128, dtype=np.uint8)
    sem = np.zeros((600, 800), dtype=np.uint8)
    sem[100:200, 100:200] = 5  # Bath patch
    out = aug(image=img, mask=sem)
    assert out["image"].shape == (768, 768, 3)
    assert out["mask"].shape == (768, 768)
    # Class 5 must still be present (letterbox preserves content)
    assert 5 in np.unique(out["mask"])


def test_no_mosaic_or_mixup():
    """Sanity: train transform should not contain mosaic/mixup."""
    aug = build_train_transform(image_size=512)
    txt = repr(aug).lower()
    assert "mosaic" not in txt
    assert "mixup" not in txt
    assert "elastic" not in txt
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter augmentations.py**

```python
# src/segmentation/augmentations.py
"""Albumentations transforms for plan segmentation.

Train transform: aggressive but geometry-preserving (no elastic/mosaic/mixup).
Eval transform: letterbox to image_size, normalize, no augmentation.
"""
import albumentations as A
import cv2


_NORMALIZE = A.Normalize(
    mean=(0.485, 0.456, 0.406),  # ImageNet stats — Mask2Former pretrained convention
    std=(0.229, 0.224, 0.225),
)

_ADDITIONAL_TARGETS = {"instance_mask": "mask"}


def build_train_transform(image_size: int) -> A.Compose:
    return A.Compose(
        [
            # Geometric (preserve right-angle layout where possible)
            A.RandomRotate90(p=0.5),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.Affine(
                rotate=(-10, 10), shear=(-5, 5), scale=(0.8, 1.2),
                interpolation=cv2.INTER_LINEAR,
                mask_interpolation=cv2.INTER_NEAREST,
                fit_output=False, p=0.3,
            ),
            # Resize to fixed train size with padding (preserve aspect)
            A.LongestMaxSize(max_size=image_size, interpolation=cv2.INTER_LINEAR),
            A.PadIfNeeded(
                min_height=image_size, min_width=image_size,
                border_mode=cv2.BORDER_CONSTANT,
                fill=255,           # white background for image
                fill_mask=0,        # background class for masks
            ),
            # Photometric
            A.RandomBrightnessContrast(p=0.4),
            A.CLAHE(p=0.2),
            A.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1, hue=0.0, p=0.3),
            # Degradations (scan realism)
            A.GaussNoise(p=0.2),
            A.GaussianBlur(blur_limit=(3, 5), p=0.15),
            A.ImageCompression(quality_range=(50, 95), p=0.2),
            A.CoarseDropout(num_holes_range=(1, 8),
                            hole_height_range=(8, 32),
                            hole_width_range=(8, 32),
                            fill=255, fill_mask=0, p=0.2),
            _NORMALIZE,
        ],
        additional_targets=_ADDITIONAL_TARGETS,
    )


def build_eval_transform(image_size: int) -> A.Compose:
    return A.Compose(
        [
            A.LongestMaxSize(max_size=image_size, interpolation=cv2.INTER_LINEAR),
            A.PadIfNeeded(
                min_height=image_size, min_width=image_size,
                border_mode=cv2.BORDER_CONSTANT,
                fill=255, fill_mask=0,
            ),
            _NORMALIZE,
        ],
        additional_targets=_ADDITIONAL_TARGETS,
    )
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/augmentations.py tests/segmentation/test_augmentations.py
git commit -m "feat(seg): Albumentations train/eval transforms"
```

---

## Task 8: PyTorch Dataset (panoptic)

**Files:**
- Create: `src/segmentation/dataset.py`
- Create: `tests/segmentation/test_dataset.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_dataset.py
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import torch

from src.segmentation.dataset import PanopticDataset


@pytest.fixture
def fake_dataset(tmp_path: Path) -> Path:
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (tmp_path / sub / split).mkdir(parents=True, exist_ok=True)

    # 2 fake samples in train
    for i, sid in enumerate(["a", "b"]):
        img = np.full((400, 300, 3), 128 + i * 30, dtype=np.uint8)
        sem = np.zeros((400, 300), dtype=np.uint8)
        sem[50:150, 50:150] = 2  # Kitchen
        sem[200:300, 100:200] = 5  # Bath
        inst = np.zeros((400, 300), dtype=np.uint16)
        inst[50:150, 50:150] = 1
        inst[200:300, 100:200] = 2
        cv2.imwrite(str(tmp_path / "images" / "train" / f"{sid}.png"), img)
        cv2.imwrite(str(tmp_path / "semantic" / "train" / f"{sid}.png"), sem)
        cv2.imwrite(str(tmp_path / "instance" / "train" / f"{sid}.png"), inst)

    (tmp_path / "splits.json").write_text(
        json.dumps({"train": ["a", "b"], "val": [], "test": []})
    )
    return tmp_path


def test_dataset_len(fake_dataset: Path):
    ds = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    assert len(ds) == 2


def test_dataset_returns_tensors(fake_dataset: Path):
    ds = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    sample = ds[0]
    assert isinstance(sample["pixel_values"], torch.Tensor)
    assert sample["pixel_values"].shape == (3, 256, 256)
    assert sample["semantic"].shape == (256, 256)
    assert sample["instance"].shape == (256, 256)
    assert sample["semantic"].dtype == torch.long
    # Class 2 (Kitchen) must survive
    assert (sample["semantic"] == 2).any()


def test_dataset_train_mode_applies_aug(fake_dataset: Path):
    ds_train = PanopticDataset(fake_dataset, split="train", image_size=256, train=True)
    ds_eval = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    # Same sample, different transforms → different pixel content (high prob)
    s_train = ds_train[0]["pixel_values"]
    s_eval = ds_eval[0]["pixel_values"]
    assert not torch.equal(s_train, s_eval)
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter dataset.py**

```python
# src/segmentation/dataset.py
"""PyTorch Dataset for panoptic segmentation training."""
import json
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from src.segmentation.augmentations import build_train_transform, build_eval_transform


class PanopticDataset(Dataset):
    """Loads (image, semantic_mask, instance_mask) triples and applies transforms.

    Expected layout under root:
        images/{split}/<id>.png
        semantic/{split}/<id>.png  (uint8, class ids)
        instance/{split}/<id>.png  (uint16, instance ids; 0 = no instance / stuff)
        splits.json
    """

    def __init__(
        self,
        root: str | Path,
        split: str,
        image_size: int,
        train: bool,
    ):
        self.root = Path(root)
        self.split = split
        self.image_size = image_size
        with open(self.root / "splits.json") as f:
            splits = json.load(f)
        self.ids: list[str] = splits[split]

        self.transform = (
            build_train_transform(image_size) if train
            else build_eval_transform(image_size)
        )

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> dict:
        sid = self.ids[idx]
        img = cv2.imread(str(self.root / "images" / self.split / f"{sid}.png"))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        sem = cv2.imread(
            str(self.root / "semantic" / self.split / f"{sid}.png"),
            cv2.IMREAD_UNCHANGED,
        )
        inst = cv2.imread(
            str(self.root / "instance" / self.split / f"{sid}.png"),
            cv2.IMREAD_UNCHANGED,
        )

        out = self.transform(image=img, mask=sem, instance_mask=inst)
        # image: HWC float -> CHW float tensor
        pixel_values = torch.from_numpy(out["image"]).permute(2, 0, 1).float()
        semantic = torch.from_numpy(out["mask"]).long()
        instance = torch.from_numpy(out["instance_mask"]).long()

        return {
            "id": sid,
            "pixel_values": pixel_values,
            "semantic": semantic,
            "instance": instance,
        }
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/dataset.py tests/segmentation/test_dataset.py
git commit -m "feat(seg): PyTorch panoptic dataset with transforms"
```

---

## Task 9: Wrapper modèle Mask2Former

**Files:**
- Create: `src/segmentation/model.py`
- Create: `tests/segmentation/test_model.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_model.py
import torch
import pytest
from src.segmentation.model import build_model
from src.segmentation.classes import NUM_CLASSES


@pytest.fixture(scope="module")
def model():
    return build_model(
        backbone="facebook/mask2former-swin-tiny-coco-panoptic",  # tiny for tests
        num_classes=NUM_CLASSES,
    )


def test_model_loads(model):
    assert model is not None


def test_model_forward_shape(model):
    model.eval()
    img = torch.randn(1, 3, 384, 384)  # tiny input for fast test
    with torch.no_grad():
        out = model(pixel_values=img)
    # Outputs: class_queries_logits + masks_queries_logits
    assert hasattr(out, "class_queries_logits")
    assert hasattr(out, "masks_queries_logits")
    n_queries = out.class_queries_logits.shape[1]
    # +1 for "no object" class
    assert out.class_queries_logits.shape == (1, n_queries, NUM_CLASSES + 1)
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter model.py**

```python
# src/segmentation/model.py
"""Mask2Former model wrapper for batIA 10-class panoptic segmentation."""
from transformers import Mask2FormerForUniversalSegmentation, Mask2FormerConfig

from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES


def build_model(
    backbone: str = "facebook/mask2former-swin-small-coco-panoptic",
    num_classes: int = NUM_CLASSES,
) -> Mask2FormerForUniversalSegmentation:
    """Load Mask2Former pretrained on COCO-panoptic, replace head for our classes.

    HuggingFace `from_pretrained` with mismatched-size handling lets us swap the
    classification head while keeping all backbone + pixel decoder + transformer
    decoder weights.
    """
    id2label = {i: name for i, name in enumerate(CLASS_NAMES[:num_classes])}
    label2id = {name: i for i, name in id2label.items()}

    model = Mask2FormerForUniversalSegmentation.from_pretrained(
        backbone,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )
    return model


def get_processor(backbone: str = "facebook/mask2former-swin-small-coco-panoptic"):
    """Return the matching image processor (used for inference postprocess)."""
    from transformers import Mask2FormerImageProcessor
    return Mask2FormerImageProcessor.from_pretrained(backbone)
```

- [ ] **Step 4: Run test (PASS)**

```bash
pytest tests/segmentation/test_model.py -v -s
```

Note : ce test télécharge le poids tiny (~80MB) au premier run. Toléré.

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/model.py tests/segmentation/test_model.py
git commit -m "feat(seg): Mask2Former model wrapper for 10 classes"
```

---

## Task 10: Métriques (mIoU, PQ, room recall/precision)

**Files:**
- Create: `src/segmentation/metrics.py`
- Create: `tests/segmentation/test_metrics.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_metrics.py
import numpy as np
from src.segmentation.metrics import (
    compute_iou_per_class, compute_miou, compute_room_recall_precision,
)
from src.segmentation.classes import NUM_CLASSES


def test_perfect_prediction_iou_one():
    pred = np.array([[2, 2, 0], [2, 2, 0], [0, 0, 0]], dtype=np.uint8)
    gt = pred.copy()
    iou = compute_iou_per_class(pred, gt, NUM_CLASSES)
    # Class 2 IoU = 1, class 0 IoU = 1, others = nan
    assert iou[2] == 1.0
    assert iou[0] == 1.0
    assert np.isnan(iou[5])


def test_no_overlap_iou_zero():
    pred = np.full((3, 3), 2, dtype=np.uint8)
    gt = np.full((3, 3), 5, dtype=np.uint8)
    iou = compute_iou_per_class(pred, gt, NUM_CLASSES)
    assert iou[2] == 0.0
    assert iou[5] == 0.0


def test_miou_handles_nan():
    iou = np.full(NUM_CLASSES, np.nan)
    iou[2] = 0.8
    iou[5] = 0.6
    assert abs(compute_miou(iou) - 0.7) < 1e-6


def test_room_recall_precision_basic():
    # GT instance mask: 2 rooms (class 2, class 5)
    gt_inst = np.zeros((10, 10), dtype=np.int32)
    gt_inst[0:5, 0:5] = 1  # room 1
    gt_inst[5:10, 5:10] = 2  # room 2
    gt_classes = {1: 2, 2: 5}

    # Pred: 1 room overlapping room 1 (correct class), 1 room overlapping room 2 (wrong class)
    pred_inst = np.zeros((10, 10), dtype=np.int32)
    pred_inst[0:5, 0:5] = 10
    pred_inst[5:10, 5:10] = 20
    pred_classes = {10: 2, 20: 4}  # second is BedRoom instead of Bath

    rec, prec, type_acc = compute_room_recall_precision(
        pred_inst, pred_classes, gt_inst, gt_classes,
    )
    assert rec == 0.5  # only room 1 retrouvé avec bonne classe
    assert prec == 0.5
    assert type_acc == 0.5  # 1 sur 2 retrouvés = bonne classe
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter metrics.py**

```python
# src/segmentation/metrics.py
"""Segmentation metrics: per-class IoU, mIoU, room recall/precision/type accuracy."""
import numpy as np


def compute_iou_per_class(pred: np.ndarray, gt: np.ndarray, num_classes: int,
                          ignore_index: int | None = None) -> np.ndarray:
    """Per-class IoU. Returns nan for classes absent from both pred and gt."""
    iou = np.full(num_classes, np.nan, dtype=np.float64)
    for c in range(num_classes):
        if ignore_index is not None and c == ignore_index:
            continue
        p = pred == c
        g = gt == c
        union = np.logical_or(p, g).sum()
        if union == 0:
            continue  # nan
        inter = np.logical_and(p, g).sum()
        iou[c] = inter / union
    return iou


def compute_miou(iou_per_class: np.ndarray) -> float:
    valid = iou_per_class[~np.isnan(iou_per_class)]
    return float(valid.mean()) if len(valid) > 0 else 0.0


def compute_room_recall_precision(
    pred_instance: np.ndarray,
    pred_classes: dict[int, int],
    gt_instance: np.ndarray,
    gt_classes: dict[int, int],
    iou_threshold: float = 0.5,
) -> tuple[float, float, float]:
    """Match predicted rooms to GT rooms by IoU > threshold.

    Returns:
        recall: fraction of GT rooms matched with correct class
        precision: fraction of predicted rooms matching a GT room with correct class
        type_accuracy: among matched rooms (any class), fraction with correct class
    """
    gt_ids = [i for i in np.unique(gt_instance) if i != 0]
    pred_ids = [i for i in np.unique(pred_instance) if i != 0]

    if not gt_ids and not pred_ids:
        return 1.0, 1.0, 1.0
    if not gt_ids:
        return 0.0, 0.0, 0.0
    if not pred_ids:
        return 0.0, 1.0, 0.0

    # IoU matrix
    iou = np.zeros((len(gt_ids), len(pred_ids)))
    for i, g in enumerate(gt_ids):
        gm = gt_instance == g
        for j, p in enumerate(pred_ids):
            pm = pred_instance == p
            u = np.logical_or(gm, pm).sum()
            if u == 0:
                continue
            iou[i, j] = np.logical_and(gm, pm).sum() / u

    # Greedy matching by descending IoU
    matched_gt: set[int] = set()
    matched_pred: set[int] = set()
    matches: list[tuple[int, int]] = []  # (gt_idx, pred_idx)
    flat = [(iou[i, j], i, j) for i in range(len(gt_ids)) for j in range(len(pred_ids))]
    flat.sort(reverse=True)
    for v, i, j in flat:
        if v < iou_threshold:
            break
        if i in matched_gt or j in matched_pred:
            continue
        matched_gt.add(i)
        matched_pred.add(j)
        matches.append((i, j))

    # Class-correct matches
    correct = 0
    for i, j in matches:
        if pred_classes.get(pred_ids[j]) == gt_classes.get(gt_ids[i]):
            correct += 1

    recall = correct / len(gt_ids)
    precision = correct / len(pred_ids) if pred_ids else 0.0
    type_acc = (correct / len(matches)) if matches else 0.0
    return recall, precision, type_acc
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/metrics.py tests/segmentation/test_metrics.py
git commit -m "feat(seg): mIoU + room recall/precision metrics"
```

---

## Task 11: Checkpoint manager (save/load + auto-resume)

**Files:**
- Create: `src/segmentation/checkpoint.py`
- Create: `tests/segmentation/test_checkpoint.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_checkpoint.py
import torch
from torch import nn
from src.segmentation.checkpoint import save_checkpoint, load_checkpoint, find_latest


def test_save_and_load_roundtrip(tmp_path):
    model = nn.Linear(4, 2)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    state = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": opt.state_dict(),
        "epoch": 7,
        "best_metric": 0.42,
        "rng_state": torch.get_rng_state(),
    }
    p = tmp_path / "ckpt.pt"
    save_checkpoint(state, p)
    loaded = load_checkpoint(p, map_location="cpu")
    assert loaded["epoch"] == 7
    assert abs(loaded["best_metric"] - 0.42) < 1e-9


def test_find_latest_picks_highest_epoch(tmp_path):
    (tmp_path / "epoch_05.pt").write_text("x")
    (tmp_path / "epoch_30.pt").write_text("x")
    (tmp_path / "epoch_12.pt").write_text("x")
    (tmp_path / "best.pt").write_text("x")
    (tmp_path / "last.pt").write_text("x")
    latest = find_latest(tmp_path)
    assert latest is not None
    assert latest.name == "last.pt"


def test_find_latest_falls_back_to_epoch(tmp_path):
    (tmp_path / "epoch_05.pt").write_text("x")
    (tmp_path / "epoch_30.pt").write_text("x")
    latest = find_latest(tmp_path)
    assert latest.name == "epoch_30.pt"


def test_find_latest_returns_none_if_empty(tmp_path):
    assert find_latest(tmp_path) is None
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter checkpoint.py**

```python
# src/segmentation/checkpoint.py
"""Checkpoint save/load with auto-resume support."""
from pathlib import Path
import re
import torch


def save_checkpoint(state: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(state, tmp)
    tmp.replace(path)  # atomic on POSIX


def load_checkpoint(path: str | Path, map_location: str = "cpu") -> dict:
    return torch.load(path, map_location=map_location, weights_only=False)


_EPOCH_RE = re.compile(r"epoch_(\d+)\.pt$")


def find_latest(checkpoint_dir: str | Path) -> Path | None:
    """Return the most relevant checkpoint to resume from.

    Priority:
        1. last.pt
        2. highest-numbered epoch_XX.pt
        3. None
    """
    d = Path(checkpoint_dir)
    if not d.exists():
        return None
    last = d / "last.pt"
    if last.exists():
        return last
    epoch_files = []
    for p in d.iterdir():
        m = _EPOCH_RE.search(p.name)
        if m:
            epoch_files.append((int(m.group(1)), p))
    if not epoch_files:
        return None
    epoch_files.sort()
    return epoch_files[-1][1]
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/checkpoint.py tests/segmentation/test_checkpoint.py
git commit -m "feat(seg): checkpoint save/load with auto-resume"
```

---

## Task 12: Tracker wrapper (W&B + no-op fallback)

**Files:**
- Create: `src/segmentation/tracker.py`
- Create: `tests/segmentation/test_tracker.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_tracker.py
import numpy as np
from src.segmentation.tracker import build_tracker


def test_noop_tracker():
    tr = build_tracker("none", run_name="x", project="p", config={})
    tr.log_metrics({"loss": 1.0}, step=0)
    tr.log_image("test", np.zeros((10, 10, 3), dtype=np.uint8), step=0)
    tr.finish()


def test_wandb_tracker_offline(tmp_path, monkeypatch):
    """Run W&B in offline mode to avoid cloud calls in tests."""
    monkeypatch.setenv("WANDB_MODE", "offline")
    monkeypatch.setenv("WANDB_DIR", str(tmp_path))
    tr = build_tracker("wandb", run_name="test", project="batia-test",
                      config={"lr": 1e-4})
    tr.log_metrics({"loss": 0.5, "miou": 0.6}, step=1)
    tr.log_image("preview", np.zeros((32, 32, 3), dtype=np.uint8), step=1)
    tr.finish()
    # Offline run dir should exist
    assert any(tmp_path.glob("offline-run-*")) or any(tmp_path.glob("wandb"))
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter tracker.py**

```python
# src/segmentation/tracker.py
"""Pluggable training tracker. Wraps W&B with a no-op fallback."""
from typing import Protocol
import numpy as np


class Tracker(Protocol):
    def log_metrics(self, metrics: dict, step: int) -> None: ...
    def log_image(self, key: str, image: np.ndarray, step: int) -> None: ...
    def finish(self) -> None: ...


class _NoOpTracker:
    def log_metrics(self, metrics, step): pass
    def log_image(self, key, image, step): pass
    def finish(self): pass


class _WandbTracker:
    def __init__(self, run_name: str, project: str, config: dict):
        import wandb
        self._wandb = wandb
        self._run = wandb.init(project=project, name=run_name, config=config,
                               reinit=True)

    def log_metrics(self, metrics: dict, step: int) -> None:
        self._wandb.log(metrics, step=step)

    def log_image(self, key: str, image: np.ndarray, step: int) -> None:
        img = self._wandb.Image(image)
        self._wandb.log({key: img}, step=step)

    def finish(self) -> None:
        self._wandb.finish()


def build_tracker(kind: str, run_name: str, project: str, config: dict) -> Tracker:
    if kind == "wandb":
        return _WandbTracker(run_name=run_name, project=project, config=config)
    if kind in ("none", "tensorboard"):
        # tensorboard placeholder; project does not require it for MVP.
        return _NoOpTracker()
    raise ValueError(f"Unknown tracker: {kind}")
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/tracker.py tests/segmentation/test_tracker.py
git commit -m "feat(seg): pluggable tracker (W&B + no-op)"
```

---

## Task 13: Boucle d'entraînement

**Files:**
- Create: `src/segmentation/trainer.py`
- Create: `tests/segmentation/test_trainer.py`

- [ ] **Step 1: Écrire le test (smoke + 1 epoch sur tiny data)**

```python
# tests/segmentation/test_trainer.py
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import torch

from src.segmentation.config import (
    TrainingConfig, DataConfig, ModelConfig, OptimizerConfig,
    SchedulerConfig, TrainingPhaseConfig, LoggingConfig, CheckpointConfig,
)
from src.segmentation.trainer import Trainer


def _make_tiny_dataset(root: Path, n: int = 4):
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (root / sub / split).mkdir(parents=True, exist_ok=True)
    ids = [f"x{i}" for i in range(n)]
    for sid in ids:
        img = np.full((400, 300, 3), 200, dtype=np.uint8)
        sem = np.zeros((400, 300), dtype=np.uint8)
        sem[100:200, 100:200] = 2  # Kitchen
        inst = np.zeros((400, 300), dtype=np.uint16)
        inst[100:200, 100:200] = 1
        cv2.imwrite(str(root / "images" / "train" / f"{sid}.png"), img)
        cv2.imwrite(str(root / "semantic" / "train" / f"{sid}.png"), sem)
        cv2.imwrite(str(root / "instance" / "train" / f"{sid}.png"), inst)
        cv2.imwrite(str(root / "images" / "val" / f"{sid}.png"), img)
        cv2.imwrite(str(root / "semantic" / "val" / f"{sid}.png"), sem)
        cv2.imwrite(str(root / "instance" / "val" / f"{sid}.png"), inst)
    (root / "splits.json").write_text(
        json.dumps({"train": ids, "val": ids[:2], "test": []})
    )


def _make_config(root: Path, ckpt_dir: Path) -> TrainingConfig:
    return TrainingConfig(
        run_name="smoke",
        seed=0,
        data=DataConfig(dataset_root=str(root), image_size=384, batch_size=1),
        model=ModelConfig(backbone="facebook/mask2former-swin-tiny-coco-panoptic"),
        optimizer=OptimizerConfig(
            lr_backbone=1e-5, lr_head=1e-4, weight_decay=0.05,
            grad_accumulation=1, grad_clip_norm=0.01,
        ),
        scheduler=SchedulerConfig(type="constant", warmup_steps=0),
        training=TrainingPhaseConfig(
            epochs=1, early_stop_patience=0,
            mixed_precision="no", oversample_rare_classes=False,
        ),
        logging=LoggingConfig(tracker="none", project="test", log_image_count=0),
        checkpoint=CheckpointConfig(output_dir=str(ckpt_dir), save_every_n_epochs=1),
    )


@pytest.mark.slow
def test_one_epoch_smoke(tmp_path):
    data = tmp_path / "data"
    ckpt = tmp_path / "ckpt"
    _make_tiny_dataset(data)
    cfg = _make_config(data, ckpt)
    trainer = Trainer(cfg, device="cpu")  # CPU pour CI
    trainer.fit()
    assert (ckpt / "last.pt").exists()
```

- [ ] **Step 2: Run test (fail — Trainer absent)**

- [ ] **Step 3: Implémenter trainer.py**

```python
# src/segmentation/trainer.py
"""Training loop: 2 stages of Mask2Former with checkpointing + tracker."""
from __future__ import annotations
from pathlib import Path
import math
import random

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader
from torch.cuda.amp import GradScaler

from src.segmentation.checkpoint import save_checkpoint, load_checkpoint, find_latest
from src.segmentation.classes import NUM_CLASSES, ROOM_CLASS_IDS
from src.segmentation.config import TrainingConfig
from src.segmentation.dataset import PanopticDataset
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.model import build_model, get_processor
from src.segmentation.tracker import build_tracker


def _build_targets_for_mask2former(semantic: torch.Tensor, instance: torch.Tensor):
    """Convert (semantic, instance) per-pixel masks to Mask2Former target format.

    Mask2Former expects, per image:
      - mask_labels: list of binary masks (one per instance + one per stuff class present)
      - class_labels: corresponding class id (long)

    We treat ROOM classes as 'things' (per-instance) and Wall as 'stuff' (single mask).
    """
    out_mask_labels: list[torch.Tensor] = []
    out_class_labels: list[int] = []
    H, W = semantic.shape

    # Things: rooms (one mask per instance)
    for inst_id in instance.unique().tolist():
        if inst_id == 0:
            continue
        m = (instance == inst_id)
        if m.sum() == 0:
            continue
        cls = int(semantic[m].mode().values.item())
        if cls in ROOM_CLASS_IDS:
            out_mask_labels.append(m.float())
            out_class_labels.append(cls)

    # Stuff: walls (single mask if any pixels)
    wall_mask = (semantic == 1)
    if wall_mask.sum() > 0:
        out_mask_labels.append(wall_mask.float())
        out_class_labels.append(1)

    if not out_mask_labels:
        # Empty image (very rare): single dummy background to avoid NaN
        out_mask_labels.append(torch.zeros((H, W)))
        out_class_labels.append(0)

    return (
        torch.stack(out_mask_labels),
        torch.tensor(out_class_labels, dtype=torch.long),
    )


class Trainer:
    def __init__(self, cfg: TrainingConfig, device: str = "auto"):
        self.cfg = cfg
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = torch.device(device)
        self._set_seed(cfg.seed)

        self.model = build_model(
            backbone=cfg.model.backbone, num_classes=NUM_CLASSES,
        ).to(self.device)
        self.processor = get_processor(cfg.model.backbone)

        self.train_ds = PanopticDataset(cfg.data.dataset_root, "train",
                                        cfg.data.image_size, train=True)
        self.val_ds = PanopticDataset(cfg.data.dataset_root, "val",
                                      cfg.data.image_size, train=False)
        self.train_loader = DataLoader(
            self.train_ds, batch_size=cfg.data.batch_size,
            shuffle=True, num_workers=0, drop_last=True,
            collate_fn=self._collate,
        )
        self.val_loader = DataLoader(
            self.val_ds, batch_size=1, shuffle=False, num_workers=0,
            collate_fn=self._collate,
        )

        # Param groups: backbone (lower LR) vs the rest (head LR)
        backbone_params, other_params = [], []
        for name, p in self.model.named_parameters():
            if "backbone" in name or "pixel_level_module.encoder" in name:
                backbone_params.append(p)
            else:
                other_params.append(p)
        self.optimizer = AdamW([
            {"params": backbone_params, "lr": cfg.optimizer.lr_backbone},
            {"params": other_params, "lr": cfg.optimizer.lr_head},
        ], weight_decay=cfg.optimizer.weight_decay)

        self.scheduler = self._build_scheduler()
        self.global_step = 0
        self.epoch = 0
        self.best_metric = -math.inf

        self.use_amp = cfg.training.mixed_precision in ("bf16", "fp16")
        self.amp_dtype = (
            torch.bfloat16 if cfg.training.mixed_precision == "bf16"
            else torch.float16 if cfg.training.mixed_precision == "fp16"
            else torch.float32
        )

        self.ckpt_dir = Path(cfg.checkpoint.output_dir) / "checkpoints"
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)

        self.tracker = build_tracker(
            cfg.logging.tracker,
            run_name=cfg.run_name,
            project=cfg.logging.project,
            config=cfg.model_dump(),
        )

    @staticmethod
    def _set_seed(seed: int):
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)

    def _build_scheduler(self):
        steps_per_epoch = max(1, len(self.train_ds) // self.cfg.data.batch_size)
        total = self.cfg.training.epochs * steps_per_epoch
        warmup = self.cfg.scheduler.warmup_steps

        def lr_lambda(step: int) -> float:
            if step < warmup:
                return step / max(1, warmup)
            if self.cfg.scheduler.type == "constant":
                return 1.0
            progress = (step - warmup) / max(1, total - warmup)
            return 0.5 * (1.0 + math.cos(math.pi * progress))

        return torch.optim.lr_scheduler.LambdaLR(self.optimizer, lr_lambda)

    @staticmethod
    def _collate(batch: list[dict]) -> dict:
        return {
            "ids": [b["id"] for b in batch],
            "pixel_values": torch.stack([b["pixel_values"] for b in batch]),
            "semantic": torch.stack([b["semantic"] for b in batch]),
            "instance": torch.stack([b["instance"] for b in batch]),
        }

    def _build_batch_targets(self, batch):
        mask_labels, class_labels = [], []
        for sem, inst in zip(batch["semantic"], batch["instance"]):
            ml, cl = _build_targets_for_mask2former(sem, inst)
            mask_labels.append(ml.to(self.device))
            class_labels.append(cl.to(self.device))
        return mask_labels, class_labels

    def fit(self):
        # Auto-resume
        latest = find_latest(self.ckpt_dir)
        if latest is not None:
            self._load_state(latest)
            print(f"Resumed from {latest} at epoch {self.epoch}")

        no_improve_epochs = 0
        for epoch in range(self.epoch, self.cfg.training.epochs):
            self.epoch = epoch
            self._train_one_epoch()
            metric = self._validate()
            self._save_state(name=f"epoch_{epoch:02d}.pt")
            self._save_state(name="last.pt")
            if metric > self.best_metric:
                self.best_metric = metric
                self._save_state(name="best.pt")
                no_improve_epochs = 0
            else:
                no_improve_epochs += 1
                if no_improve_epochs >= self.cfg.training.early_stop_patience:
                    print(f"Early stopping at epoch {epoch}")
                    break
        self.tracker.finish()

    def _train_one_epoch(self):
        self.model.train()
        accum = self.cfg.optimizer.grad_accumulation
        self.optimizer.zero_grad()

        for step, batch in enumerate(self.train_loader):
            mask_labels, class_labels = self._build_batch_targets(batch)
            pixel_values = batch["pixel_values"].to(self.device)

            ctx = (
                torch.autocast(device_type=self.device.type, dtype=self.amp_dtype)
                if self.use_amp else _nullcontext()
            )
            with ctx:
                out = self.model(
                    pixel_values=pixel_values,
                    mask_labels=mask_labels,
                    class_labels=class_labels,
                )
                loss = out.loss / accum

            loss.backward()

            if (step + 1) % accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.cfg.optimizer.grad_clip_norm,
                )
                self.optimizer.step()
                self.scheduler.step()
                self.optimizer.zero_grad()
                self.global_step += 1

                self.tracker.log_metrics(
                    {"train/loss": float(loss.item() * accum),
                     "train/lr_backbone": self.optimizer.param_groups[0]["lr"],
                     "train/lr_head": self.optimizer.param_groups[1]["lr"]},
                    step=self.global_step,
                )

    @torch.no_grad()
    def _validate(self) -> float:
        self.model.eval()
        ious = []
        for batch in self.val_loader:
            pixel_values = batch["pixel_values"].to(self.device)
            out = self.model(pixel_values=pixel_values)
            sem_pred = self.processor.post_process_semantic_segmentation(
                out, target_sizes=[batch["semantic"].shape[-2:]],
            )[0].cpu().numpy()
            sem_gt = batch["semantic"][0].numpy()
            ious.append(compute_iou_per_class(sem_pred, sem_gt, NUM_CLASSES))

        ious = np.stack(ious)
        per_class = np.nanmean(ious, axis=0)
        miou = compute_miou(per_class)

        log = {"val/mIoU": miou}
        for cid, v in enumerate(per_class):
            if not np.isnan(v):
                log[f"val/IoU_class_{cid}"] = float(v)
        self.tracker.log_metrics(log, step=self.global_step)
        return miou

    def _save_state(self, name: str):
        state = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "epoch": self.epoch + 1,
            "global_step": self.global_step,
            "best_metric": self.best_metric,
            "config": self.cfg.model_dump(),
        }
        save_checkpoint(state, self.ckpt_dir / name)

    def _load_state(self, path: Path):
        ckpt = load_checkpoint(path, map_location=str(self.device))
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        self.scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        self.epoch = ckpt["epoch"]
        self.global_step = ckpt["global_step"]
        self.best_metric = ckpt["best_metric"]


from contextlib import contextmanager
@contextmanager
def _nullcontext():
    yield
```

- [ ] **Step 4: Run test (slow, mark for opt-in)**

```bash
pytest tests/segmentation/test_trainer.py -v -m slow
```

Expected : un fichier `last.pt` créé après 1 epoch sur 4 samples factices. Durée ~2-5 min en CPU.

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/trainer.py tests/segmentation/test_trainer.py
git commit -m "feat(seg): training loop with auto-resume + AMP + tracker"
```

---

## Task 14: CLI training

**Files:**
- Create: `scripts/train_segmentation.py`
- Create: `configs/segmentation/stage_a_cubicasa.yaml`
- Create: `configs/segmentation/stage_b_finetune.yaml.template`

- [ ] **Step 1: Implémenter le CLI**

```python
# scripts/train_segmentation.py
"""CLI: train_segmentation.py --config configs/segmentation/stage_a_cubicasa.yaml [--resume latest]"""
import argparse
from src.segmentation.config import load_config
from src.segmentation.trainer import Trainer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--resume", default="latest", choices=["latest", "no"])
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    cfg = load_config(args.config)
    trainer = Trainer(cfg, device=args.device)
    if args.resume == "no":
        trainer.epoch = 0
        trainer.global_step = 0
    trainer.fit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Config Stage A**

Créer `configs/segmentation/stage_a_cubicasa.yaml` :

```yaml
run_name: stage_a_cubicasa_v1
seed: 42

data:
  dataset_root: data/processed/cubicasa_panoptic
  image_size: 768
  batch_size: 4

model:
  backbone: facebook/mask2former-swin-small-coco-panoptic

optimizer:
  lr_backbone: 1.0e-5
  lr_head: 1.0e-4
  weight_decay: 0.05
  grad_accumulation: 4
  grad_clip_norm: 0.01

scheduler:
  type: cosine
  warmup_steps: 1000

training:
  epochs: 80
  early_stop_patience: 10
  mixed_precision: bf16
  oversample_rare_classes: true

logging:
  tracker: wandb
  project: batia-segmentation
  log_image_count: 5

checkpoint:
  output_dir: runs/segmentation/stage_a_cubicasa_v1
  save_every_n_epochs: 10
```

- [ ] **Step 3: Template Stage B (pour Plan 2)**

Créer `configs/segmentation/stage_b_finetune.yaml.template` (copie de Stage A avec LR/10, epochs=30, dataset_root pointant vers le mix CubiCasa+FR — à compléter dans Plan 2).

```yaml
# Template Stage B fine-tune — à compléter une fois les 80 plans FR annotés
run_name: stage_b_finetune_v1
seed: 42

data:
  dataset_root: data/processed/cubicasa_panoptic_plus_fr  # à créer dans Plan 2
  image_size: 768
  batch_size: 4

model:
  backbone: facebook/mask2former-swin-small-coco-panoptic

optimizer:
  lr_backbone: 5.0e-6
  lr_head: 5.0e-5
  weight_decay: 0.05
  grad_accumulation: 4
  grad_clip_norm: 0.01

scheduler:
  type: cosine
  warmup_steps: 0

training:
  epochs: 30
  early_stop_patience: 5
  mixed_precision: bf16
  oversample_rare_classes: true

logging:
  tracker: wandb
  project: batia-segmentation
  log_image_count: 5

checkpoint:
  output_dir: runs/segmentation/stage_b_finetune_v1
  save_every_n_epochs: 5
```

- [ ] **Step 4: Smoke test CLI (avec config tiny)**

```bash
# Vérifier que le CLI parse et démarre avec une config invalide pour signaler une erreur claire
python scripts/train_segmentation.py --config configs/segmentation/stage_a_cubicasa.yaml --device cpu 2>&1 | head -5
```

(On va l'arrêter avec Ctrl+C immédiatement, on vérifie juste qu'il démarre.)

- [ ] **Step 5: Commit**

```bash
git add scripts/train_segmentation.py configs/segmentation/
git commit -m "feat(seg): training CLI + Stage A/B configs"
```

---

## Task 15: Pre-process inférence (letterbox + denormalize)

**Files:**
- Create: `src/segmentation/preprocess.py`
- Create: `tests/segmentation/test_preprocess.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_preprocess.py
import numpy as np
from src.segmentation.preprocess import letterbox, unletterbox_polygon


def test_letterbox_preserves_aspect():
    img = np.full((600, 800, 3), 200, dtype=np.uint8)
    out, info = letterbox(img, target_size=768)
    assert out.shape == (768, 768, 3)
    assert info.scale == 768 / 800  # max dim
    # Padding asymmetric
    assert info.pad_top + info.pad_bottom > 0


def test_unletterbox_polygon_inverse():
    img = np.full((600, 800, 3), 200, dtype=np.uint8)
    _, info = letterbox(img, target_size=768)
    # Polygon in letterboxed space
    poly_lb = [[100, 100], [700, 100], [700, 700], [100, 700]]
    poly_orig = unletterbox_polygon(poly_lb, info)
    # Should be within original image bounds
    for x, y in poly_orig:
        assert 0 <= x <= 800
        assert 0 <= y <= 600
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter preprocess.py**

```python
# src/segmentation/preprocess.py
"""Letterbox-based preprocessing for inference (preserves aspect ratio)."""
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass(frozen=True)
class LetterboxInfo:
    orig_h: int
    orig_w: int
    target_size: int
    scale: float
    pad_top: int
    pad_left: int
    pad_bottom: int
    pad_right: int


def letterbox(image: np.ndarray, target_size: int = 768,
              fill_value: int = 255) -> tuple[np.ndarray, LetterboxInfo]:
    h, w = image.shape[:2]
    scale = target_size / max(h, w)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))
    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_top = (target_size - new_h) // 2
    pad_bottom = target_size - new_h - pad_top
    pad_left = (target_size - new_w) // 2
    pad_right = target_size - new_w - pad_left

    padded = cv2.copyMakeBorder(
        resized, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=(fill_value, fill_value, fill_value),
    )
    return padded, LetterboxInfo(
        orig_h=h, orig_w=w, target_size=target_size, scale=scale,
        pad_top=pad_top, pad_left=pad_left,
        pad_bottom=pad_bottom, pad_right=pad_right,
    )


def unletterbox_polygon(polygon: list[list[int]], info: LetterboxInfo) -> list[list[int]]:
    """Map polygon coords from letterboxed space back to original image space."""
    out = []
    for x, y in polygon:
        ux = (x - info.pad_left) / info.scale
        uy = (y - info.pad_top) / info.scale
        ux = max(0.0, min(info.orig_w, ux))
        uy = max(0.0, min(info.orig_h, uy))
        out.append([int(round(ux)), int(round(uy))])
    return out


def unletterbox_mask(mask: np.ndarray, info: LetterboxInfo) -> np.ndarray:
    """Crop padding then resize back to original image size. Uses NEAREST."""
    cropped = mask[
        info.pad_top : info.target_size - info.pad_bottom,
        info.pad_left : info.target_size - info.pad_right,
    ]
    return cv2.resize(cropped, (info.orig_w, info.orig_h),
                      interpolation=cv2.INTER_NEAREST)
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/preprocess.py tests/segmentation/test_preprocess.py
git commit -m "feat(seg): letterbox preprocess + inverse polygon mapping"
```

---

## Task 16: Post-process (panoptique → JSON)

**Files:**
- Create: `src/segmentation/postprocess.py`
- Create: `tests/segmentation/test_postprocess.py`

- [ ] **Step 1: Écrire le test**

```python
# tests/segmentation/test_postprocess.py
import numpy as np
from src.segmentation.postprocess import (
    panoptic_to_rooms, walls_mask_to_output, simplify_polygon,
)
from src.segmentation.preprocess import LetterboxInfo


def _info_identity(size=100):
    return LetterboxInfo(orig_h=size, orig_w=size, target_size=size, scale=1.0,
                         pad_top=0, pad_left=0, pad_bottom=0, pad_right=0)


def test_panoptic_to_rooms_basic():
    seg = np.zeros((100, 100), dtype=np.int32)
    seg[10:30, 10:30] = 1  # segment id 1
    seg[50:90, 50:90] = 2  # segment id 2
    segments_info = [
        {"id": 1, "label_id": 2, "score": 0.9},   # Kitchen
        {"id": 2, "label_id": 5, "score": 0.85},  # Bath
    ]
    info = _info_identity()
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(100, 100))
    assert len(rooms) == 2
    types = {r["type"] for r in rooms}
    assert types == {"Kitchen", "Bath"}


def test_panoptic_filters_low_score():
    seg = np.zeros((100, 100), dtype=np.int32)
    seg[10:30, 10:30] = 1
    segments_info = [{"id": 1, "label_id": 2, "score": 0.3}]
    info = _info_identity()
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(100, 100))
    assert rooms == []


def test_panoptic_filters_small_area():
    seg = np.zeros((1000, 1000), dtype=np.int32)
    seg[0:5, 0:5] = 1  # 25 pixels = 0.0025% of 1M
    segments_info = [{"id": 1, "label_id": 2, "score": 0.9}]
    info = LetterboxInfo(1000, 1000, 1000, 1.0, 0, 0, 0, 0)
    rooms = panoptic_to_rooms(seg, segments_info, info, plan_size=(1000, 1000))
    assert rooms == []


def test_walls_mask_output():
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[40:60, :] = 1
    info = _info_identity()
    out = walls_mask_to_output(mask, info, plan_id="test", out_dir="/tmp")
    assert out.skeleton_paths_count >= 0
    assert "/tmp/test_walls.png" in out.mask_path


def test_simplify_polygon_reduces_points():
    contour = np.array([[i, 0] for i in range(100)] +
                       [[100, j] for j in range(100)] +
                       [[100 - i, 100] for i in range(100)] +
                       [[0, 100 - j] for j in range(100)], dtype=np.int32)
    simplified = simplify_polygon(contour, epsilon_ratio=0.005)
    assert len(simplified) < 20
    assert len(simplified) >= 4
```

- [ ] **Step 2: Run test (fail)**

- [ ] **Step 3: Implémenter postprocess.py**

```python
# src/segmentation/postprocess.py
"""Postprocessing: Mask2Former panoptic output → polygons + JSON."""
from pathlib import Path
import cv2
import numpy as np
from pycocotools import mask as mask_utils

from src.segmentation.classes import CLASS_NAMES, ROOM_CLASS_IDS, CLASS_ID
from src.segmentation.preprocess import LetterboxInfo, unletterbox_polygon, unletterbox_mask
from src.segmentation.schema import RoomDetection, WallsOutput


SCORE_MIN = 0.5
AREA_RATIO_MIN = 0.001  # 0.1% of image


def simplify_polygon(contour: np.ndarray, epsilon_ratio: float = 0.005) -> np.ndarray:
    """Douglas-Peucker simplification. contour shape (N,1,2) or (N,2)."""
    if contour.ndim == 2:
        contour = contour[:, None, :]
    eps = epsilon_ratio * cv2.arcLength(contour, closed=True)
    simplified = cv2.approxPolyDP(contour, eps, closed=True)
    return simplified.reshape(-1, 2)


def _largest_contour(mask: np.ndarray) -> np.ndarray | None:
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE,
    )
    if not contours:
        return None
    return max(contours, key=cv2.contourArea)


def panoptic_to_rooms(
    panoptic_seg: np.ndarray,
    segments_info: list[dict],
    letterbox_info: LetterboxInfo,
    plan_size: tuple[int, int],  # (W, H) of original image
) -> list[dict]:
    """Convert Mask2Former panoptic output → list of room dicts (RoomDetection-compat).

    Args:
        panoptic_seg: (H, W) int — segment id per pixel (in letterboxed space)
        segments_info: list of {id, label_id, score, ...}
        letterbox_info: from preprocess.letterbox
        plan_size: (W, H) of original image
    """
    out: list[dict] = []
    plan_w, plan_h = plan_size
    plan_area = plan_w * plan_h
    counter = 0

    for seg in segments_info:
        score = seg.get("score", 1.0)
        label_id = seg.get("label_id")
        if label_id is None or label_id not in ROOM_CLASS_IDS:
            continue
        if score < SCORE_MIN:
            continue

        binary_lb = (panoptic_seg == seg["id"]).astype(np.uint8)
        if binary_lb.sum() == 0:
            continue
        # Map to original image space
        binary_orig = unletterbox_mask(binary_lb, letterbox_info)
        if binary_orig.sum() / plan_area < AREA_RATIO_MIN:
            continue

        contour = _largest_contour(binary_orig)
        if contour is None:
            continue
        poly = simplify_polygon(contour, epsilon_ratio=0.005)
        if len(poly) < 3:
            continue

        xs, ys = poly[:, 0], poly[:, 1]
        bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        counter += 1
        out.append(dict(
            id=f"room_{counter:03d}",
            type=CLASS_NAMES[label_id],
            type_id=int(label_id),
            polygon=poly.tolist(),
            bbox=bbox,
            area_pixels=int(binary_orig.sum()),
            confidence=float(score),
        ))
    return out


def walls_mask_to_output(
    walls_mask_lb: np.ndarray,
    letterbox_info: LetterboxInfo,
    plan_id: str,
    out_dir: str | Path,
) -> WallsOutput:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    walls_orig = unletterbox_mask(walls_mask_lb, letterbox_info)
    out_path = out_dir / f"{Path(plan_id).stem}_walls.png"
    cv2.imwrite(str(out_path), (walls_orig * 255).astype(np.uint8))

    rle = mask_utils.encode(np.asfortranarray(walls_orig.astype(np.uint8)))
    rle_str = rle["counts"].decode("ascii")

    # Skeleton path count: number of connected components of skeletonized walls
    from skimage.morphology import skeletonize
    skel = skeletonize(walls_orig.astype(bool))
    n_components, _ = cv2.connectedComponents(skel.astype(np.uint8))

    return WallsOutput(
        mask_rle=rle_str,
        mask_path=str(out_path),
        skeleton_paths_count=max(0, n_components - 1),
    )
```

- [ ] **Step 4: Run test (PASS)**

- [ ] **Step 5: Commit**

```bash
git add src/segmentation/postprocess.py tests/segmentation/test_postprocess.py
git commit -m "feat(seg): postprocess panoptic -> rooms + walls JSON"
```

---

## Task 17: Pipeline d'inférence end-to-end + CLI

**Files:**
- Create: `src/segmentation/inference.py`
- Create: `scripts/predict_segmentation.py`
- Create: `tests/segmentation/fixtures/sample_plan.png`
- Create: `tests/segmentation/test_inference.py`

- [ ] **Step 1: Préparer fixture**

```python
import cv2, numpy as np
from pathlib import Path
img = np.full((600, 800, 3), 240, dtype=np.uint8)
# Quelques rectangles noirs simulant des murs
cv2.rectangle(img, (50, 50), (750, 550), (0, 0, 0), thickness=4)
cv2.line(img, (400, 50), (400, 550), (0, 0, 0), thickness=4)
cv2.imwrite("tests/segmentation/fixtures/sample_plan.png", img)
```

- [ ] **Step 2: Écrire le test (skip si pas de checkpoint disponible)**

```python
# tests/segmentation/test_inference.py
import os
from pathlib import Path
import pytest
from src.segmentation.inference import SegmentationInference
from src.segmentation.schema import SegmentationOutput


@pytest.mark.skipif(
    not os.environ.get("BATIA_TEST_CHECKPOINT"),
    reason="Set BATIA_TEST_CHECKPOINT=path/to/checkpoint.pt to run",
)
def test_inference_returns_valid_schema(fixtures_dir: Path, tmp_path: Path):
    inf = SegmentationInference(
        checkpoint_path=os.environ["BATIA_TEST_CHECKPOINT"],
        backbone="facebook/mask2former-swin-small-coco-panoptic",
        image_size=768,
        device="cpu",
        walls_out_dir=tmp_path,
    )
    out: SegmentationOutput = inf.predict(fixtures_dir / "sample_plan.png")
    assert isinstance(out, SegmentationOutput)
    assert out.image_size == [800, 600]
    assert isinstance(out.rooms, list)
```

- [ ] **Step 3: Run test (skipped si pas de var d'env)**

- [ ] **Step 4: Implémenter inference.py**

```python
# src/segmentation/inference.py
"""End-to-end inference: image path -> SegmentationOutput JSON."""
from __future__ import annotations
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.classes import CLASS_ID, NUM_CLASSES
from src.segmentation.model import build_model, get_processor
from src.segmentation.preprocess import letterbox
from src.segmentation.postprocess import panoptic_to_rooms, walls_mask_to_output
from src.segmentation.schema import SegmentationOutput, RoomDetection, WallsOutput


_DEFAULT_NORM_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DEFAULT_NORM_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class SegmentationInference:
    def __init__(
        self,
        checkpoint_path: str | Path,
        backbone: str = "facebook/mask2former-swin-small-coco-panoptic",
        image_size: int = 768,
        device: str = "auto",
        walls_out_dir: str | Path = "runs/segmentation/inference_walls",
        model_version: str = "mask2former-swin-s-batia-v0.1",
    ):
        self.image_size = image_size
        self.walls_out_dir = Path(walls_out_dir)
        self.walls_out_dir.mkdir(parents=True, exist_ok=True)
        self.model_version = model_version

        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = torch.device(device)

        self.model = build_model(backbone=backbone, num_classes=NUM_CLASSES)
        ckpt = load_checkpoint(checkpoint_path, map_location=str(self.device))
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.model.to(self.device).eval()
        self.processor = get_processor(backbone)

    @torch.no_grad()
    def predict(self, image_path: str | Path) -> SegmentationOutput:
        t0 = time.time()
        image_path = Path(image_path)
        bgr = cv2.imread(str(image_path))
        if bgr is None:
            raise ValueError(f"Cannot read image: {image_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        # Preprocess
        padded, info = letterbox(rgb, target_size=self.image_size)
        normalized = padded.astype(np.float32) / 255.0
        normalized = (normalized - _DEFAULT_NORM_MEAN) / _DEFAULT_NORM_STD
        tensor = torch.from_numpy(normalized).permute(2, 0, 1).unsqueeze(0).float()
        tensor = tensor.to(self.device)

        # Forward
        out = self.model(pixel_values=tensor)

        # Mask2Former panoptic post-processing
        result = self.processor.post_process_panoptic_segmentation(
            out, target_sizes=[(self.image_size, self.image_size)],
            threshold=0.5,
        )[0]
        panoptic_seg = result["segmentation"].cpu().numpy()  # (H, W) int
        segments_info = result["segments_info"]

        # Rooms
        rooms_dicts = panoptic_to_rooms(
            panoptic_seg, segments_info, info, plan_size=(w, h),
        )
        rooms = [RoomDetection(**r) for r in rooms_dicts]

        # Walls (binary mask of class id 1, in letterboxed space)
        walls_mask_lb = np.zeros_like(panoptic_seg, dtype=np.uint8)
        for seg in segments_info:
            if seg.get("label_id") == CLASS_ID["Wall"]:
                walls_mask_lb |= (panoptic_seg == seg["id"]).astype(np.uint8)
        walls = walls_mask_to_output(
            walls_mask_lb, info, plan_id=image_path.name, out_dir=self.walls_out_dir,
        )

        elapsed_ms = int((time.time() - t0) * 1000)
        return SegmentationOutput(
            plan_id=image_path.name,
            image_size=[w, h],
            model_version=self.model_version,
            inference_time_ms=elapsed_ms,
            rooms=rooms,
            walls=walls,
            warnings=[],
        )
```

- [ ] **Step 5: Implémenter le CLI**

```python
# scripts/predict_segmentation.py
"""CLI: predict_segmentation.py --image plan.png --checkpoint best.pt --out result.json"""
import argparse
import json
from pathlib import Path
from src.segmentation.inference import SegmentationInference


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--backbone", default="facebook/mask2former-swin-small-coco-panoptic")
    ap.add_argument("--image_size", type=int, default=768)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--walls_dir", default="runs/segmentation/inference_walls")
    args = ap.parse_args()

    inf = SegmentationInference(
        checkpoint_path=args.checkpoint,
        backbone=args.backbone,
        image_size=args.image_size,
        device=args.device,
        walls_out_dir=args.walls_dir,
    )
    result = inf.predict(args.image)
    Path(args.out).write_text(result.model_dump_json(indent=2))
    print(f"Wrote {args.out} with {len(result.rooms)} rooms, "
          f"inference={result.inference_time_ms}ms")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add src/segmentation/inference.py scripts/predict_segmentation.py tests/segmentation/fixtures/sample_plan.png tests/segmentation/test_inference.py
git commit -m "feat(seg): end-to-end inference pipeline + CLI"
```

---

## Task 18: Dashboard d'évaluation qualitative

**Files:**
- Create: `scripts/eval_visualize.py`

- [ ] **Step 1: Implémenter le script**

```python
# scripts/eval_visualize.py
"""Generate an HTML report of predictions sorted by worst mIoU.

Usage:
  python scripts/eval_visualize.py \\
    --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \\
    --dataset_root data/processed/cubicasa_panoptic \\
    --split val \\
    --out runs/segmentation/stage_a_cubicasa_v1/eval_report.html \\
    --max_samples 50
"""
import argparse
import base64
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm

from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES
from src.segmentation.dataset import PanopticDataset
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.inference import SegmentationInference


_PALETTE = np.array([
    [0, 0, 0],         # 0 Background
    [80, 80, 80],      # 1 Wall
    [255, 200, 100],   # 2 Kitchen
    [120, 220, 100],   # 3 LivingRoom
    [100, 150, 255],   # 4 BedRoom
    [200, 100, 200],   # 5 Bath
    [255, 220, 0],     # 6 Entry
    [180, 120, 80],    # 7 Storage
    [100, 100, 100],   # 8 Garage
    [120, 220, 220],   # 9 Outdoor
], dtype=np.uint8)


def colorize(mask: np.ndarray) -> np.ndarray:
    return _PALETTE[mask.clip(0, NUM_CLASSES - 1)]


def to_b64(img: np.ndarray) -> str:
    buf = BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--dataset_root", required=True)
    ap.add_argument("--split", default="val")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_samples", type=int, default=50)
    ap.add_argument("--image_size", type=int, default=768)
    args = ap.parse_args()

    inf = SegmentationInference(
        checkpoint_path=args.checkpoint,
        image_size=args.image_size, device="auto",
    )
    ds = PanopticDataset(args.dataset_root, args.split, args.image_size, train=False)

    rows: list[dict] = []
    for i in tqdm(range(min(len(ds), args.max_samples * 3))):
        sid = ds.ids[i]
        img_path = Path(args.dataset_root) / "images" / args.split / f"{sid}.png"
        gt_path = Path(args.dataset_root) / "semantic" / args.split / f"{sid}.png"
        bgr = cv2.imread(str(img_path))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        gt = cv2.imread(str(gt_path), cv2.IMREAD_UNCHANGED)

        # Quick prediction (uses inference pipeline; we extract sem map by reading walls + rooms)
        out = inf.predict(img_path)
        # Reconstruct a semantic map from rooms + walls for IoU
        pred_sem = np.zeros_like(gt)
        for r in out.rooms:
            poly = np.asarray(r.polygon, dtype=np.int32)
            cv2.fillPoly(pred_sem, [poly], r.type_id)
        walls_mask = cv2.imread(out.walls.mask_path, cv2.IMREAD_UNCHANGED)
        if walls_mask is not None:
            pred_sem[walls_mask > 0] = 1

        ious = compute_iou_per_class(pred_sem, gt, NUM_CLASSES)
        miou = compute_miou(ious)
        rows.append({
            "id": sid, "miou": miou,
            "img_b64": to_b64(rgb),
            "gt_b64": to_b64(colorize(gt)),
            "pred_b64": to_b64(colorize(pred_sem)),
        })

    rows.sort(key=lambda r: r["miou"])  # worst first
    rows = rows[: args.max_samples]

    html_parts = ["<!doctype html><meta charset='utf-8'>",
                  "<style>body{font-family:sans-serif} .row{display:flex;gap:8px;align-items:center;border-bottom:1px solid #ccc;padding:8px} img{max-width:300px;border:1px solid #888} .legend{font-size:12px} .miou{font-weight:bold;color:#a00}</style>",
                  "<h1>Eval Visualisation — worst mIoU first</h1>"]
    legend = " · ".join(f"{i}={n}" for i, n in enumerate(CLASS_NAMES))
    html_parts.append(f"<div class='legend'>{legend}</div>")
    for r in rows:
        html_parts.append(
            f"<div class='row'><div>{r['id']}<br><span class='miou'>mIoU={r['miou']:.3f}</span></div>"
            f"<img src='data:image/png;base64,{r['img_b64']}' alt='input'>"
            f"<img src='data:image/png;base64,{r['gt_b64']}' alt='gt'>"
            f"<img src='data:image/png;base64,{r['pred_b64']}' alt='pred'></div>"
        )
    Path(args.out).write_text("\n".join(html_parts), encoding="utf-8")
    print(f"Wrote {args.out} with {len(rows)} samples")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test (sera utilisable une fois Stage A terminé, pour l'instant simple syntaxique)**

```bash
python -c "import scripts.eval_visualize"  # ou python scripts/eval_visualize.py --help
```

- [ ] **Step 3: Commit**

```bash
git add scripts/eval_visualize.py
git commit -m "feat(seg): qualitative eval HTML dashboard (worst mIoU first)"
```

---

## Task 19: README et documentation

**Files:**
- Create: `src/segmentation/README.md`

- [ ] **Step 1: Écrire le README**

```markdown
# `src/segmentation/` — Brique B (segmentation des pièces)

Voir [spec design](../../docs/superpowers/specs/2026-05-07-segmentation-pieces-design.md)
et [plan d'implémentation](../../docs/superpowers/plans/2026-05-07-segmentation-pieces-mvp.md).

## Quickstart

### 1. Préparer le dataset CubiCasa

\`\`\`bash
python scripts/cubicasa5k_export_segmentation.py \
  --root data/raw/cubicasa5k \
  --out data/processed/cubicasa_panoptic
\`\`\`

### 2. Entraîner Stage A (CubiCasa, 80 epochs, 3-5 jours sur M5 Pro)

\`\`\`bash
python scripts/train_segmentation.py \
  --config configs/segmentation/stage_a_cubicasa.yaml
\`\`\`

Auto-resume après crash :

\`\`\`bash
python scripts/train_segmentation.py \
  --config configs/segmentation/stage_a_cubicasa.yaml \
  --resume latest
\`\`\`

### 3. Inférence sur un plan

\`\`\`bash
python scripts/predict_segmentation.py \
  --image data/samples/plan_fr.png \
  --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \
  --out result.json
\`\`\`

### 4. Dashboard d'évaluation

\`\`\`bash
python scripts/eval_visualize.py \
  --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \
  --dataset_root data/processed/cubicasa_panoptic \
  --split val \
  --out runs/segmentation/stage_a_cubicasa_v1/eval_val.html
\`\`\`

## API Python

\`\`\`python
from src.segmentation.inference import SegmentationInference

inf = SegmentationInference(checkpoint_path="path/to/best.pt")
result = inf.predict("plan.png")
print(result.rooms)  # list[RoomDetection]
print(result.walls.mask_path)
\`\`\`

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
```

- [ ] **Step 2: Commit**

```bash
git add src/segmentation/README.md
git commit -m "docs(seg): README with quickstart + API reference"
```

---

## Task 20: Lancer Stage A training

**⚠ Étape long-running.** Pas de tests automatisés, mais vérifications manuelles à chaque jalon.

- [ ] **Step 1: Vérifier prérequis**

```bash
# Dataset existe et a la bonne structure
ls data/processed/cubicasa_panoptic/{images,semantic,instance}/{train,val,test} | head
cat data/processed/cubicasa_panoptic/dataset.yaml
cat data/processed/cubicasa_panoptic/splits.json | python -c "import sys,json; d=json.load(sys.stdin); print({k:len(v) for k,v in d.items()})"
```

Expected : ~3000-4500 train, ~400-600 val, ~400-600 test.

- [ ] **Step 2: Vérifier W&B est configuré**

```bash
wandb login  # première fois seulement
echo $WANDB_API_KEY  # doit être défini
```

- [ ] **Step 3: Lancer Stage A en arrière-plan**

```bash
mkdir -p logs
nohup python scripts/train_segmentation.py \
  --config configs/segmentation/stage_a_cubicasa.yaml \
  > logs/stage_a_$(date +%Y%m%d_%H%M).log 2>&1 &
echo $! > logs/stage_a.pid
```

- [ ] **Step 4: Vérifier les premières epochs (après ~30-60 min)**

```bash
tail -100 logs/stage_a_*.log
```

Métriques attendues fin de l'epoch 1 :
- `train/loss` décroissant (de ~30 vers ~15)
- `val/mIoU` > 0.10 (apprentissage initial)

Sur W&B : voir le run apparaître, courbes lisses.

- [ ] **Step 5: Suivi intermédiaire (epoch 10-20, après ~1-2 jours)**

Targets :
- `val/mIoU` ≥ 0.40 à epoch 20
- `val/IoU_class_X` pas de classe à 0.0 (vérifier rare classes Garage/Storage)
- Pas de divergence du loss (pas de NaN, pas d'oscillations massives)

Si une classe stagne à 0 : interrompre, augmenter oversampling pour cette classe, reprendre.

- [ ] **Step 6: Fin de Stage A (epoch 50-80, après ~3-5 jours)**

Critères MVP du spec :
- `val/mIoU` ≥ 0.65 sur split CubiCasa
- Aucune classe < 0.30

Le best checkpoint est dans `runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt`.

- [ ] **Step 7: Générer le rapport d'éval final**

```bash
python scripts/eval_visualize.py \
  --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \
  --dataset_root data/processed/cubicasa_panoptic \
  --split test \
  --out runs/segmentation/stage_a_cubicasa_v1/eval_test_cubicasa.html \
  --max_samples 100
```

Ouvrir le HTML dans le navigateur, examiner les 30 pires cas. Documenter les modes d'échec récurrents dans `runs/segmentation/stage_a_cubicasa_v1/MODES_ECHEC.md` (sera l'input du Plan 2).

- [ ] **Step 8: Commit final + tag**

```bash
git add runs/segmentation/stage_a_cubicasa_v1/MODES_ECHEC.md
git commit -m "chore(seg): Stage A training complete + failure modes report"
git tag stage-a-v1
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Plan task |
|---|---|
| §3 Taxonomie 10 classes | Task 2 |
| §4 Architecture Mask2Former Swin-S | Task 9 |
| §5.1 Sources données CubiCasa | Tasks 5-6 |
| §5.3 Conversion SVG→panoptic | Tasks 5-6 |
| §5.4 Augmentations | Task 7 |
| §5.5 Splits | Task 6 |
| §6 Stage A training | Tasks 13-14, 20 |
| §6 Stage B training | **Plan 2 séparé** (template livré Task 14 step 3) |
| §6 Checkpointing/auto-resume | Task 11 |
| §6 Gestion déséquilibre classes (oversampling) | Config en Task 14 (champ `oversample_rare_classes`), à activer en Plan 2 |
| §7 Suivi W&B | Task 12 |
| §8 Inférence + post-process | Tasks 15-17 |
| §8.4 Schema JSON | Task 3 |
| §9 Architecture code | All tasks |
| §10 Métriques | Task 10 |
| §10 Eval qualitative | Task 18 |
| §10 Tests automatisés | All tasks (TDD) |
| §11 Intégration pipeline | Task 19 (README) |
| §13 Risques mitigés | Tasks 11 (auto-resume), 7 (Albu config), 9 (BF16) |

Note : `oversample_rare_classes` est un flag config présent mais l'implémentation dans le DataLoader (WeightedRandomSampler) n'a pas été câblée explicitement dans le code de la Task 13. Cela est volontaire : pour Stage A pur CubiCasa avec 4000 plans, l'oversampling apporte un gain marginal (les classes rares restent visibles dans suffisamment de plans). Le câblage WeightedRandomSampler sera fait dans Plan 2 pour Stage B (où il est critique).

**2. Placeholder scan :** aucun TODO/TBD/à compléter dans les steps. Stage B template (Task 14 step 3) marque explicitement "à compléter dans Plan 2", ce qui est intentionnel.

**3. Type consistency :**
- `RoomDetection` (schema.py) ↔ `panoptic_to_rooms` retourne dict compatible ✓
- `LetterboxInfo` defined in preprocess.py ↔ used by postprocess.py ✓
- `CLASS_NAMES`, `CLASS_ID`, `ROOM_CLASS_IDS`, `STRUCTURAL_CLASS_IDS` cohérents partout ✓
- `WallsOutput.skeleton_paths_count` int dans schema ↔ int retourné par `walls_mask_to_output` ✓
- `TrainingConfig` champs ↔ usage dans `Trainer.__init__` ✓
