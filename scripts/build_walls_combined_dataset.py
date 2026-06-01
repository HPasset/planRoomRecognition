"""Fusionne data/processed/cubicasa_wall_only + data/processed/dwg_walls en un
dataset combiné `data/processed/walls_combined/` au format Cubicasa attendu par
src/segmentation/dataset.py (images / semantic / instance / splits.json).

Stratégie :
- Cubicasa : symlinks vers les fichiers existants (zéro duplication).
- DWG     : copie + conversion masque 0/255 → 0/1 indexé + instance zeros.
- IDs préfixés `cc_<orig>` et `dwg_<orig>` pour éviter collisions.
- sample_origins.json mappe chaque ID → "cc" ou "dwg" pour permettre
  l'oversampling configurable côté trainer.

Run :
    .venv/bin/python scripts/build_walls_combined_dataset.py
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
CC_ROOT = PROJECT_ROOT / "data" / "processed" / "cubicasa_wall_only"
DWG_ROOT = PROJECT_ROOT / "data" / "processed" / "dwg_walls"
OUT_ROOT = PROJECT_ROOT / "data" / "processed" / "walls_combined"

SPLITS = ("train", "val", "test")


def link_cubicasa(out_root: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Symlink Cubicasa wall_only files into out_root with cc_ prefix."""
    with (CC_ROOT / "splits.json").open() as f:
        cc_splits = json.load(f)

    splits: dict[str, list[str]] = {s: [] for s in SPLITS}
    origins: dict[str, str] = {}

    for split in SPLITS:
        for sub in ("images", "semantic", "instance"):
            (out_root / sub / split).mkdir(parents=True, exist_ok=True)

        for sid in cc_splits[split]:
            new_id = f"cc_{sid}"
            for sub in ("images", "semantic", "instance"):
                src = CC_ROOT / sub / split / f"{sid}.png"
                dst = out_root / sub / split / f"{new_id}.png"
                if dst.exists() or dst.is_symlink():
                    dst.unlink()
                dst.symlink_to(src.resolve())
            splits[split].append(new_id)
            origins[new_id] = "cc"

    print(f"  Cubicasa : {sum(len(splits[s]) for s in SPLITS)} samples liés")
    return splits, origins


def convert_dwg(
    out_root: Path,
    splits: dict[str, list[str]],
    origins: dict[str, str],
) -> None:
    """Convertit DWG (mask 0/255 grayscale) → format Cubicasa (semantic 0/1
    indexé + instance uint16 zeros). Stocke sous dwg_<orig_id>."""
    with (DWG_ROOT / "meta.json").open() as f:
        meta = json.load(f)

    n_added = 0
    for split in SPLITS:
        for entry in meta["splits"][split]:
            orig_id = Path(entry["img"]).stem  # "img_0001"
            stem = orig_id.replace("img_", "")  # "0001"
            new_id = f"dwg_{stem}"

            src_img = DWG_ROOT / split / entry["img"]
            src_mask = DWG_ROOT / split / entry["mask"]
            dst_img = out_root / "images" / split / f"{new_id}.png"
            dst_sem = out_root / "semantic" / split / f"{new_id}.png"
            dst_inst = out_root / "instance" / split / f"{new_id}.png"

            # Image : copie directe (déjà RGB 1024×1024)
            shutil.copy2(src_img, dst_img)

            # Semantic : 0/255 grayscale → 0/1 uint8 indexé
            mask = cv2.imread(str(src_mask), cv2.IMREAD_GRAYSCALE)
            sem = (mask > 127).astype(np.uint8)  # 0 = BG, 1 = Wall
            cv2.imwrite(str(dst_sem), sem)

            # Instance : walls = stuff, donc tous zeros uint16
            inst = np.zeros(mask.shape, dtype=np.uint16)
            cv2.imwrite(str(dst_inst), inst)

            splits[split].append(new_id)
            origins[new_id] = "dwg"
            n_added += 1

    print(f"  DWG      : {n_added} samples convertis + copiés")


def write_metadata(
    out_root: Path,
    splits: dict[str, list[str]],
    origins: dict[str, str],
) -> None:
    with (out_root / "splits.json").open("w") as f:
        json.dump(splits, f, indent=2)
    with (out_root / "sample_origins.json").open("w") as f:
        json.dump(origins, f, indent=2)
    dataset_yaml = (
        f"path: {out_root.resolve()}\n"
        "num_classes: 2  # 0=Background, 1=Wall (training uses 10-class model)\n"
        "names:\n"
        "  - Background\n"
        "  - Wall\n"
        "splits: [train, val, test]\n"
        "source: CubiCasa5K wall_only + DWG plans (combiné via "
        "scripts/build_walls_combined_dataset.py)\n"
        f"origins: cc (Cubicasa Japon) + dwg (plans monde, rendu matplotlib)\n"
    )
    (out_root / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")


def sanity_check(out_root: Path) -> None:
    """Charge 1 sample par origine + split pour vérifier le format."""
    print("\n=== Sanity check ===")
    with (out_root / "splits.json").open() as f:
        splits = json.load(f)
    with (out_root / "sample_origins.json").open() as f:
        origins = json.load(f)

    for split in SPLITS:
        ids = splits[split]
        cc_ids = [sid for sid in ids if origins[sid] == "cc"][:1]
        dwg_ids = [sid for sid in ids if origins[sid] == "dwg"][:1]
        for sid in cc_ids + dwg_ids:
            img = cv2.imread(str(out_root / "images" / split / f"{sid}.png"))
            sem = cv2.imread(
                str(out_root / "semantic" / split / f"{sid}.png"),
                cv2.IMREAD_UNCHANGED,
            )
            inst = cv2.imread(
                str(out_root / "instance" / split / f"{sid}.png"),
                cv2.IMREAD_UNCHANGED,
            )
            sem_uniques = sorted(np.unique(sem).tolist())
            inst_uniques = sorted(np.unique(inst).tolist())[:5]
            print(
                f"  {split:5s} {sid:18s} img={img.shape} "
                f"sem_uniques={sem_uniques} inst_uniques={inst_uniques} "
                f"sem_dtype={sem.dtype} inst_dtype={inst.dtype}"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if OUT_ROOT.exists():
        if args.overwrite:
            print(f"Suppression {OUT_ROOT}")
            shutil.rmtree(OUT_ROOT)
        else:
            print(f"ERROR: {OUT_ROOT} existe déjà. Utilise --overwrite.")
            sys.exit(1)

    if not CC_ROOT.exists():
        print(f"ERROR: Cubicasa wall_only introuvable à {CC_ROOT}")
        sys.exit(1)
    if not DWG_ROOT.exists():
        print(f"ERROR: DWG walls introuvable à {DWG_ROOT}")
        sys.exit(1)

    print(f"Cubicasa : {CC_ROOT}")
    print(f"DWG      : {DWG_ROOT}")
    print(f"Output   : {OUT_ROOT}")

    splits: dict[str, list[str]] = {s: [] for s in SPLITS}
    origins: dict[str, str] = {}

    print("\n=== Liaison Cubicasa (symlinks) ===")
    splits, origins = link_cubicasa(OUT_ROOT)

    print("\n=== Conversion DWG (copy + cast) ===")
    convert_dwg(OUT_ROOT, splits, origins)

    write_metadata(OUT_ROOT, splits, origins)

    print("\n=== Résumé ===")
    for split in SPLITS:
        cc_n = sum(1 for sid in splits[split] if origins[sid] == "cc")
        dwg_n = sum(1 for sid in splits[split] if origins[sid] == "dwg")
        print(f"  {split:5s} : {len(splits[split]):5d} samples ({cc_n} cc + {dwg_n} dwg)")

    sanity_check(OUT_ROOT)
    print(f"\nDataset prêt : {OUT_ROOT}")


if __name__ == "__main__":
    main()
