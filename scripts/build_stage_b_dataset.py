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
    ap.add_argument("--cc_root", required=True,
                    help="CubiCasa panoptic root")
    ap.add_argument("--out", required=True,
                    help="Output dir for combined Stage B dataset")
    args = ap.parse_args()

    fr_root = Path(args.fr_root).resolve()
    cc_root = Path(args.cc_root).resolve()
    out = Path(args.out).resolve()

    for root in (fr_root, cc_root):
        if not (root / "splits.json").is_file():
            raise SystemExit(f"splits.json not found in {root}")

    fr_splits = json.loads((fr_root / "splits.json").read_text())
    cc_splits = json.loads((cc_root / "splits.json").read_text())

    print(f"FR  source: train={len(fr_splits['train'])} "
          f"val={len(fr_splits['val'])} test={len(fr_splits['test'])}")
    print(f"CC  source: train={len(cc_splits['train'])} "
          f"val={len(cc_splits['val'])} test={len(cc_splits['test'])}")

    out.mkdir(parents=True, exist_ok=True)

    splits_out: dict[str, list[str]] = {
        "train": [], "val": [], "test_fr": [], "test_cc": [],
    }
    origins: dict[str, str] = {}

    # --- train: FR train ∪ CC train ---
    fr_train = _symlink_split(fr_root, "train", out, "train",
                              fr_splits["train"], "fr")
    cc_train = _symlink_split(cc_root, "train", out, "train",
                              cc_splits["train"], "cc")
    splits_out["train"] = fr_train + cc_train
    for sid in fr_train: origins[sid] = "fr"
    for sid in cc_train: origins[sid] = "cc"

    # --- val: FR val ∪ CC val (mixed, used for early stopping) ---
    fr_val = _symlink_split(fr_root, "val", out, "val",
                            fr_splits["val"], "fr")
    cc_val = _symlink_split(cc_root, "val", out, "val",
                            cc_splits["val"], "cc")
    splits_out["val"] = fr_val + cc_val
    for sid in fr_val: origins[sid] = "fr"
    for sid in cc_val: origins[sid] = "cc"

    # --- test_fr: FR test only (MVP metric) ---
    fr_test = _symlink_split(fr_root, "test", out, "test_fr",
                             fr_splits["test"], "fr")
    splits_out["test_fr"] = fr_test
    for sid in fr_test: origins[sid] = "fr"

    # --- test_cc: CC test only (sanity check) ---
    cc_test = _symlink_split(cc_root, "test", out, "test_cc",
                             cc_splits["test"], "cc")
    splits_out["test_cc"] = cc_test
    for sid in cc_test: origins[sid] = "cc"

    # Write splits + origins
    (out / "splits.json").write_text(json.dumps(splits_out, indent=2))
    (out / "sample_origins.json").write_text(json.dumps(origins, indent=2))

    # dataset.yaml
    yaml_text = (
        f"path: {out.as_posix()}\n"
        f"num_classes: {NUM_CLASSES}\n"
        "names:\n" + "\n".join(f"  - {n}" for n in CLASS_NAMES) + "\n"
        "splits: [train, val, test_fr, test_cc]\n"
        "source: FR_annotated + CubiCasa5K (Stage B combined)\n"
        "oversampling:\n"
        "  fr: 8\n"
        "  cc: 1\n"
    )
    (out / "dataset.yaml").write_text(yaml_text)

    n_train_fr = sum(1 for s in splits_out["train"] if origins[s] == "fr")
    n_train_cc = sum(1 for s in splits_out["train"] if origins[s] == "cc")
    fr_contribution = n_train_fr * 8 / (n_train_fr * 8 + n_train_cc) * 100

    print(f"\n✓ Stage B dataset built at {out}")
    print(f"  train    : {len(splits_out['train'])} "
          f"(fr={n_train_fr}, cc={n_train_cc}) "
          f"→ FR contribution after ×8 oversampling: {fr_contribution:.1f}%")
    print(f"  val      : {len(splits_out['val'])} "
          f"(fr={sum(1 for s in splits_out['val'] if origins[s] == 'fr')}, "
          f"cc={sum(1 for s in splits_out['val'] if origins[s] == 'cc')})")
    print(f"  test_fr  : {len(splits_out['test_fr'])} (MVP metric)")
    print(f"  test_cc  : {len(splits_out['test_cc'])} (sanity check)")


if __name__ == "__main__":
    main()
