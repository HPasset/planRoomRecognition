"""Convert CVAT COCO 1.0 export → YOLO detection dataset (Brique A).

Reads CVAT export (bbox mode) + original FR plans directory, then writes
the ultralytics-compatible dataset structure:

    <out>/
      images/{train,val,test}/<plan>.png         (symlinks to plans_dir)
      labels/{train,val,test}/<plan>.txt         YOLO format: <cls> <cx> <cy> <w> <h>
      dataset.yaml

YOLO format reminder:
  - One .txt file per image (same name, .txt extension)
  - One line per bbox: class_id x_center y_center width height
  - All coords NORMALIZED to [0, 1] (divided by image dims)
  - class_id is 0-indexed (0..N-1)

Splits: 70 train / 15 val / 15 test on 110 plans → ~77/16/17.

Usage:
    python scripts/cvat_to_yolo.py \\
        --coco_json data/processed/cvat_export/brique_a_v1/annotations/instances_Train.json \\
        --plans_dir data/raw/plans_fr \\
        --out data/processed/datasets/brique_a
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
from tqdm import tqdm


# Canonical class order — same as in predict_yolo_for_annotation.py.
# YOLO class_id = index in this list.
BATIA_CLASSES = [
    "Bathtub",          # 0
    "Shower",           # 1
    "WashBasin",        # 2
    "Toilet",           # 3
    "KitchenSink",      # 4
    "Cooktop",          # 5
    "Refrigerator",     # 6
    "WashingMachine",   # 7
    "Bed",              # 8  — mobilier ambiance pour placement prises chevet
]
# Note : "Dishwasher" droppé (0 annotation manuelle). Si présent dans le CVAT
# export, sera silencieusement ignoré via _build_cat_id_mapping (label inconnu
# pour ce modèle → warning + skip).
NAME_TO_YOLO_CLS = {n: i for i, n in enumerate(BATIA_CLASSES)}


def _build_cat_id_mapping(coco_categories: list[dict]) -> dict[int, int]:
    """Map CVAT category_id → our YOLO class_id (0-indexed, BY NAME)."""
    mapping: dict[int, int] = {}
    unknown: list[str] = []
    for c in coco_categories:
        name = c["name"]
        cvat_id = c["id"]
        if name in NAME_TO_YOLO_CLS:
            mapping[cvat_id] = NAME_TO_YOLO_CLS[name]
        else:
            unknown.append(name)
    if unknown:
        print(f"⚠ Unknown labels in CVAT export (will be ignored): {unknown}")
    return mapping


def _bbox_coco_to_yolo(
    bbox: list[float], img_w: int, img_h: int,
) -> tuple[float, float, float, float]:
    """COCO bbox [x, y, w, h] (top-left + dims, absolute px) →
       YOLO bbox [x_center, y_center, w, h] (center + dims, normalized 0-1)."""
    x, y, w, h = bbox
    cx = (x + w / 2.0) / img_w
    cy = (y + h / 2.0) / img_h
    nw = w / img_w
    nh = h / img_h
    # Clamp to [0, 1] in case of slight overflow
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    nw = max(0.0, min(1.0, nw))
    nh = max(0.0, min(1.0, nh))
    return cx, cy, nw, nh


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco_json", required=True,
                    help="CVAT export COCO 1.0 JSON path (bbox mode)")
    ap.add_argument("--plans_dir", required=True,
                    help="Directory with original FR plan images")
    ap.add_argument("--out", required=True,
                    help="Output directory for YOLO dataset")
    ap.add_argument("--train_ratio", type=float, default=0.70,
                    help="Fraction of plans for training (default 0.70)")
    ap.add_argument("--val_ratio", type=float, default=0.15,
                    help="Fraction for validation (default 0.15)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    coco_path = Path(args.coco_json)
    plans_dir = Path(args.plans_dir).resolve()
    out = Path(args.out).resolve()

    if not coco_path.is_file():
        raise SystemExit(f"COCO json not found: {coco_path}")
    if not plans_dir.is_dir():
        raise SystemExit(f"plans_dir not found: {plans_dir}")

    coco = json.loads(coco_path.read_text())
    cat_mapping = _build_cat_id_mapping(coco["categories"])

    print("Category mapping (CVAT id → YOLO class):")
    for cvat_id, yolo_cls in sorted(cat_mapping.items(), key=lambda kv: kv[1]):
        print(f"  CVAT {cvat_id:>2} → YOLO {yolo_cls} ({BATIA_CLASSES[yolo_cls]})")

    # Group annotations by image_id
    anns_by_image: dict[int, list[dict]] = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    # Create output dirs
    for split in ("train", "val", "test"):
        for sub in ("images", "labels"):
            (out / sub / split).mkdir(parents=True, exist_ok=True)

    # Deterministic split
    images = sorted(coco["images"], key=lambda i: i["id"])
    rng = random.Random(args.seed)
    rng.shuffle(images)

    n = len(images)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    train_imgs = images[:n_train]
    val_imgs = images[n_train:n_train + n_val]
    test_imgs = images[n_train + n_val:]
    splits_map = {"train": train_imgs, "val": val_imgs, "test": test_imgs}

    print(f"\nSplits: train={len(train_imgs)} val={len(val_imgs)} "
          f"test={len(test_imgs)}")

    total_counts = {n: 0 for n in BATIA_CLASSES}
    skipped: list[tuple[str, str]] = []

    for split, imgs in splits_map.items():
        for img_info in tqdm(imgs, desc=f"export {split}"):
            file_name = img_info["file_name"]
            sample_id = Path(file_name).stem

            src_path = plans_dir / file_name
            if not src_path.exists():
                skipped.append((file_name, "src not found"))
                continue

            # Read actual image dims (CVAT sometimes stores logical dims)
            real_img = cv2.imread(str(src_path))
            if real_img is None:
                skipped.append((file_name, "unreadable"))
                continue
            real_h, real_w = real_img.shape[:2]

            # Symlink image (no copy)
            ext = Path(file_name).suffix
            img_dst = out / "images" / split / f"{sample_id}{ext}"
            if img_dst.is_symlink() or img_dst.exists():
                img_dst.unlink()
            img_dst.symlink_to(src_path)

            # Write YOLO label file
            label_path = out / "labels" / split / f"{sample_id}.txt"
            lines: list[str] = []
            for ann in anns_by_image.get(img_info["id"], []):
                cvat_cat_id = ann["category_id"]
                if cvat_cat_id not in cat_mapping:
                    continue
                yolo_cls = cat_mapping[cvat_cat_id]
                cx, cy, nw, nh = _bbox_coco_to_yolo(
                    ann["bbox"], real_w, real_h,
                )
                if nw < 0.001 or nh < 0.001:
                    continue  # degenerate bbox
                lines.append(f"{yolo_cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                total_counts[BATIA_CLASSES[yolo_cls]] += 1

            label_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    # dataset.yaml (ultralytics format)
    yaml_lines = [
        f"path: {out.as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        f"nc: {len(BATIA_CLASSES)}",
        "names:",
    ]
    for i, name in enumerate(BATIA_CLASSES):
        yaml_lines.append(f"  {i}: {name}")
    (out / "dataset.yaml").write_text("\n".join(yaml_lines) + "\n")

    print(f"\n✓ Exported {n} plans to {out}")
    print(f"\nAnnotations per class:")
    for name, count in total_counts.items():
        marker = " ⚠ LOW" if count < 30 else ""
        print(f"  {name:>15s}: {count:>4}{marker}")

    total = sum(total_counts.values())
    print(f"\n  Total annotations: {total}")
    if total > 0:
        print(f"  Avg per plan: {total / n:.1f}")

    if skipped:
        print(f"\n⚠ {len(skipped)} images skipped:")
        for name, reason in skipped[:10]:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()
