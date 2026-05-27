"""Export a CubiCasa Wall-only dataset from the existing cubicasa_panoptic.

Generates a BINARY Wall vs Background semantic mask. All non-Wall classes
(Background, Kitchen, LivingRoom, ...) collapse to Background (0). Wall pixels
(class 1 in the source) become 1.

Instance mask is all zeros (Wall is stuff, not instanceable).

Reuses source images via symlinks (zero copy, ~5 sec).

The output layout matches PanopticDataset's expectations so the existing
trainer can consume it without any code change:

    <out>/
      images/{train,val,test}/<sample>.png     (symlinks to source)
      semantic/{train,val,test}/<sample>.png   uint8, 0=BG, 1=Wall
      instance/{train,val,test}/<sample>.png   uint16, all zeros
      splits.json
      dataset.yaml

Usage:
    python scripts/cubicasa5k_export_wall.py \\
        --src data/processed/cubicasa_panoptic \\
        --out data/processed/cubicasa_wall_only

Note: with the "pragmatic" approach we keep NUM_CLASSES=10 in the model. The
model will simply learn that classes 2-9 never have positive examples and
predict 0 or 1 everywhere. Slightly inefficient (10 query channels used
instead of 2) but works with zero refactor.
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
import numpy as np
from tqdm import tqdm

from src.segmentation.classes import CLASS_ID

WALL_CLASS_ID = CLASS_ID["Wall"]  # = 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/processed/cubicasa_panoptic",
                    help="Source panoptic root (output of cubicasa5k_export_segmentation.py)")
    ap.add_argument("--out", default="data/processed/cubicasa_wall_only",
                    help="Output directory for Wall-only dataset")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()

    if not (src / "splits.json").is_file():
        raise SystemExit(f"splits.json not found in {src} — "
                         f"run cubicasa5k_export_segmentation.py first.")
    splits = json.loads((src / "splits.json").read_text())

    for sub in ("images", "semantic", "instance"):
        for split in splits.keys():
            (out / sub / split).mkdir(parents=True, exist_ok=True)

    n_wall_total = 0
    n_pixels_total = 0
    skipped: list[tuple[str, str]] = []

    for split, ids in splits.items():
        for sid in tqdm(ids, desc=f"wall-only {split}"):
            img_src = src / "images" / split / f"{sid}.png"
            sem_src = src / "semantic" / split / f"{sid}.png"

            if not img_src.exists() or not sem_src.exists():
                skipped.append((sid, "src missing"))
                continue

            # Image: symlink
            img_dst = out / "images" / split / f"{sid}.png"
            if img_dst.is_symlink() or img_dst.exists():
                img_dst.unlink()
            img_dst.symlink_to(img_src)

            # Semantic: binary Wall mask
            sem = cv2.imread(str(sem_src), cv2.IMREAD_UNCHANGED)
            if sem is None:
                skipped.append((sid, "sem unreadable"))
                continue
            sem_wall = (sem == WALL_CLASS_ID).astype(np.uint8)
            cv2.imwrite(str(out / "semantic" / split / f"{sid}.png"), sem_wall)

            # Instance: all zeros (Wall = stuff)
            inst_zero = np.zeros_like(sem_wall, dtype=np.uint16)
            cv2.imwrite(str(out / "instance" / split / f"{sid}.png"), inst_zero)

            n_wall_total += int(sem_wall.sum())
            n_pixels_total += sem_wall.size

    # Splits.json: copy as-is
    shutil.copy(src / "splits.json", out / "splits.json")

    # dataset.yaml — note num_classes=2 is informational, the trainer uses
    # NUM_CLASSES=10 from src.segmentation.classes (pragmatic approach).
    yaml_text = (
        f"path: {out.as_posix()}\n"
        "num_classes: 2  # 0=Background, 1=Wall (training uses 10-class model)\n"
        "names:\n  - Background\n  - Wall\n"
        "splits: [train, val, test]\n"
        "source: CubiCasa5K — Wall-only binary mask\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    print(f"\n✓ Wall-only dataset built at {out}")
    for split, ids in splits.items():
        print(f"  {split}: {len(ids)} samples")
    if n_pixels_total > 0:
        pct = n_wall_total / n_pixels_total * 100
        print(f"  Wall pixel ratio: {pct:.2f}% (sanity check: should be ~3-8%)")
    if skipped:
        print(f"\n⚠ {len(skipped)} samples skipped:")
        for sid, reason in skipped[:5]:
            print(f"  {sid}: {reason}")


if __name__ == "__main__":
    main()
