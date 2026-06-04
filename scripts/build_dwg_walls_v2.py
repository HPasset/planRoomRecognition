"""Construit data/processed/dwg_walls_v2/ en cumulant l'ancien lot
(data/processed/dwg_walls/) et les 99 nouveaux DWG dwglab retenus après
triage visuel.

Splits :
- Les 50 entrées existantes gardent leur split (train/val/test) — pour
  préserver la comparabilité avec wall_only_dwg_v1.
- Les 99 nouvelles (img/mask déjà rendus dans
  data/processed/dwg_walls_dwglab_preview/) sont stratifiées 70/15/15
  par size_bin avec seed=42 et ajoutées à chaque split.

IDs :
- Renumérotation GLOBALE 1..149 (l'ancien dataset utilisait des IDs
  contiguous par split, ce qui crée des collisions img_0001.png entre
  splits dans le repackager). Nouvelle convention : un ID unique = un
  fichier img_NNNN.png unique, peu importe le split.

EXCLUSIONS (post-review utilisateur) :
- PROJET_01           multi-étages CASANOVA, ratio 0.004
- PROJET_02           Archicad XREF dégénéré, 0 mur
- RE-SingDetch-HH_AG  0 mur extrait
"""
from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OLD_ROOT = PROJECT_ROOT / "data" / "processed" / "dwg_walls"
PREVIEW_ROOT = PROJECT_ROOT / "data" / "processed" / "dwg_walls_dwglab_preview"
OUT_ROOT = PROJECT_ROOT / "data" / "processed" / "dwg_walls_v2"

EXCLUDE_STEMS = {"PROJET_01", "PROJET_02", "RE-SingDetch-HH_AG"}
SEED = 42
SPLITS_RATIO = {"train": 0.70, "val": 0.15, "test": 0.15}


def main():
    if OUT_ROOT.exists():
        print(f"Removing existing {OUT_ROOT}")
        shutil.rmtree(OUT_ROOT)
    for split in ("train", "val", "test"):
        (OUT_ROOT / split).mkdir(parents=True, exist_ok=True)

    new_splits: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    next_id = 1  # global counter

    # 1. Old dataset : preserve split assignment, renumber globally
    old_meta = json.loads((OLD_ROOT / "meta.json").read_text())
    for split in ("train", "val", "test"):
        for entry in old_meta["splits"][split]:
            new_id = next_id
            next_id += 1
            new_img = f"img_{new_id:04d}.png"
            new_mask = f"mask_{new_id:04d}.png"
            shutil.copy2(OLD_ROOT / split / entry["img"],
                         OUT_ROOT / split / new_img)
            shutil.copy2(OLD_ROOT / split / entry["mask"],
                         OUT_ROOT / split / new_mask)
            new_splits[split].append({
                "id": new_id,
                "img": new_img,
                "mask": new_mask,
                "source_dxf": entry["source_dxf"],
                "source_set": "plans_dxf",
                "n_wall_segments": entry["n_wall_segments"],
                "n_context_segments": entry["n_context_segments"],
                "size_bin": entry["size_bin"],
                "wall_pixel_ratio": entry["wall_pixel_ratio"],
            })
    n_old = next_id - 1
    print(f"Copied {n_old} existing entries (renumbered to IDs 1..{n_old})")

    # 2. Load preview stats for the new entries
    preview_stats = json.loads((PREVIEW_ROOT / "stats.json").read_text())
    candidates = [
        s for s in preview_stats
        if s["status"] == "ok" and s["stem"] not in EXCLUDE_STEMS
    ]
    n_excluded = len([s for s in preview_stats if s["stem"] in EXCLUDE_STEMS or s["status"] != "ok"])
    print(f"New candidates after exclusions: {len(candidates)} (excluded: {n_excluded})")

    # 3. Stratified split by size_bin (deterministic with seed)
    by_bin: dict[str, list[dict]] = {"small": [], "medium": [], "large": []}
    for s in candidates:
        by_bin[s["size_bin"]].append(s)
    rng = random.Random(SEED)
    assigned: dict[str, list[dict]] = {"train": [], "val": [], "test": []}
    for bin_name in ("small", "medium", "large"):
        items = sorted(by_bin[bin_name], key=lambda s: s["stem"])
        rng.shuffle(items)
        n = len(items)
        n_train = round(n * SPLITS_RATIO["train"])
        n_val = round(n * SPLITS_RATIO["val"])
        n_test = n - n_train - n_val
        assigned["train"].extend(items[:n_train])
        assigned["val"].extend(items[n_train:n_train + n_val])
        assigned["test"].extend(items[n_train + n_val:])
        print(f"  {bin_name:6s}: n={n:3d} → train={n_train} val={n_val} test={n_test}")

    # 4. Copy new img/mask with continued globally-unique IDs
    for split in ("train", "val", "test"):
        for s in assigned[split]:
            new_id = next_id
            next_id += 1
            new_img = f"img_{new_id:04d}.png"
            new_mask = f"mask_{new_id:04d}.png"
            shutil.copy2(PREVIEW_ROOT / "images" / f"{s['stem']}.png",
                         OUT_ROOT / split / new_img)
            shutil.copy2(PREVIEW_ROOT / "masks" / f"{s['stem']}.png",
                         OUT_ROOT / split / new_mask)
            new_splits[split].append({
                "id": new_id,
                "img": new_img,
                "mask": new_mask,
                "source_dxf": f"{s['stem']}.dxf",
                "source_set": "plans_dxf_dwglab",
                "n_wall_segments": s["n_wall_segments"],
                "n_context_segments": s["n_context_segments"],
                "size_bin": s["size_bin"],
                "wall_pixel_ratio": s["wall_pixel_ratio"],
            })

    # Sort each split by id
    for split in new_splits:
        new_splits[split].sort(key=lambda e: e["id"])

    # 5. Write meta.json
    out_meta = {
        "size": old_meta["size"],
        "seed": SEED,
        "stroke_wall": old_meta["stroke_wall"],
        "stroke_context": old_meta["stroke_context"],
        "build_notes": (
            "v2 = anciens dwg_walls (50 paires, splits préservés) "
            "+ 99 nouveaux dwg_walls_dwglab_preview (stratifiés 70/15/15 "
            "par size_bin avec seed=42). Renumérotation globale 1..149 "
            "pour éviter les collisions img_NNNN.png entre splits."
        ),
        "exclusions": sorted(EXCLUDE_STEMS),
        "splits": new_splits,
    }
    (OUT_ROOT / "meta.json").write_text(json.dumps(out_meta, indent=2))

    # 6. Bilan
    totals = {s: len(new_splits[s]) for s in ("train", "val", "test")}
    grand_total = sum(totals.values())
    print(f"\n=== Bilan dwg_walls_v2 ===")
    print(f"Total : {grand_total} paires (vs 50 en v1)")
    for s in ("train", "val", "test"):
        print(f"  {s:5s}: {totals[s]}")
    print(f"\nOutput : {OUT_ROOT}")


if __name__ == "__main__":
    main()
