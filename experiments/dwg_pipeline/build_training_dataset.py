"""
Build wall-only training dataset depuis les DXF des plans curés.

Pour chaque DXF :
1. Lire toutes les entités du modelspace
2. Identifier les segments des layers classifiés "wall"
3. Calculer bbox tight des murs (élimine élévations / cartouches via crop)
4. Rendu RGB image 1024×1024 : style PDF artisan (murs noirs épais + contexte gris fin)
5. Rendu masque 1024×1024 : murs blancs sur fond noir (binaire 0/255)
6. Split stratifié 70/15/15 par taille (small/medium/large) avec seed fixe
7. Output : data/processed/dwg_walls/{train,val,test}/img_NNNN.png + mask_NNNN.png
8. Meta.json : mapping img_NNNN ↔ plan source + split

Run :
    .venv/bin/python experiments/dwg_pipeline/build_training_dataset.py
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from pathlib import Path
from typing import Iterable

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from PIL import Image
import ezdxf

# Reuse les heuristiques de classification de run_analysis
sys.path.insert(0, str(Path(__file__).parent))
from run_analysis import (  # noqa: E402
    classify_layer, _entity_segments,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DXF_DIR = PROJECT_ROOT / "data" / "raw" / "plans_dxf"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "dwg_walls"
REPORTS_DIR = PROJECT_ROOT / "experiments" / "dwg_pipeline" / "outputs"

OUTPUT_SIZE = 1024
SEED = 42

# Rendu : épaisseurs de trait visant à mimer le style PDF artisan FR
STROKE_WALL = 3.0     # mur en noir épais
STROKE_CONTEXT = 0.4  # mobilier / cotes en gris fin
COLOR_WALL = "black"
COLOR_CONTEXT = "#bbbbbb"


def _walk_entities(msp, max_insert_depth: int = 5):
    """Itère sur les entités du modelspace en explodant récursivement les INSERT
    (références de BLOCK). Nécessaire pour les fichiers Archicad/Revit où la
    géométrie réelle vit dans des blocs nommés (CASANOVA-…|Murs - Maconnerie),
    le modelspace ne contenant que des INSERT vers ces blocs.

    `virtual_entities()` d'ezdxf applique automatiquement les transforms
    d'insertion (translation, rotation, scale).

    Yield (entity, effective_layer) tuples — pour les entités sur layer "0"
    dans un block, applique la convention AutoCAD/Archicad : layer héritée de
    l'INSERT parent (chain le long de l'arborescence imbriquée).
    """
    def _emit(entity, depth, parent_layer):
        if entity.dxftype() == "INSERT":
            if depth >= max_insert_depth:
                return
            insert_layer = entity.dxf.layer
            try:
                virt_iter = entity.virtual_entities()
            except Exception:
                return
            for sub in virt_iter:
                yield from _emit(sub, depth + 1, insert_layer)
        else:
            # Convention AutoCAD : layer "0" dans un block hérite de l'INSERT parent
            effective = entity.dxf.layer
            if effective == "0" and parent_layer is not None:
                effective = parent_layer
            yield entity, effective

    for entity in msp:
        yield from _emit(entity, 0, None)


def extract_segments_by_category(dxf_path: Path) -> tuple[list, list]:
    """Extrait les segments du DXF, séparés en (wall_segs, context_segs).

    Walke récursivement dans les INSERT/BLOCK (cf `_walk_entities`) — couvre
    aussi bien les DXF "tout-modelspace" (AutoCAD plat) que les DXF "tout-blocs"
    (Archicad/Revit).
    """
    doc = ezdxf.readfile(str(dxf_path))
    msp = doc.modelspace()

    wall_layers = {
        layer.dxf.name for layer in doc.layers
        if classify_layer(layer.dxf.name) == "wall"
    }

    walls: list = []
    context: list = []
    for entity, effective_layer in _walk_entities(msp):
        segs = _entity_segments(entity)
        if not segs:
            continue
        if effective_layer in wall_layers:
            walls.extend(segs)
        else:
            # Ignore le mobilier/cotes très volumineux : on garde mais en gris pâle.
            # Les hatches/textes sont déjà ignorés par _entity_segments (renvoie []).
            context.extend(segs)

    return walls, context


def bbox_from_segments(segments: list) -> tuple[float, float, float, float] | None:
    """Retourne (xmin, ymin, xmax, ymax) à partir d'une liste de segments."""
    if not segments:
        return None
    xs = []
    ys = []
    for (p1, p2) in segments:
        xs.extend([p1[0], p2[0]])
        ys.extend([p1[1], p2[1]])
    return (min(xs), min(ys), max(xs), max(ys))


def crop_segments_to_bbox(
    segments: list, bbox: tuple[float, float, float, float],
    margin_factor: float = 1.1,
) -> list:
    """Retourne les segments dont au moins un point est dans la bbox étendue."""
    xmin, ymin, xmax, ymax = bbox
    w, h = xmax - xmin, ymax - ymin
    pad = max(w, h) * (margin_factor - 1) / 2
    xmin_p = xmin - pad
    xmax_p = xmax + pad
    ymin_p = ymin - pad
    ymax_p = ymax + pad
    out = []
    for (p1, p2) in segments:
        if (xmin_p <= p1[0] <= xmax_p and ymin_p <= p1[1] <= ymax_p) \
           or (xmin_p <= p2[0] <= xmax_p and ymin_p <= p2[1] <= ymax_p):
            out.append((p1, p2))
    return out


def render_pair(
    wall_segments: list,
    context_segments: list,
    bbox: tuple[float, float, float, float],
    out_size: int = OUTPUT_SIZE,
) -> tuple[np.ndarray, np.ndarray]:
    """Génère (image_rgb, mask_binary) carrés out_size×out_size.

    L'image carrée centre la bbox des murs, avec padding pour préserver
    l'aspect-ratio des plans (typiquement plus large que haut).
    """
    xmin, ymin, xmax, ymax = bbox
    w, h = xmax - xmin, ymax - ymin
    side = max(w, h) * 1.05  # 5% de padding
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    extent = (cx - side / 2, cx + side / 2, cy - side / 2, cy + side / 2)

    # --- IMAGE : contexte gris + murs noirs ---
    fig = plt.figure(figsize=(out_size / 100, out_size / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("white")
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])

    if context_segments:
        lc_ctx = LineCollection(
            context_segments, colors=COLOR_CONTEXT,
            linewidths=STROKE_CONTEXT, antialiased=True,
        )
        ax.add_collection(lc_ctx)
    if wall_segments:
        lc_walls = LineCollection(
            wall_segments, colors=COLOR_WALL,
            linewidths=STROKE_WALL, antialiased=True,
        )
        ax.add_collection(lc_walls)

    fig.canvas.draw()
    image = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)

    # --- MASK : murs blanc / fond noir ---
    # ax.axis("off") cache le patch de l'axes, donc on doit teinter le
    # fond du figure (sinon les pixels lus via buffer_rgba sont blancs).
    fig = plt.figure(figsize=(out_size / 100, out_size / 100), dpi=100)
    fig.patch.set_facecolor("black")
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])

    if wall_segments:
        lc_mask = LineCollection(
            wall_segments, colors="white",
            linewidths=STROKE_WALL, antialiased=False,
        )
        ax.add_collection(lc_mask)

    fig.canvas.draw()
    mask_rgba = np.asarray(fig.canvas.buffer_rgba())
    plt.close(fig)
    # Binarise sur le canal rouge (255 = mur, 0 = fond)
    mask = (mask_rgba[..., 0] > 127).astype(np.uint8) * 255

    # S'assure que la taille finale est exactement out_size×out_size
    # (matplotlib peut rendre un poil différent à cause du dpi/figsize rounding)
    if image.shape[:2] != (out_size, out_size):
        image = np.asarray(
            Image.fromarray(image).resize((out_size, out_size), Image.LANCZOS)
        )
    if mask.shape[:2] != (out_size, out_size):
        mask = np.asarray(
            Image.fromarray(mask).resize((out_size, out_size), Image.NEAREST)
        )

    return image, mask


def size_bin(n_wall_segments: int) -> str:
    """Catégorise la taille du plan en small/medium/large pour split stratifié."""
    if n_wall_segments < 200:
        return "small"
    if n_wall_segments < 800:
        return "medium"
    return "large"


def stratified_split(
    plans: list[dict], train_ratio: float = 0.70, val_ratio: float = 0.15,
    seed: int = SEED,
) -> dict[str, list[dict]]:
    """Split stratifié par bin de taille avec seed fixe."""
    rng = random.Random(seed)
    by_bin: dict[str, list[dict]] = {}
    for p in plans:
        by_bin.setdefault(p["size_bin"], []).append(p)

    splits = {"train": [], "val": [], "test": []}
    for bin_name, items in by_bin.items():
        rng.shuffle(items)
        n = len(items)
        n_train = max(1, int(round(n * train_ratio)))
        n_val = max(1, int(round(n * val_ratio))) if n - n_train > 1 else 0
        n_test = n - n_train - n_val
        if n_test < 0:
            n_test = 0
            n_val = n - n_train
        splits["train"].extend(items[:n_train])
        splits["val"].extend(items[n_train:n_train + n_val])
        splits["test"].extend(items[n_train + n_val:])

    return splits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dxf-dir", default=str(DEFAULT_DXF_DIR))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--reports-dir", default=str(REPORTS_DIR))
    parser.add_argument("--size", type=int, default=OUTPUT_SIZE)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Liste seulement les plans à traiter sans rien rendre",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Écrase le contenu de --out-dir s'il existe",
    )
    args = parser.parse_args()

    dxf_dir = Path(args.dxf_dir)
    out_dir = Path(args.out_dir)
    reports_dir = Path(args.reports_dir)

    if out_dir.exists():
        if args.overwrite:
            shutil.rmtree(out_dir)
        else:
            print(f"ERROR: {out_dir} existe déjà. Utilise --overwrite.")
            sys.exit(1)

    # Construit la liste des plans curés (= ceux qui ont un report.json)
    plan_stems = sorted(p.name for p in reports_dir.iterdir() if p.is_dir())
    print(f"Plans curés : {len(plan_stems)}")

    plans = []
    print("\n=== Extraction des segments + bbox ===")
    for i, stem in enumerate(plan_stems, 1):
        dxf_path = dxf_dir / f"{stem}.dxf"
        if not dxf_path.exists():
            print(f"  [{i:3d}/{len(plan_stems)}] {stem}: MISSING DXF, skip")
            continue
        try:
            walls, context = extract_segments_by_category(dxf_path)
        except Exception as e:
            print(f"  [{i:3d}/{len(plan_stems)}] {stem}: extract failed ({type(e).__name__})")
            continue
        if not walls:
            print(f"  [{i:3d}/{len(plan_stems)}] {stem}: 0 wall segments, skip")
            continue
        # Seuil min : exclure les plans avec parsing dégénéré (1-10 segments)
        if len(walls) < 20:
            print(f"  [{i:3d}/{len(plan_stems)}] {stem}: {len(walls)} walls < 20, skip (likely degenerate parsing)")
            continue
        wall_bbox = bbox_from_segments(walls)
        # Crop context aux 110% de la bbox murs (élimine élévations à côté)
        context_cropped = crop_segments_to_bbox(context, wall_bbox, 1.10)
        plans.append({
            "stem": stem,
            "n_walls": len(walls),
            "n_context": len(context_cropped),
            "wall_bbox": wall_bbox,
            "size_bin": size_bin(len(walls)),
            "walls": walls,
            "context": context_cropped,
        })
        print(f"  [{i:3d}/{len(plan_stems)}] {stem}: {len(walls)} walls, {len(context_cropped)} context, bin={size_bin(len(walls))}")

    if not plans:
        print("Aucun plan valide.")
        sys.exit(1)

    # Stats par bin
    by_bin: dict[str, int] = {}
    for p in plans:
        by_bin[p["size_bin"]] = by_bin.get(p["size_bin"], 0) + 1
    print(f"\nDistribution par taille : {by_bin}")

    # Split stratifié
    splits = stratified_split(plans, train_ratio=0.70, val_ratio=0.15, seed=SEED)
    print("\n=== Split stratifié 70/15/15 ===")
    for name, items in splits.items():
        bins_count = {}
        for p in items:
            bins_count[p["size_bin"]] = bins_count.get(p["size_bin"], 0) + 1
        print(f"  {name:6s}: {len(items):3d} plans  {bins_count}")

    if args.dry_run:
        print("\n[dry-run] arrêt avant rendu.")
        return

    # Rendu + sauvegarde
    out_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {
        "size": args.size,
        "seed": SEED,
        "stroke_wall": STROKE_WALL,
        "stroke_context": STROKE_CONTEXT,
        "splits": {},
    }

    print(f"\n=== Rendu image+mask à {args.size}×{args.size} ===")
    for split_name, items in splits.items():
        split_dir = out_dir / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        meta["splits"][split_name] = []
        for idx, p in enumerate(items, 1):
            img_name = f"img_{idx:04d}.png"
            mask_name = f"mask_{idx:04d}.png"
            try:
                image, mask = render_pair(
                    p["walls"], p["context"], p["wall_bbox"], out_size=args.size,
                )
                Image.fromarray(image).save(split_dir / img_name)
                Image.fromarray(mask).save(split_dir / mask_name)
                # Petit check : ratio de pixels mur dans le masque
                wall_pixel_ratio = float((mask > 127).sum()) / mask.size
                meta["splits"][split_name].append({
                    "id": idx,
                    "img": img_name,
                    "mask": mask_name,
                    "source_dxf": f"{p['stem']}.dxf",
                    "n_wall_segments": p["n_walls"],
                    "n_context_segments": p["n_context"],
                    "size_bin": p["size_bin"],
                    "wall_pixel_ratio": round(wall_pixel_ratio, 4),
                })
                print(f"  [{split_name}/{idx:3d}/{len(items)}] {p['stem'][:55]:55s} walls={p['n_walls']:4d} ratio={wall_pixel_ratio:.3f}")
            except Exception as e:
                print(f"  [{split_name}/{idx:3d}/{len(items)}] {p['stem']}: render FAILED ({type(e).__name__}: {e})")

    # Save meta.json (sans les listes de segments — trop volumineux)
    with (out_dir / "meta.json").open("w") as f:
        json.dump(meta, f, indent=2, default=str)

    # Synthèse finale
    print("\n=== Synthèse ===")
    for split_name in ("train", "val", "test"):
        n = len(meta["splits"][split_name])
        ratios = [s["wall_pixel_ratio"] for s in meta["splits"][split_name]]
        if ratios:
            print(f"  {split_name:6s}: {n:3d} pairs  wall_pixel_ratio mean={np.mean(ratios):.3f} min={min(ratios):.3f} max={max(ratios):.3f}")

    print(f"\nDataset prêt : {out_dir}")
    print(f"meta.json    : {out_dir / 'meta.json'}")


if __name__ == "__main__":
    main()
