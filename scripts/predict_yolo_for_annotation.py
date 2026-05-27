"""Pre-annotate FR plans with yolo11m COCO weights for CVAT import (Brique A).

Detects furniture from COCO classes that overlap with our 9 NFC classes:
  - refrigerator (COCO) → Refrigerator
  - toilet (COCO) → Toilet
  - sink (COCO) → WashBasin (default; user reclasses KitchenSink in CVAT)

Output: COCO 1.0 JSON importable in CVAT, with all 9 NFC categories pre-defined.
The 6 non-COCO classes (Bathtub, Shower, KitchenSink, Cooktop, Dishwasher,
WashingMachine) are declared as empty categories — user annotates them
manually in CVAT.

Usage:
    python scripts/predict_yolo_for_annotation.py \\
        --weights yolo11m.pt \\
        --plans_dir data/raw/plans_fr \\
        --out data/processed/cvat_import/brique_a_preanno.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
from tqdm import tqdm
from ultralytics import YOLO


# Our 10 classes (9 NFC + Bed for chambre placement rules)
# Order matters: category_id = index + 1, CVAT convention
BATIA_CLASSES = [
    "Bathtub", "Shower", "WashBasin", "Toilet", "KitchenSink",
    "Cooktop", "Refrigerator", "Dishwasher", "WashingMachine",
    "Bed",  # Mobilier ambiance : sert au placement des prises chevet
]
NAME_TO_CAT_ID = {n: i + 1 for i, n in enumerate(BATIA_CLASSES)}

# COCO class names (yolo11 default) → our 9 classes.
# Only 3 COCO classes overlap usefully:
#   - "refrigerator" maps cleanly to Refrigerator
#   - "toilet" maps cleanly to Toilet
#   - "sink" is AMBIGUOUS (kitchen vs bath) — default to WashBasin (most common
#     case on residential plans: 1-2 lavabos SDB > 1 évier cuisine). The user
#     reclasses kitchen sinks manually in CVAT.
COCO_TO_BATIA = {
    "refrigerator": "WashBasin",  # placeholder, overridden below
}
# Re-defined explicitly to avoid bugs:
COCO_TO_BATIA = {
    "refrigerator": "Refrigerator",
    "toilet": "Toilet",
    "sink": "WashBasin",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="yolo11m.pt",
                    help="YOLO weights path (auto-downloaded by ultralytics if needed)")
    ap.add_argument("--plans_dir", required=True,
                    help="Directory with FR plan images")
    ap.add_argument("--out", required=True,
                    help="Output COCO 1.0 JSON path")
    ap.add_argument("--conf", type=float, default=0.25,
                    help="Min confidence threshold for detections (default 0.25)")
    args = ap.parse_args()

    plans_dir = Path(args.plans_dir)
    out_path = Path(args.out)
    if not plans_dir.is_dir():
        raise SystemExit(f"plans_dir not found: {plans_dir}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    plans = sorted(
        list(plans_dir.glob("*.png"))
        + list(plans_dir.glob("*.jpg"))
        + list(plans_dir.glob("*.jpeg"))
    )
    if not plans:
        raise SystemExit(f"No plan images found in {plans_dir}")

    print(f"Loading YOLO weights: {args.weights}")
    model = YOLO(args.weights)
    coco_names = model.names  # dict: {idx: name}
    coco_name_set = set(coco_names.values())

    # Sanity: warn if expected COCO names absent (e.g. custom weights)
    missing = [n for n in COCO_TO_BATIA if n not in coco_name_set]
    if missing:
        print(f"⚠ COCO classes not found in this model: {missing}. "
              f"Pre-annotation will skip them.")

    coco_out = {
        "info": {
            "description": "batIA Brique A pre-annotation (yolo11m COCO)",
            "version": "1.0",
        },
        "licenses": [{"id": 1, "name": "internal", "url": ""}],
        "categories": [
            {"id": cid, "name": name, "supercategory": ""}
            for name, cid in NAME_TO_CAT_ID.items()
        ],
        "images": [],
        "annotations": [],
    }

    ann_id = 1
    stats: dict[str, int] = {n: 0 for n in BATIA_CLASSES}
    skipped = 0

    for img_id, plan in enumerate(tqdm(plans, desc="pre-annotating"), 1):
        img = cv2.imread(str(plan))
        if img is None:
            skipped += 1
            continue
        h, w = img.shape[:2]

        coco_out["images"].append({
            "id": img_id,
            "file_name": plan.name,
            "width": w,
            "height": h,
            "license": 1,
        })

        result = model(str(plan), conf=args.conf, verbose=False)[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue

        for box in result.boxes:
            class_id_coco = int(box.cls[0])
            class_name_coco = coco_names[class_id_coco]
            if class_name_coco not in COCO_TO_BATIA:
                continue

            batia_name = COCO_TO_BATIA[class_name_coco]
            cat_id = NAME_TO_CAT_ID[batia_name]

            x1, y1, x2, y2 = box.xyxy[0].tolist()
            bbox_w = max(0.0, x2 - x1)
            bbox_h = max(0.0, y2 - y1)
            if bbox_w < 1 or bbox_h < 1:
                continue

            coco_out["annotations"].append({
                "id": ann_id,
                "image_id": img_id,
                "category_id": cat_id,
                "bbox": [round(x1, 2), round(y1, 2),
                         round(bbox_w, 2), round(bbox_h, 2)],
                "area": round(bbox_w * bbox_h, 2),
                "iscrowd": 0,
                "segmentation": [],  # CVAT bbox mode (no polygon)
                "attributes": {
                    "score": float(box.conf[0]),
                    "source_coco_class": class_name_coco,
                },
            })
            ann_id += 1
            stats[batia_name] += 1

    out_path.write_text(json.dumps(coco_out, indent=2))

    print(f"\n✓ Pre-annotated {len(plans)} plans → {out_path}")
    print(f"  Total annotations: {len(coco_out['annotations'])}")
    print(f"\n  Per class (from COCO):")
    for name, n in stats.items():
        marker = "←" if name in COCO_TO_BATIA.values() else "  (annotate manually in CVAT)"
        print(f"    {name:>15s}: {n:>3} {marker}")

    if skipped:
        print(f"\n⚠ {skipped} unreadable images skipped")
    print(
        "\nNext steps:"
        "\n  1. Import this JSON in CVAT (Project: Brique A YOLO meubles)"
        "\n  2. Reclass 'WashBasin' detections that are actually kitchen sinks → KitchenSink"
        "\n  3. Annotate the 6 missing classes manually: Bathtub, Shower,"
        "\n     Cooktop, Dishwasher, WashingMachine (+ KitchenSink corrections)"
    )


if __name__ == "__main__":
    main()
