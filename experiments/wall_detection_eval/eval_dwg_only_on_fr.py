"""Inférence du modèle wall_only_dwg_v1 sur les 8 plans FR de test, et
génération d'une grille comparative (original | predicted mask | overlay).

Sortie : experiments/wall_detection_eval/outputs/dwg_only/
"""
from __future__ import annotations

import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.segmentation.inference import SegmentationInference


CKPT = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v1" / "checkpoints" / "best.pt"
PLANS_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "dwg_only"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    walls_dir = OUT_DIR / "walls_masks"
    walls_dir.mkdir(exist_ok=True)

    print(f"Loading model from {CKPT}")
    inf = SegmentationInference(
        checkpoint_path=CKPT,
        backbone="facebook/mask2former-swin-tiny-coco-panoptic",
        image_size=512,                  # match training resolution
        walls_out_dir=walls_dir,
    )
    print(f"Model loaded on {inf.device}")

    plans = sorted(PLANS_DIR.glob("*.png"))
    print(f"Found {len(plans)} test plans")

    fig, axes = plt.subplots(len(plans), 3, figsize=(18, 4 * len(plans)))
    if len(plans) == 1:
        axes = axes.reshape(1, -1)

    for i, plan_path in enumerate(plans):
        print(f"  [{i+1}/{len(plans)}] {plan_path.name}")
        t0 = time.time()
        result = inf.predict(plan_path)
        elapsed = time.time() - t0

        # Load original + predicted mask
        original = cv2.imread(str(plan_path))
        original = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
        mask_path = walls_dir / f"{plan_path.stem}_walls.png"
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(f"    WARNING: no mask saved for {plan_path.name}")
            continue
        # Resize mask to original size
        mask_full = cv2.resize(
            mask, (original.shape[1], original.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

        # Overlay : red transparent
        overlay = original.copy()
        red = np.zeros_like(original)
        red[..., 0] = 255
        alpha = (mask_full > 127).astype(np.float32)[..., None] * 0.5
        overlay = (overlay * (1 - alpha) + red * alpha).astype(np.uint8)

        axes[i, 0].imshow(original)
        axes[i, 0].set_title(f"{plan_path.name[:50]}\n({elapsed:.2f}s, walls_ratio={(mask_full>127).mean():.3f})")
        axes[i, 0].axis("off")
        axes[i, 1].imshow(mask_full, cmap="gray")
        axes[i, 1].set_title("Predicted wall mask")
        axes[i, 1].axis("off")
        axes[i, 2].imshow(overlay)
        axes[i, 2].set_title("Overlay")
        axes[i, 2].axis("off")

    plt.tight_layout()
    grid_path = OUT_DIR / "comparison_grid_dwg_only.png"
    plt.savefig(grid_path, dpi=80, bbox_inches="tight")
    plt.close()
    print(f"\nGrid saved : {grid_path}")
    print(f"Masks dans : {walls_dir}/")


if __name__ == "__main__":
    main()
