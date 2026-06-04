"""Construit un dataset DWG-only au format Cubicasa attendu par
src/segmentation/dataset.py (images / semantic / instance / splits.json).

Source : data/processed/dwg_walls/{train,val,test}/{img_NNNN.png, mask_NNNN.png}
Sortie : data/processed/walls_dwg_only/

Pas de sample_origins.json (pas d'oversampling utile, 100% DWG).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = PROJECT_ROOT / "data" / "processed" / "dwg_walls"
DEFAULT_OUT = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only"

SPLITS = ("train", "val", "test")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC,
                    help="Source dir (contient meta.json + train/val/test)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="Output dir au format Cubicasa-like")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    src_root: Path = args.src
    out_root: Path = args.out

    if out_root.exists():
        if args.overwrite:
            shutil.rmtree(out_root)
        else:
            print(f"ERROR: {out_root} existe déjà. Utilise --overwrite.")
            sys.exit(1)

    with (src_root / "meta.json").open() as f:
        meta = json.load(f)

    splits: dict[str, list[str]] = {s: [] for s in SPLITS}

    for split in SPLITS:
        for sub in ("images", "semantic", "instance"):
            (out_root / sub / split).mkdir(parents=True, exist_ok=True)

        for entry in meta["splits"][split]:
            orig_id = Path(entry["img"]).stem  # "img_0001"
            stem = orig_id.replace("img_", "")
            new_id = f"dwg_{stem}"

            src_img = src_root / split / entry["img"]
            src_mask = src_root / split / entry["mask"]
            dst_img = out_root / "images" / split / f"{new_id}.png"
            dst_sem = out_root / "semantic" / split / f"{new_id}.png"
            dst_inst = out_root / "instance" / split / f"{new_id}.png"

            shutil.copy2(src_img, dst_img)
            mask = cv2.imread(str(src_mask), cv2.IMREAD_GRAYSCALE)
            sem = (mask > 127).astype(np.uint8)
            cv2.imwrite(str(dst_sem), sem)
            cv2.imwrite(str(dst_inst), np.zeros(mask.shape, dtype=np.uint16))

            splits[split].append(new_id)

    with (out_root / "splits.json").open("w") as f:
        json.dump(splits, f, indent=2)

    n_total = sum(len(splits[s]) for s in SPLITS)
    (out_root / "dataset.yaml").write_text(
        f"path: {out_root.resolve()}\n"
        "num_classes: 2  # 0=Background, 1=Wall (training uses 10-class model)\n"
        "names:\n"
        "  - Background\n"
        "  - Wall\n"
        "splits: [train, val, test]\n"
        f"source: DWG plans only ({n_total} paires depuis {src_root.name})\n",
        encoding="utf-8",
    )

    print(f"=== Résumé {out_root.name} ===")
    for split in SPLITS:
        print(f"  {split:5s} : {len(splits[split]):3d} samples")
    print(f"\nDataset prêt : {out_root}")


if __name__ == "__main__":
    main()
