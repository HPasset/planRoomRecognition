"""Génère img/mask/overlay 1024² pour chaque DXF d'un dossier source, sans
splits ni meta — usage = inspection visuelle avant inclusion au dataset.

Inputs  : --src <dir>  (défaut : data/raw/plans_dxf_dwglab/)
Outputs : --out <dir>  (défaut : data/processed/dwg_walls_dwglab_preview/)
  Sous-dossiers :
    images/   <stem>.png         (rendu plan style PDF artisan)
    masks/    <stem>.png          (mask binaire murs, 0/255)
    overlays/ <stem>.png          (image + masque rouge transparent)
  Fichier stats.json : taille, n_wall_segments, wall_pixel_ratio par plan

Run :
    .venv/bin/python scripts/preview_dwg_walls.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "experiments" / "dwg_pipeline"))

from build_training_dataset import (  # noqa: E402
    extract_segments_by_category,
    bbox_from_segments,
    crop_segments_to_bbox,
    render_pair,
    size_bin,
)


def make_overlay(image: np.ndarray, mask: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    """Image RGB + mask (0/255) → overlay RGB avec mur en rouge transparent."""
    red = np.zeros_like(image)
    red[..., 0] = 255
    a = (mask > 127).astype(np.float32)[..., None] * alpha
    return (image * (1 - a) + red * a).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path,
                    default=PROJECT_ROOT / "data" / "raw" / "plans_dxf_dwglab")
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "data" / "processed" / "dwg_walls_dwglab_preview")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limiter à N DXF pour tester")
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: {args.src} n'existe pas.")
        sys.exit(1)

    dxf_files = sorted(args.src.glob("*.dxf"))
    if args.limit:
        dxf_files = dxf_files[:args.limit]
    print(f"{len(dxf_files)} DXF trouvés dans {args.src}")

    for sub in ("images", "masks", "overlays"):
        (args.out / sub).mkdir(parents=True, exist_ok=True)

    stats = []
    for i, dxf in enumerate(dxf_files, 1):
        stem = dxf.stem
        print(f"[{i}/{len(dxf_files)}] {stem}", end=" ")
        try:
            walls, context = extract_segments_by_category(dxf)
            if not walls:
                print("WALL_EMPTY (skipped)")
                stats.append({"stem": stem, "status": "no_walls"})
                continue

            bbox = bbox_from_segments(walls)
            if bbox is None:
                print("BBOX_FAIL (skipped)")
                stats.append({"stem": stem, "status": "bbox_fail"})
                continue

            context_cropped = crop_segments_to_bbox(context, bbox, margin_factor=1.1)
            image, mask = render_pair(walls, context_cropped, bbox)

            cv2.imwrite(str(args.out / "images" / f"{stem}.png"),
                        cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            cv2.imwrite(str(args.out / "masks" / f"{stem}.png"), mask)
            overlay = make_overlay(image, mask)
            cv2.imwrite(str(args.out / "overlays" / f"{stem}.png"),
                        cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

            ratio = float((mask > 127).mean())
            n_walls = len(walls)
            sb = size_bin(n_walls)
            print(f"walls={n_walls} ratio={ratio:.3f} bin={sb}")
            stats.append({
                "stem": stem,
                "status": "ok",
                "n_wall_segments": n_walls,
                "n_context_segments": len(context),
                "wall_pixel_ratio": round(ratio, 4),
                "size_bin": sb,
            })
        except Exception as e:
            print(f"ERROR: {e!r}")
            stats.append({"stem": stem, "status": "error", "error": str(e)})

    (args.out / "stats.json").write_text(json.dumps(stats, indent=2))
    ok = sum(1 for s in stats if s["status"] == "ok")
    print(f"\n=== Bilan ===")
    print(f"OK         : {ok}/{len(stats)}")
    for status in ("no_walls", "bbox_fail", "error"):
        n = sum(1 for s in stats if s["status"] == status)
        if n:
            print(f"{status:11s}: {n}")
    print(f"\nOverlays dans : {args.out}/overlays/")


if __name__ == "__main__":
    main()
