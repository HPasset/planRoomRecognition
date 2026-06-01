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
DWG_ROOT = PROJECT_ROOT / "data" / "processed" / "dwg_walls"
OUT_ROOT = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only"

SPLITS = ("train", "val", "test")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if OUT_ROOT.exists():
        if args.overwrite:
            shutil.rmtree(OUT_ROOT)
        else:
            print(f"ERROR: {OUT_ROOT} existe déjà. Utilise --overwrite.")
            sys.exit(1)

    with (DWG_ROOT / "meta.json").open() as f:
        meta = json.load(f)

    splits: dict[str, list[str]] = {s: [] for s in SPLITS}

    for split in SPLITS:
        for sub in ("images", "semantic", "instance"):
            (OUT_ROOT / sub / split).mkdir(parents=True, exist_ok=True)

        for entry in meta["splits"][split]:
            orig_id = Path(entry["img"]).stem  # "img_0001"
            stem = orig_id.replace("img_", "")
            new_id = f"dwg_{stem}"

            src_img = DWG_ROOT / split / entry["img"]
            src_mask = DWG_ROOT / split / entry["mask"]
            dst_img = OUT_ROOT / "images" / split / f"{new_id}.png"
            dst_sem = OUT_ROOT / "semantic" / split / f"{new_id}.png"
            dst_inst = OUT_ROOT / "instance" / split / f"{new_id}.png"

            shutil.copy2(src_img, dst_img)
            mask = cv2.imread(str(src_mask), cv2.IMREAD_GRAYSCALE)
            sem = (mask > 127).astype(np.uint8)
            cv2.imwrite(str(dst_sem), sem)
            cv2.imwrite(str(dst_inst), np.zeros(mask.shape, dtype=np.uint16))

            splits[split].append(new_id)

    with (OUT_ROOT / "splits.json").open("w") as f:
        json.dump(splits, f, indent=2)

    (OUT_ROOT / "dataset.yaml").write_text(
        f"path: {OUT_ROOT.resolve()}\n"
        "num_classes: 2  # 0=Background, 1=Wall (training uses 10-class model)\n"
        "names:\n"
        "  - Background\n"
        "  - Wall\n"
        "splits: [train, val, test]\n"
        "source: DWG plans only (50 paires curees, rendu matplotlib)\n",
        encoding="utf-8",
    )

    print("=== Résumé walls_dwg_only ===")
    for split in SPLITS:
        print(f"  {split:5s} : {len(splits[split]):3d} samples")
    print(f"\nDataset prêt : {OUT_ROOT}")


if __name__ == "__main__":
    main()
