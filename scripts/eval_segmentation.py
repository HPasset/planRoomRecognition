"""Evaluate one or more segmentation checkpoints on specified splits.

Designed to compare Stage A best.pt vs Stage B best.pt on test_fr (MVP target)
and test_cc (sanity check / non-regression on CubiCasa).

Usage (single checkpoint, both splits):
    python scripts/eval_segmentation.py \\
        --checkpoint runs/segmentation/stage_b_finetune_v1/checkpoints/best.pt \\
        --dataset_root data/processed/stage_b_combined \\
        --splits test_fr test_cc

Usage (compare 2 checkpoints side-by-side):
    python scripts/eval_segmentation.py \\
        --checkpoints \\
            stage_a=runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \\
            stage_b=runs/segmentation/stage_b_finetune_v1/checkpoints/best.pt \\
        --dataset_root data/processed/stage_b_combined \\
        --splits test_fr test_cc

Use --device cpu to avoid contention with a running training (slower ×5 but safe).
"""
from __future__ import annotations
import os
# MUST be set before torch import (Mask2Former needs grid_sampler_2d fallback)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np
import torch
from torch.utils.data import DataLoader
from tqdm import tqdm

from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES
from src.segmentation.dataset import PanopticDataset
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.model import build_model, get_processor


def _select_device(name: str) -> torch.device:
    if name == "auto":
        name = "mps" if torch.backends.mps.is_available() else "cpu"
    return torch.device(name)


def _parse_checkpoints(args) -> dict[str, Path]:
    """Returns ordered dict {label: ckpt_path}."""
    out: dict[str, Path] = {}
    if args.checkpoint:
        label = Path(args.checkpoint).parent.parent.name  # e.g. stage_b_finetune_v1
        out[label] = Path(args.checkpoint)
    for item in args.checkpoints or []:
        if "=" not in item:
            raise SystemExit(f"--checkpoints item must be label=path, got: {item}")
        label, path = item.split("=", 1)
        out[label] = Path(path)
    if not out:
        raise SystemExit("Provide --checkpoint OR --checkpoints label=path ...")
    return out


def evaluate_split(model, processor, ds, device) -> tuple[float, np.ndarray]:
    model.eval()
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=0)
    ious: list[np.ndarray] = []
    for batch in tqdm(loader, desc=f"  {ds.split}", leave=False):
        pixel_values = batch["pixel_values"].to(device)
        with torch.no_grad():
            out = model(pixel_values=pixel_values)
        sem_pred = processor.post_process_semantic_segmentation(
            out, target_sizes=[batch["semantic"].shape[-2:]],
        )[0].cpu().numpy()
        sem_gt = batch["semantic"][0].numpy()
        ious.append(compute_iou_per_class(sem_pred, sem_gt, NUM_CLASSES))
    ious = np.stack(ious)
    per_class = np.nanmean(ious, axis=0)
    miou = compute_miou(per_class)
    return miou, per_class


def evaluate_checkpoint(
    ckpt_path: Path, dataset_root: str, splits: list[str],
    image_size: int, backbone: str, device: torch.device,
) -> dict[str, tuple[float, np.ndarray]]:
    print(f"\n>>> Loading {ckpt_path}")
    model = build_model(backbone=backbone, num_classes=NUM_CLASSES).to(device)
    ckpt = load_checkpoint(ckpt_path, map_location=str(device))
    model.load_state_dict(ckpt["model_state_dict"])
    print(f"    epoch={ckpt.get('epoch', '?')}  "
          f"prior_best_metric={ckpt.get('best_metric', '?'):.4f}")
    processor = get_processor(backbone)

    results: dict[str, tuple[float, np.ndarray]] = {}
    for split in splits:
        ds = PanopticDataset(dataset_root, split, image_size, train=False)
        print(f"  Evaluating {split} ({len(ds)} samples)...")
        results[split] = evaluate_split(model, processor, ds, device)
    return results


def print_results_table(
    all_results: dict[str, dict[str, tuple[float, np.ndarray]]],
    splits: list[str],
):
    """all_results[ckpt_label][split] = (miou, per_class)."""
    ckpt_labels = list(all_results.keys())
    # Column header: <split>/<ckpt> for each combination
    columns = [(s, c) for s in splits for c in ckpt_labels]
    col_w = 13
    name_w = 14

    print(f"\n{'='*(name_w + 3 + (col_w + 3) * len(columns))}")
    # Header row 1: split groups
    header1 = " " * (name_w + 2)
    for s in splits:
        cell = s.center(len(ckpt_labels) * (col_w + 3) - 3)
        header1 += " | " + cell
    print(header1)
    # Header row 2: ckpt labels
    header2 = f"{'Class':<{name_w}}"
    for split, ckpt in columns:
        header2 += " | " + ckpt[:col_w].center(col_w)
    print(header2)
    sep = "-" * name_w + "-+-" + "-+-".join("-" * col_w for _ in columns)
    print(sep)

    for cid, name in enumerate(CLASS_NAMES):
        row = f"{cid} {name:<{name_w - 2}}"
        for split, ckpt in columns:
            v = all_results[ckpt][split][1][cid]
            cell = f"{v:.3f}" if not np.isnan(v) else "n/a"
            # Highlight Δ vs first ckpt (baseline)
            if ckpt != ckpt_labels[0]:
                baseline = all_results[ckpt_labels[0]][split][1][cid]
                if not np.isnan(v) and not np.isnan(baseline):
                    delta = v - baseline
                    cell = f"{v:.3f} ({delta:+.3f})"
            row += " | " + cell.rjust(col_w)
        print(row)

    print(sep)
    row = f"{'mIoU':<{name_w}}"
    for split, ckpt in columns:
        miou = all_results[ckpt][split][0]
        cell = f"{miou:.3f}"
        if ckpt != ckpt_labels[0]:
            baseline = all_results[ckpt_labels[0]][split][0]
            delta = miou - baseline
            cell = f"{miou:.3f} ({delta:+.3f})"
        row += " | " + cell.rjust(col_w)
    print(row)
    print(sep)

    # MVP target check
    if "test_fr" in splits:
        print(f"\n🎯 MVP target: mIoU on test_fr ≥ 0.55")
        for ckpt in ckpt_labels:
            miou = all_results[ckpt]["test_fr"][0]
            status = "✓ REACHED" if miou >= 0.55 else "✗ below"
            print(f"   {ckpt}: {miou:.4f}  {status}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", help="Single checkpoint path")
    ap.add_argument("--checkpoints", nargs="+",
                    help="Multiple checkpoints as label=path (e.g. stage_a=path1 stage_b=path2)")
    ap.add_argument("--dataset_root", required=True,
                    help="Combined dataset root (must contain the requested splits)")
    ap.add_argument("--splits", nargs="+", default=["test_fr", "test_cc"])
    ap.add_argument("--image_size", type=int, default=768)
    ap.add_argument("--backbone",
                    default="facebook/mask2former-swin-small-coco-panoptic")
    ap.add_argument("--device", default="auto",
                    help="auto / mps / cpu — use cpu while training runs in BG")
    args = ap.parse_args()

    ckpts = _parse_checkpoints(args)
    device = _select_device(args.device)
    print(f"Device: {device}")
    print(f"Dataset: {args.dataset_root}")
    print(f"Splits:  {args.splits}")
    print(f"Checkpoints: {list(ckpts.keys())}")

    all_results: dict[str, dict[str, tuple[float, np.ndarray]]] = {}
    for label, path in ckpts.items():
        all_results[label] = evaluate_checkpoint(
            path, args.dataset_root, args.splits,
            args.image_size, args.backbone, device,
        )

    print_results_table(all_results, args.splits)


if __name__ == "__main__":
    main()
