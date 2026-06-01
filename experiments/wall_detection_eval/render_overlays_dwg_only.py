"""Génère 1 overlay PNG par plan FR (full resolution) à partir des masks
déjà calculés par eval_dwg_only_on_fr.py.

Overlay = original + transparent red where mask > 127.
"""
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLANS_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
MASKS_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "dwg_only" / "walls_masks"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "dwg_only" / "overlays"

OUT_DIR.mkdir(parents=True, exist_ok=True)

plans = sorted(PLANS_DIR.glob("*.png"))
print(f"{len(plans)} plans")

for plan_path in plans:
    original = cv2.imread(str(plan_path))
    original_rgb = cv2.cvtColor(original, cv2.COLOR_BGR2RGB)
    mask_path = MASKS_DIR / f"{plan_path.stem}_walls.png"
    if not mask_path.exists():
        print(f"  MISSING : {plan_path.name}")
        continue
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    mask_full = cv2.resize(mask, (original.shape[1], original.shape[0]), interpolation=cv2.INTER_NEAREST)

    red = np.zeros_like(original_rgb)
    red[..., 0] = 255  # R channel
    alpha = (mask_full > 127).astype(np.float32)[..., None] * 0.55
    overlay = (original_rgb * (1 - alpha) + red * alpha).astype(np.uint8)

    out_path = OUT_DIR / f"{plan_path.stem}_overlay.png"
    cv2.imwrite(str(out_path), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    pct = (mask_full > 127).mean() * 100
    print(f"  {plan_path.name[:60]:60s} walls={pct:.1f}%  →  {out_path.name}")

print(f"\nOverlays dans : {OUT_DIR}/")
