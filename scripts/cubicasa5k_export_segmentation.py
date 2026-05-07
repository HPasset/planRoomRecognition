"""Export CubiCasa5K to panoptic segmentation dataset.

Output structure:
  <out>/
    images/{train,val,test}/<sample_id>.png
    semantic/{train,val,test}/<sample_id>.png   # uint8 mask, class_id per pixel
    instance/{train,val,test}/<sample_id>.png   # uint16 mask, instance id per pixel
    splits.json
    dataset.yaml
"""
from __future__ import annotations
import argparse
import json
import random
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# Ensure project root is on sys.path so that `src.*` and sibling scripts resolve
# regardless of how/where the script is invoked.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
# Ensure scripts/ dir is on path for the sibling import below
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import cv2
import numpy as np
from tqdm import tqdm

from src.segmentation.classes import CLASS_NAMES
from src.segmentation.cubicasa_export import (
    extract_room_polygons, rasterize_panoptic, RoomPolygon, _get_viewbox,
)

# Reuse the YOLO export's image-selection logic (proven robust)
from cubicasa5k_export_yolo import select_best_image  # noqa: E402


def _scale_polygons(polygons: list[RoomPolygon], sx: float, sy: float) -> list[RoomPolygon]:
    out = []
    for p in polygons:
        scaled = p.points.copy()
        scaled[:, 0] *= sx
        scaled[:, 1] *= sy
        out.append(RoomPolygon(class_id=p.class_id, points=scaled))
    return out


def export_one(svg_path: Path, out_dir: Path, split: str,
               max_aspect_diff: float) -> tuple[bool, str]:
    """Export one CubiCasa sample. Returns (success, reason_if_skipped)."""
    folder = svg_path.parent
    sample_id = folder.name

    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
        _, _, svg_w, svg_h = _get_viewbox(root)
    except Exception as e:
        return False, f"viewbox_err:{e}"
    if svg_w <= 0 or svg_h <= 0:
        return False, "viewbox_zero"

    res = select_best_image(folder, svg_w, svg_h, floor_num=1)
    if res is None:
        return False, "no_image"
    img_path, aspect_diff = res
    if aspect_diff > max_aspect_diff:
        return False, f"aspect_diff:{aspect_diff:.2f}"

    img = cv2.imread(str(img_path))
    if img is None:
        return False, "img_unreadable"
    img_h, img_w = img.shape[:2]

    polygons = extract_room_polygons(svg_path)
    if not polygons:
        return False, "no_polygons"

    sx = img_w / svg_w
    sy = img_h / svg_h
    polygons_scaled = _scale_polygons(polygons, sx, sy)

    sem, inst = rasterize_panoptic(polygons_scaled, image_size=(img_w, img_h))

    # Persist
    img_out = out_dir / "images" / split / f"{sample_id}.png"
    sem_out = out_dir / "semantic" / split / f"{sample_id}.png"
    inst_out = out_dir / "instance" / split / f"{sample_id}.png"

    cv2.imwrite(str(img_out), img)
    cv2.imwrite(str(sem_out), sem)
    # Save instance as uint16 PNG (room counts in CubiCasa stay <65535)
    inst_u16 = inst.astype(np.uint16)
    cv2.imwrite(str(inst_out), inst_u16)

    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw/cubicasa5k")
    ap.add_argument("--out", default="data/processed/cubicasa_panoptic")
    ap.add_argument("--train_ratio", type=float, default=0.80)
    ap.add_argument("--val_ratio", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max_aspect_diff", type=float, default=0.20)
    args = ap.parse_args()

    out = Path(args.out).resolve()
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (out / sub / split).mkdir(parents=True, exist_ok=True)

    svgs = sorted(Path(args.root).rglob("model.svg"))
    if not svgs:
        raise SystemExit(f"No model.svg under {args.root}")

    rng = random.Random(args.seed)
    rng.shuffle(svgs)

    n_train = int(len(svgs) * args.train_ratio)
    n_val = int(len(svgs) * args.val_ratio)
    train_svgs = svgs[:n_train]
    val_svgs = svgs[n_train:n_train + n_val]
    test_svgs = svgs[n_train + n_val:]

    splits = {"train": train_svgs, "val": val_svgs, "test": test_svgs}
    splits_log = {"train": [], "val": [], "test": []}
    skip_reasons: dict[str, int] = {}

    for split_name, paths in splits.items():
        for svg in tqdm(paths, desc=f"export {split_name}"):
            ok, reason = export_one(svg, out, split_name, args.max_aspect_diff)
            if ok:
                splits_log[split_name].append(svg.parent.name)
            else:
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1

    (out / "splits.json").write_text(json.dumps(splits_log, indent=2))

    yaml_text = (
        f"path: {out.as_posix()}\n"
        f"num_classes: {len(CLASS_NAMES)}\n"
        "names:\n" + "\n".join(f"  - {n}" for n in CLASS_NAMES) + "\n"
        "splits: [train, val, test]\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    total = sum(len(v) for v in splits_log.values())
    print(f"Exported {total} samples to {out}")
    print(f"  train={len(splits_log['train'])} "
          f"val={len(splits_log['val'])} test={len(splits_log['test'])}")
    print(f"Skipped: {dict(sorted(skip_reasons.items()))}")


if __name__ == "__main__":
    main()
