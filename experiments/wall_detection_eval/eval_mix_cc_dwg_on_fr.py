"""Inférence du modèle wall_only_stage_a_v1_cloud (mix CC+DWG) sur les 8 plans
FR de test. Génère masks + overlays HR pour comparer avec DWG-only.

Sortie : experiments/wall_detection_eval/outputs/mix_cc_dwg/
"""
from __future__ import annotations

import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import sys
import time
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.segmentation.inference import SegmentationInference


CKPT = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_stage_a_v1_cloud" / "checkpoints" / "best.pt"
PLANS_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "mix_cc_dwg"
OVERLAYS_DIR = OUT_DIR / "overlays"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAYS_DIR.mkdir(exist_ok=True)
    walls_dir = OUT_DIR / "walls_masks"
    walls_dir.mkdir(exist_ok=True)

    print(f"Loading model from {CKPT}")
    inf = SegmentationInference(
        checkpoint_path=CKPT,
        backbone="facebook/mask2former-swin-tiny-coco-panoptic",
        image_size=640,                  # match training resolution
        walls_out_dir=walls_dir,
    )
    print(f"Model loaded on {inf.device}")

    plans = sorted(PLANS_DIR.glob("*.png"))
    print(f"Found {len(plans)} test plans\n")

    for plan_path in plans:
        print(f"  {plan_path.name[:60]:60s}", end=" ")
        t0 = time.time()
        result = inf.predict(plan_path)
        elapsed = time.time() - t0

        original = cv2.imread(str(plan_path))
        mask_path = walls_dir / f"{plan_path.stem}_walls.png"
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            print(" MISSING mask")
            continue
        mask_full = cv2.resize(
            mask, (original.shape[1], original.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

        # Overlay red transparent (alpha 0.55) — same style as DWG-only for fair comparison
        original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
        red = np.zeros_like(original_rgb)
        red[..., 0] = 255
        alpha = (mask_full > 127).astype(np.float32)[..., None] * 0.55
        overlay = (original_rgb * (1 - alpha) + red * alpha).astype(np.uint8)
        out_path = OVERLAYS_DIR / f"{plan_path.stem}_overlay.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

        pct = (mask_full > 127).mean() * 100
        print(f"({elapsed:.2f}s, walls={pct:.1f}%)")

    print(f"\nOverlays dans : {OVERLAYS_DIR}/")
    print(f"Comparaison disponible avec : experiments/wall_detection_eval/outputs/dwg_only/overlays/")


if __name__ == "__main__":
    main()
