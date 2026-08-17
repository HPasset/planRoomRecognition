"""Construit data/processed/dwg_walls_v3/ en cumulant :
- les 149 paires de dwg_walls_v2 (préservées telles quelles)
- les N nouvelles paires annotées CVAT (depuis data/processed/fr_walls/
  ou un autre dossier passé en argument)

IDs globalement uniques : v2 garde 1..149, les FR commencent à 150.

Usage :
    .venv/bin/python scripts/build_dwg_walls_v3.py \\
        --fr-source data/processed/fr_walls \\
        --out data/processed/dwg_walls_v3

    # v4 : plusieurs sources FR + val/test 100 %% FR
    .venv/bin/python scripts/build_dwg_walls_v3.py \\
        --fr-source data/processed/fr_walls data/processed/fr_walls_v2 \\
        --dwg-all-train --out data/processed/walls_fr_v4
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DWG_V2 = PROJECT_ROOT / "data" / "processed" / "dwg_walls_v2"
DEFAULT_FR = PROJECT_ROOT / "data" / "processed" / "fr_walls"
DEFAULT_OUT = PROJECT_ROOT / "data" / "processed" / "dwg_walls_v3"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dwg-v2", type=Path, default=DEFAULT_DWG_V2)
    ap.add_argument("--fr-source", type=Path, nargs="+", default=[DEFAULT_FR])
    ap.add_argument("--dwg-all-train", action="store_true",
                    help="verse tout le DWG dans train : le val et le test ne "
                         "contiennent alors que du FR. Sans ça le val est à "
                         "23 DWG pour 4 FR, et toute métrique de mur y est "
                         "dominée par des plans qui ne ressemblent pas aux nôtres.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.dwg_v2.exists():
        print(f"ERROR: dwg_walls_v2 absent : {args.dwg_v2}")
        sys.exit(1)
    for src in args.fr_source:
        if not src.exists():
            print(f"ERROR: source FR absente : {src}. "
                  "Lance d'abord scripts/cvat_to_walls_dataset.py.")
            sys.exit(1)

    if args.out.exists():
        print(f"Removing existing {args.out}")
        shutil.rmtree(args.out)
    for split in ("train", "val", "test"):
        (args.out / split).mkdir(parents=True, exist_ok=True)

    new_splits = {"train": [], "val": [], "test": []}

    # 1. Copy dwg_walls_v2 (149 entrées, IDs 1..149 préservés)
    v2_meta = json.loads((args.dwg_v2 / "meta.json").read_text())
    for split in ("train", "val", "test"):
        for entry in v2_meta["splits"][split]:
            dest = "train" if args.dwg_all_train else split
            new_splits[dest].append(entry.copy())
            shutil.copy2(args.dwg_v2 / split / entry["img"],
                         args.out / dest / entry["img"])
            shutil.copy2(args.dwg_v2 / split / entry["mask"],
                         args.out / dest / entry["mask"])
    n_v2 = sum(len(new_splits[s]) for s in new_splits)
    max_v2_id = max(e["id"] for s in new_splits.values() for e in s)
    next_id = max_v2_id + 1
    print(f"DWG v2 : {n_v2} entrées copiées (IDs 1..{max_v2_id})")

    # 2. Copy les sources FR (renumérotées IDs 150..)
    fr_count = 0
    for src in args.fr_source:
        fr_meta = json.loads((src / "meta.json").read_text())
        n_src = 0
        for split in ("train", "val", "test"):
            for entry in fr_meta["splits"][split]:
                new_id = next_id
                next_id += 1
                new_img = f"img_{new_id:04d}.png"
                new_mask = f"mask_{new_id:04d}.png"
                shutil.copy2(src / split / entry["img"], args.out / split / new_img)
                shutil.copy2(src / split / entry["mask"], args.out / split / new_mask)
                new_splits[split].append({
                    "id": new_id,
                    "img": new_img,
                    "mask": new_mask,
                    "source_image": entry.get("source_image"),
                    "source_set": entry.get("source_set", "cvat_fr"),
                    "source_dataset": src.name,
                    "wall_pixel_ratio": entry.get("wall_pixel_ratio"),
                })
                fr_count += 1
                n_src += 1
        print(f"FR  : {n_src} entrées depuis {src.name}")
    print(f"FR  : {fr_count} entrées au total (IDs {max_v2_id + 1}..{next_id - 1})")

    # Sort splits by id
    for split in new_splits:
        new_splits[split].sort(key=lambda e: e["id"])

    # 3. Meta
    out_meta = {
        "size": v2_meta.get("size"),
        "seed": v2_meta.get("seed"),
        "stroke_wall": v2_meta.get("stroke_wall"),
        "stroke_context": v2_meta.get("stroke_context"),
        "build_notes": (
            f"dwg_walls_v2 ({n_v2} paires DWG"
            f"{', toutes en train' if args.dwg_all_train else ''}) + "
            f"{', '.join(s.name for s in args.fr_source)} "
            f"({fr_count} paires architectes FR annotées CVAT). "
            f"Total = {n_v2 + fr_count} paires."
        ),
        "splits": new_splits,
    }
    (args.out / "meta.json").write_text(json.dumps(out_meta, indent=2))

    totals = {s: len(new_splits[s]) for s in ("train", "val", "test")}
    print(f"\n=== Bilan dwg_walls_v3 ===")
    print(f"Total : {sum(totals.values())} paires (vs {n_v2} en v2)")
    for s in ("train", "val", "test"):
        print(f"  {s:5s}: {totals[s]}")
    print(f"\nOutput : {args.out}")


if __name__ == "__main__":
    main()
