"""Convert CVAT COCO 1.0 export → panoptic dataset for Stage B training.

Reads an annotated CVAT export + the original FR plans directory, then writes
out the same panoptic structure as scripts/cubicasa5k_export_segmentation.py:

    <out>/
      images/{train,val,test}/<plan>.png
      semantic/{train,val,test}/<plan>.png   uint8, class_id per pixel
      instance/{train,val,test}/<plan>.png   uint16, instance id per pixel
      splits.json
      dataset.yaml

Usage:
    python scripts/cvat_to_panoptic.py \\
        --coco_json data/processed/cvat_export/batia_stage_b_v1/annotations/instances_Train.json \\
        --plans_dir data/raw/plans_fr \\
        --out data/processed/fr_panoptic

Default splits: 70 train / 15 val / 25 test (suited to ~110 plans).
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path

# Ensure project root on path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
import numpy as np
from tqdm import tqdm

from src.segmentation.classes import (
    CLASS_NAMES, CLASS_ID, NUM_CLASSES, ROOM_CLASS_IDS, STRUCTURAL_CLASS_IDS,
)


def _flat_polygon_to_points(flat: list[float]) -> np.ndarray:
    """Convert COCO flat segmentation [x1,y1,x2,y2,...] to (N,2) ndarray."""
    if len(flat) < 6:  # need at least 3 points (6 floats)
        return np.empty((0, 2))
    coords = np.asarray(flat, dtype=np.float64)
    if len(coords) % 2 != 0:
        coords = coords[:-1]
    return coords.reshape(-1, 2)


def _build_cat_id_mapping(coco_categories: list[dict]) -> dict[int, int]:
    """Map CVAT category_id -> our internal C2 class id (0-9 by name)."""
    mapping: dict[int, int] = {}
    unknown: list[str] = []
    for c in coco_categories:
        name = c["name"]
        cvat_id = c["id"]
        if name in CLASS_ID:
            mapping[cvat_id] = CLASS_ID[name]
        else:
            unknown.append(name)
    if unknown:
        print(f"⚠ Unknown labels in CVAT export (will be ignored): {unknown}")
    return mapping


def rasterize_image(
    img_info: dict,
    annotations: list[dict],
    cat_mapping: dict[int, int],
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Build semantic + instance masks from CVAT annotations for one image.

    Returns (semantic uint8 (H,W), instance uint16 (H,W), stats dict).
    """
    w = img_info["width"]
    h = img_info["height"]
    sem = np.zeros((h, w), dtype=np.uint8)
    inst = np.zeros((h, w), dtype=np.int32)

    next_inst_id = 1
    counts = {"rooms": 0, "walls": 0, "background": 0, "skipped_unknown": 0,
              "skipped_empty": 0}

    # Sort by area DESC so bigger polygons drawn first, smaller on top
    annotations = sorted(annotations, key=lambda a: -float(a.get("area", 0)))

    # Pass 1: rooms (instance-able, classes 2-9)
    for ann in annotations:
        cvat_cat_id = ann["category_id"]
        if cvat_cat_id not in cat_mapping:
            counts["skipped_unknown"] += 1
            continue
        cls = cat_mapping[cvat_cat_id]
        if cls not in ROOM_CLASS_IDS:
            continue  # walls/background handled below

        # Each polygon in segmentation = a separate region of THIS annotation
        # (rare for room polygons but handle robustly)
        any_drawn = False
        for poly_flat in ann.get("segmentation", []):
            pts = _flat_polygon_to_points(poly_flat)
            if pts.shape[0] < 3:
                continue
            pts_int = np.round(pts).astype(np.int32)
            cv2.fillPoly(sem, [pts_int], int(cls))
            cv2.fillPoly(inst, [pts_int], int(next_inst_id))
            any_drawn = True
        if any_drawn:
            counts["rooms"] += 1
            next_inst_id += 1
        else:
            counts["skipped_empty"] += 1

    # Pass 2: Wall (class 1) — overwrites room pixels, instance_id stays 0
    for ann in annotations:
        cvat_cat_id = ann["category_id"]
        if cvat_cat_id not in cat_mapping:
            continue
        cls = cat_mapping[cvat_cat_id]
        if cls != CLASS_ID["Wall"]:
            continue
        for poly_flat in ann.get("segmentation", []):
            pts = _flat_polygon_to_points(poly_flat)
            if pts.shape[0] < 3:
                continue
            pts_int = np.round(pts).astype(np.int32)
            cv2.fillPoly(sem, [pts_int], int(cls))
            cv2.fillPoly(inst, [pts_int], 0)
        counts["walls"] += 1

    # Pass 3: Background (class 0) — only if user explicitly annotated it
    # (we don't add it by default; remaining pixels stay as Background=0 anyway)
    for ann in annotations:
        cvat_cat_id = ann["category_id"]
        if cvat_cat_id not in cat_mapping:
            continue
        cls = cat_mapping[cvat_cat_id]
        if cls != CLASS_ID["Background"]:
            continue
        for poly_flat in ann.get("segmentation", []):
            pts = _flat_polygon_to_points(poly_flat)
            if pts.shape[0] < 3:
                continue
            pts_int = np.round(pts).astype(np.int32)
            cv2.fillPoly(sem, [pts_int], int(cls))
            cv2.fillPoly(inst, [pts_int], 0)
        counts["background"] += 1

    return sem, inst.astype(np.uint16), counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco_json", required=True,
                    help="CVAT export instances_Train.json path")
    ap.add_argument("--plans_dir", required=True,
                    help="Directory with original FR plan images")
    ap.add_argument("--out", required=True,
                    help="Output directory for panoptic dataset")
    ap.add_argument("--train_ratio", type=float, default=0.65,
                    help="Fraction of plans for training (default 0.65 → 70 plans on 110)")
    ap.add_argument("--val_ratio", type=float, default=0.14,
                    help="Fraction for validation (default 0.14 → 15 plans on 110)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--splits_json", default=None,
                    help="Reuse an existing splits.json (assign each plan to its "
                         "split BY NAME). Freezes the held-out test set across "
                         "re-exports — ignores --train_ratio/--val_ratio/--seed.")
    args = ap.parse_args()

    coco_path = Path(args.coco_json)
    plans_dir = Path(args.plans_dir)
    out = Path(args.out).resolve()

    if not coco_path.is_file():
        raise SystemExit(f"COCO json not found: {coco_path}")
    if not plans_dir.is_dir():
        raise SystemExit(f"plans_dir not found: {plans_dir}")

    coco = json.loads(coco_path.read_text())
    cat_mapping = _build_cat_id_mapping(coco["categories"])
    print(f"Category mapping (CVAT id → C2 class id):")
    for cvat_id, c2_id in sorted(cat_mapping.items()):
        print(f"  {cvat_id} ({coco['categories'][cvat_id-1]['name']:>12s}) → "
              f"{c2_id} ({CLASS_NAMES[c2_id]})")

    # Group annotations by image_id
    anns_by_image: dict[int, list[dict]] = {}
    for ann in coco["annotations"]:
        anns_by_image.setdefault(ann["image_id"], []).append(ann)

    # Create output dirs
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (out / sub / split).mkdir(parents=True, exist_ok=True)

    images = sorted(coco["images"], key=lambda i: i["id"])

    if args.splits_json:
        # Freeze split BY NAME from an existing splits.json (keeps the held-out
        # test set identical across re-exports → comparable metrics).
        ref = json.loads(Path(args.splits_json).read_text())
        stem_to_split = {stem: sp for sp, stems in ref.items() for stem in stems}
        splits_map = {"train": [], "val": [], "test": []}
        unassigned = []
        for img in images:
            sp = stem_to_split.get(Path(img["file_name"]).stem)
            if sp is None:
                unassigned.append(Path(img["file_name"]).stem)
            else:
                splits_map[sp].append(img)
        if unassigned:
            print(f"⚠ {len(unassigned)} plan(s) absent(s) de {args.splits_json} "
                  f"(non assignés, ignorés): {unassigned[:5]}{'...' if len(unassigned) > 5 else ''}")
        print(f"\nSplits (figés depuis {args.splits_json}): "
              f"train={len(splits_map['train'])} val={len(splits_map['val'])} "
              f"test={len(splits_map['test'])}")
    else:
        # Deterministic random split
        rng = random.Random(args.seed)
        rng.shuffle(images)
        n = len(images)
        n_train = int(n * args.train_ratio)
        n_val = int(n * args.val_ratio)
        splits_map = {
            "train": images[:n_train],
            "val": images[n_train:n_train + n_val],
            "test": images[n_train + n_val:],
        }
        print(f"\nSplits: train={len(splits_map['train'])} "
              f"val={len(splits_map['val'])} test={len(splits_map['test'])}")

    splits_log = {"train": [], "val": [], "test": []}
    total_counts = {"rooms": 0, "walls": 0, "background": 0,
                    "skipped_unknown": 0, "skipped_empty": 0}
    skipped_images: list[tuple[str, str]] = []

    for split, imgs in splits_map.items():
        for img_info in tqdm(imgs, desc=f"export {split}"):
            file_name = img_info["file_name"]
            sample_id = Path(file_name).stem

            # Load source image
            src_path = plans_dir / file_name
            if not src_path.exists():
                skipped_images.append((file_name, "src not found"))
                continue
            img = cv2.imread(str(src_path))
            if img is None:
                skipped_images.append((file_name, "unreadable"))
                continue

            # Resize semantic/instance to match image actual dims if CVAT's dims differ
            real_h, real_w = img.shape[:2]
            if (real_w, real_h) != (img_info["width"], img_info["height"]):
                # Adjust img_info to use real dims (CVAT sometimes stores logical dims)
                img_info["width"], img_info["height"] = real_w, real_h

            anns = anns_by_image.get(img_info["id"], [])
            sem, inst, counts = rasterize_image(img_info, anns, cat_mapping)
            for k in counts:
                total_counts[k] += counts[k]

            # Write outputs
            img_out = out / "images" / split / f"{sample_id}.png"
            sem_out = out / "semantic" / split / f"{sample_id}.png"
            inst_out = out / "instance" / split / f"{sample_id}.png"

            try:
                cv2.imwrite(str(img_out), img)
                cv2.imwrite(str(sem_out), sem)
                cv2.imwrite(str(inst_out), inst)
            except Exception as e:
                skipped_images.append((file_name, f"write_err:{e}"))
                continue

            splits_log[split].append(sample_id)

    # Splits.json
    (out / "splits.json").write_text(json.dumps(splits_log, indent=2))

    # dataset.yaml
    yaml_text = (
        f"path: {out.as_posix()}\n"
        f"num_classes: {NUM_CLASSES}\n"
        "names:\n" + "\n".join(f"  - {n}" for n in CLASS_NAMES) + "\n"
        "splits: [train, val, test]\n"
        "source: FR_annotated\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    print(f"\n✓ Exported {sum(len(v) for v in splits_log.values())} plans to {out}")
    print(f"  train={len(splits_log['train'])} val={len(splits_log['val'])} test={len(splits_log['test'])}")
    print(f"\nAnnotation counts:")
    print(f"  rooms (with instance ID): {total_counts['rooms']}")
    print(f"  walls (stuff):            {total_counts['walls']}")
    print(f"  background (stuff):       {total_counts['background']}")
    print(f"  skipped unknown class:    {total_counts['skipped_unknown']}")
    print(f"  skipped empty polygons:   {total_counts['skipped_empty']}")
    if skipped_images:
        print(f"\n⚠ {len(skipped_images)} images skipped:")
        for name, reason in skipped_images[:10]:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()
