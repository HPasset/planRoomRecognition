"""Combine FR panoptic + CubiCasa panoptic into a single Stage B dataset.

Uses symlinks (no copy) to build:

    <out>/
      images/{train,val,test_fr,test_cc}/<prefix>_<id>.png   prefix = fr|cc
      semantic/{train,val,test_fr,test_cc}/<prefix>_<id>.png
      instance/{train,val,test_fr,test_cc}/<prefix>_<id>.png
      splits.json           {"train":[...], "val":[...], "test_fr":[...], "test_cc":[...]}
      sample_origins.json   { "fr_<id>": "fr", "cc_<id>": "cc", ... }
      dataset.yaml

The trainer reads `sample_origins.json` to build a WeightedRandomSampler
(FR ×8, CC ×1) for the train split.

Usage:
    python scripts/build_stage_b_dataset.py \\
        --fr_root   data/processed/fr_panoptic \\
        --cc_root   data/processed/cubicasa_panoptic \\
        --out       data/processed/stage_b_combined
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES


SUB_DIRS = ("images", "semantic", "instance")


def _symlink_split(
    src_root: Path,
    src_split: str,
    dst_root: Path,
    dst_split: str,
    sample_ids: list[str],
    prefix: str,
) -> list[str]:
    """Create symlinks for one (source_split → dest_split) batch.

    Returns the list of new ids (prefixed).
    """
    new_ids: list[str] = []
    for sid in sample_ids:
        new_id = f"{prefix}_{sid}"
        for sub in SUB_DIRS:
            src = (src_root / sub / src_split / f"{sid}.png").resolve()
            dst_dir = dst_root / sub / dst_split
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = dst_dir / f"{new_id}.png"
            if not src.exists():
                # FR may not have all 3 (e.g. no inst if room-less), but our
                # cvat_to_panoptic always writes all 3. CC same. Skip if missing.
                print(f"  ⚠ Missing source: {src} — skipping {sid}")
                break
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(src)
        else:
            new_ids.append(new_id)
    return new_ids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fr_root", required=True,
                    help="FR panoptic root (output of cvat_to_panoptic.py)")
    ap.add_argument("--aux_root", required=True,
                    help="Auxiliary bulk panoptic root (MSD, CubiCasa, …)")
    ap.add_argument("--aux_prefix", default="cc",
                    help="id prefix + origin tag for the aux source (e.g. 'msd', 'cc')")
    ap.add_argument("--aux_oversample", type=int, default=1,
                    help="Oversample weight for aux in dataset.yaml (fr is ×8)")
    ap.add_argument("--out", required=True,
                    help="Output dir for combined Stage B dataset")
    args = ap.parse_args()

    aux = args.aux_prefix
    fr_root = Path(args.fr_root).resolve()
    aux_root = Path(args.aux_root).resolve()
    out = Path(args.out).resolve()
    test_aux = f"test_{aux}"

    for root in (fr_root, aux_root):
        if not (root / "splits.json").is_file():
            raise SystemExit(f"splits.json not found in {root}")

    fr_splits = json.loads((fr_root / "splits.json").read_text())
    aux_splits = json.loads((aux_root / "splits.json").read_text())

    print(f"FR   source: train={len(fr_splits['train'])} "
          f"val={len(fr_splits['val'])} test={len(fr_splits['test'])}")
    print(f"{aux.upper():<4} source: train={len(aux_splits['train'])} "
          f"val={len(aux_splits['val'])} test={len(aux_splits['test'])}")

    out.mkdir(parents=True, exist_ok=True)

    splits_out: dict[str, list[str]] = {
        "train": [], "val": [], "test_fr": [], test_aux: [],
    }
    origins: dict[str, str] = {}

    # --- train: FR train ∪ AUX train ---
    fr_train = _symlink_split(fr_root, "train", out, "train",
                              fr_splits["train"], "fr")
    aux_train = _symlink_split(aux_root, "train", out, "train",
                               aux_splits["train"], aux)
    splits_out["train"] = fr_train + aux_train
    for sid in fr_train: origins[sid] = "fr"
    for sid in aux_train: origins[sid] = aux

    # --- val: FR val ∪ AUX val (mixed, used for early stopping) ---
    fr_val = _symlink_split(fr_root, "val", out, "val",
                            fr_splits["val"], "fr")
    aux_val = _symlink_split(aux_root, "val", out, "val",
                             aux_splits["val"], aux)
    splits_out["val"] = fr_val + aux_val
    for sid in fr_val: origins[sid] = "fr"
    for sid in aux_val: origins[sid] = aux

    # --- test_fr: FR test only (MVP metric, frozen hold-out) ---
    fr_test = _symlink_split(fr_root, "test", out, "test_fr",
                             fr_splits["test"], "fr")
    splits_out["test_fr"] = fr_test
    for sid in fr_test: origins[sid] = "fr"

    # --- test_<aux>: AUX test only (sanity check) ---
    aux_test = _symlink_split(aux_root, "test", out, test_aux,
                              aux_splits["test"], aux)
    splits_out[test_aux] = aux_test
    for sid in aux_test: origins[sid] = aux

    # Write splits + origins
    (out / "splits.json").write_text(json.dumps(splits_out, indent=2))
    (out / "sample_origins.json").write_text(json.dumps(origins, indent=2))

    # dataset.yaml
    yaml_text = (
        f"path: {out.as_posix()}\n"
        f"num_classes: {NUM_CLASSES}\n"
        "names:\n" + "\n".join(f"  - {n}" for n in CLASS_NAMES) + "\n"
        f"splits: [train, val, test_fr, {test_aux}]\n"
        f"source: FR_annotated + {aux.upper()} (Stage B combined)\n"
        "oversampling:\n"
        "  fr: 8\n"
        f"  {aux}: {args.aux_oversample}\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    n_train_fr = sum(1 for s in splits_out["train"] if origins[s] == "fr")
    n_train_aux = sum(1 for s in splits_out["train"] if origins[s] == aux)
    denom = n_train_fr * 8 + n_train_aux * args.aux_oversample
    fr_contribution = n_train_fr * 8 / denom * 100 if denom else 0.0

    print(f"\n✓ Stage B dataset built at {out}")
    print(f"  train    : {len(splits_out['train'])} "
          f"(fr={n_train_fr}, {aux}={n_train_aux}) "
          f"→ FR contribution (fr×8 / {aux}×{args.aux_oversample}): {fr_contribution:.1f}%")
    print(f"  val      : {len(splits_out['val'])} "
          f"(fr={sum(1 for s in splits_out['val'] if origins[s] == 'fr')}, "
          f"{aux}={sum(1 for s in splits_out['val'] if origins[s] == aux)})")
    print(f"  test_fr  : {len(splits_out['test_fr'])} (MVP metric)")
    print(f"  {test_aux:<8}: {len(splits_out[test_aux])} (sanity check)")


if __name__ == "__main__":
    main()
