"""Pre-annotate FR plans with the Stage A model for CVAT import (COCO 1.0).

Workflow:
  1. Run inference on every plan in --plans_dir using the Stage A checkpoint.
  2. Convert each detected room polygon to COCO 1.0 format.
  3. Write a single CVAT-compatible JSON file ready to import.

Usage:
  python scripts/predict_for_annotation.py \\
    --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \\
    --plans_dir data/raw/plans_fr \\
    --out data/processed/cvat_import/fr_pre_annotations.json

After running, in CVAT:
  1. Create a new project with the 10 classes (Background, Wall, Kitchen, ...)
  2. Upload the plans from --plans_dir as a new task
  3. Import the JSON output as 'COCO 1.0' annotations
  4. Refine polygons + types per plan, then export the corrected dataset for Stage B.

Note: walls are NOT pre-annotated (skipped intentionally). Only room polygons (classes 2-9)
appear in the COCO file. The walls binary mask is still written to --walls_dir as a side
output (one PNG per plan) for visual inspection.
"""
import os

# MUST be set before torch import (Mask2Former MPS fallback for grid_sampler_2d)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import json
import sys
import time
from pathlib import Path

# Allow running from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
from tqdm import tqdm

from src.segmentation.classes import CLASS_NAMES, ROOM_CLASS_IDS
from src.segmentation.inference import SegmentationInference
from src.planrec.polygon_postprocess import postprocess_polygon, extract_wall_lines


SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


def _list_plans(plans_dir: Path) -> list[Path]:
    """Return all supported image files in plans_dir, sorted alphabetically."""
    return sorted(p for p in plans_dir.iterdir()
                  if p.is_file() and p.suffix.lower() in SUPPORTED_EXT)


def _polygon_to_coco_segmentation(polygon: list[list[int]]) -> list[list[float]]:
    """Convert [[x1, y1], [x2, y2], ...] to [[x1, y1, x2, y2, ...]] for COCO."""
    flat = [float(c) for point in polygon for c in point]
    return [flat]


def _bbox_to_coco_format(bbox: list[int]) -> list[float]:
    """Convert [xmin, ymin, xmax, ymax] to [x, y, width, height] (COCO convention)."""
    xmin, ymin, xmax, ymax = bbox
    return [float(xmin), float(ymin), float(xmax - xmin), float(ymax - ymin)]


def _make_categories() -> list[dict]:
    """Build COCO categories list for our 10 classes.

    All classes are listed (even Background and Wall) so that CVAT users can
    manually annotate them if needed, even if they aren't pre-annotated here.
    """
    return [
        {
            "id": cid,
            "name": name,
            "supercategory": "room" if cid in ROOM_CLASS_IDS else "stuff",
        }
        for cid, name in enumerate(CLASS_NAMES)
    ]


def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__,
    )
    ap.add_argument("--checkpoint", required=True,
                    help="Path to Stage A model checkpoint (best.pt)")
    ap.add_argument("--plans_dir", required=True,
                    help="Directory containing FR plans (.png / .jpg / ...)")
    ap.add_argument("--out", required=True,
                    help="Output JSON file (CVAT-importable, COCO 1.0)")
    ap.add_argument("--backbone",
                    default="facebook/mask2former-swin-small-coco-panoptic",
                    help="HuggingFace backbone id used at training")
    ap.add_argument("--image_size", type=int, default=768,
                    help="Inference resolution (default 768)")
    ap.add_argument("--device", default="auto",
                    help="auto / mps / cpu / cuda (default auto)")
    ap.add_argument("--walls_dir", default=None,
                    help="Directory to dump per-plan walls masks (PNG). "
                         "Default: <out>/../walls_tmp/")
    ap.add_argument("--limit", type=int, default=None,
                    help="Process only the first N plans (debug)")
    # --- Nettoyage des polygones (pour une pré-annotation éditable à la main) ---
    ap.add_argument("--simplify-epsilon", type=float, default=2.0,
                    help="Douglas-Peucker, %% du périmètre (2.0 ≈ 4-6 pts/pièce ; "
                         "0 = pas de simplification)")
    ap.add_argument("--axis-align-deg", type=float, default=10.0,
                    help="Aligne les bords à <N°> de l'horizontale/verticale → "
                         "rectangles nets (0 = désactivé)")
    ap.add_argument("--snap-walls", action="store_true",
                    help="Colle les bords des pièces sur les murs détectés "
                         "(utilise le masque murs du modèle)")
    ap.add_argument("--min-confidence", type=float, default=0.5,
                    help="Ignore les pièces sous ce score → laissées vides dans "
                         "CVAT (tu les dessines). Défaut 0.5")
    args = ap.parse_args()

    plans_dir = Path(args.plans_dir).resolve()
    out_path = Path(args.out).resolve()
    walls_dir = (Path(args.walls_dir).resolve()
                 if args.walls_dir
                 else out_path.parent / "walls_tmp")

    # Validate inputs
    if not plans_dir.is_dir():
        raise SystemExit(f"plans_dir not found: {plans_dir}")
    if not Path(args.checkpoint).is_file():
        raise SystemExit(f"checkpoint not found: {args.checkpoint}")

    plans = _list_plans(plans_dir)
    if args.limit:
        plans = plans[: args.limit]
    if not plans:
        raise SystemExit(
            f"No supported images found in {plans_dir} "
            f"(expected: {sorted(SUPPORTED_EXT)})"
        )

    print(f"Found {len(plans)} plans in {plans_dir}")

    # Initialize inference engine
    print(f"Loading model from {args.checkpoint} ...")
    inf = SegmentationInference(
        checkpoint_path=args.checkpoint,
        backbone=args.backbone,
        image_size=args.image_size,
        device=args.device,
        walls_out_dir=walls_dir,
    )
    print(f"Model loaded on device={inf.device}.")

    # Aggregate COCO output
    coco = {
        "info": {
            "description": "FR plans pre-annotations (Stage A bootstrap)",
            "version": "1.0",
            "year": time.strftime("%Y"),
            "contributor": "batIA",
            "date_created": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "licenses": [],
        "images": [],
        "annotations": [],
        "categories": _make_categories(),
    }

    annotation_id = 1
    skipped: list[tuple[str, str]] = []
    pts_raw = pts_clean = n_rooms_kept = n_rooms_dropped = 0

    for image_id, plan_path in enumerate(tqdm(plans, desc="Predicting"), start=1):
        # Get image dimensions
        bgr = cv2.imread(str(plan_path))
        if bgr is None:
            skipped.append((plan_path.name, "unreadable"))
            continue
        h, w = bgr.shape[:2]

        coco["images"].append({
            "id": image_id,
            "file_name": plan_path.name,
            "width": w,
            "height": h,
        })

        # Run inference
        try:
            result = inf.predict(plan_path)
        except Exception as e:
            skipped.append((plan_path.name, f"{type(e).__name__}: {e}"))
            continue

        # Snap-to-walls : lignes de murs extraites du masque produit par le modèle
        wall_lines = None
        if args.snap_walls and result.walls.mask_path:
            wmask = cv2.imread(result.walls.mask_path, cv2.IMREAD_UNCHANGED)
            if wmask is not None:
                wall_lines = extract_wall_lines(wmask)

        # Convert each detected room to a COCO annotation
        for room in result.rooms:
            if room.confidence < args.min_confidence:
                n_rooms_dropped += 1
                continue
            clean = postprocess_polygon(
                room.polygon,
                simplify_epsilon_pct=args.simplify_epsilon,
                axis_align_tolerance_deg=(args.axis_align_deg or None),
                wall_lines=wall_lines,
            )
            pts_raw += len(room.polygon)
            pts_clean += len(clean)
            n_rooms_kept += 1
            xs = [p[0] for p in clean]
            ys = [p[1] for p in clean]
            bbox = [min(xs), min(ys), max(xs), max(ys)]
            coco["annotations"].append({
                "id": annotation_id,
                "image_id": image_id,
                "category_id": room.type_id,
                "segmentation": _polygon_to_coco_segmentation(clean),
                "area": int(room.area_pixels),
                "bbox": _bbox_to_coco_format(bbox),
                "iscrowd": 0,
                "score": float(room.confidence),  # CVAT shows it on hover
            })
            annotation_id += 1

    # Persist
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(coco, indent=2))

    n_images = len(coco["images"])
    n_anns = len(coco["annotations"])

    print(f"\n✓ Wrote {out_path}")
    print(f"  {n_images} images, {n_anns} pre-annotations "
          f"({n_anns / max(1, n_images):.1f} rooms/plan on average)")
    if n_rooms_kept:
        print(f"  Points/pièce : {pts_raw / n_rooms_kept:.1f} brut → "
              f"{pts_clean / n_rooms_kept:.1f} après nettoyage "
              f"(simplify={args.simplify_epsilon} axis_align={args.axis_align_deg}° "
              f"snap_walls={args.snap_walls})")
    print(f"  Pièces gardées : {n_rooms_kept} | "
          f"ignorées (conf < {args.min_confidence}) : {n_rooms_dropped}")
    print(f"  Walls masks dumped to {walls_dir}")
    if skipped:
        print(f"\n⚠ {len(skipped)} plans skipped:")
        for name, reason in skipped[:10]:
            print(f"    {name}: {reason}")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more")

    print("\nNext steps in CVAT:")
    print("  1. Create a new project with the 10 classes "
          "(Background, Wall, Kitchen, LivingRoom, BedRoom, Bath, Entry, "
          "Storage, Garage, Outdoor)")
    print(f"  2. Create a task and upload your plans from {plans_dir}")
    print(f"  3. Import {out_path.name} as 'COCO 1.0' annotations")
    print("  4. Refine polygons + types per plan")
    print("  5. Export the corrected dataset (COCO 1.0) → use for Stage B fine-tuning")


if __name__ == "__main__":
    main()
