"""Évaluation visuelle de wall_only_dwg_v2 sur les 8 plans FR de référence
(plans architectes français hors distribution training).

Pour chaque plan FR :
1. Forward le modèle (best.pt v2)
2. Génère un overlay (original + masque mur en rouge transparent)
3. Sauvegarde dans outputs/v2_fr_plans/

Pas de GT mask sur ces plans → pas d'IoU calculé, juste visuel.
"""
from __future__ import annotations
import sys
from pathlib import Path

import cv2
import numpy as np
import torch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.segmentation.classes import CLASS_ID, NUM_CLASSES
from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.model import build_model, get_processor
from src.segmentation.preprocess import letterbox

CKPT = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v2" / "checkpoints" / "best.pt"
FR_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "v2_fr_plans"

BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
IMAGE_SIZE = 640

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def predict_wall_mask(model, processor, device, image_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (rgb_original, mask_pred 0/1 same size)."""
    bgr = cv2.imread(str(image_path))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    padded, info = letterbox(rgb, target_size=IMAGE_SIZE)
    norm = (padded.astype(np.float32) / 255.0 - _MEAN) / _STD
    tensor = torch.from_numpy(norm).permute(2, 0, 1).unsqueeze(0).float().to(device)
    with torch.no_grad():
        out = model(pixel_values=tensor)
    sem = processor.post_process_semantic_segmentation(
        out, target_sizes=[(IMAGE_SIZE, IMAGE_SIZE)],
    )[0].cpu().numpy()
    walls_lb = (sem == CLASS_ID["Wall"]).astype(np.uint8)
    new_h = IMAGE_SIZE - info.pad_top - info.pad_bottom
    new_w = IMAGE_SIZE - info.pad_left - info.pad_right
    cropped = walls_lb[info.pad_top:info.pad_top + new_h,
                       info.pad_left:info.pad_left + new_w]
    full = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_NEAREST)
    return rgb, full


def make_overlay(rgb: np.ndarray, mask: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    """Image + masque rouge transparent."""
    red = np.zeros_like(rgb)
    red[..., 0] = 255
    a = (mask > 0).astype(np.float32)[..., None] * alpha
    return (rgb * (1 - a) + red * a).astype(np.uint8)


def make_composite(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """2 colonnes côte-à-côte : original | overlay."""
    h, w = rgb.shape[:2]
    overlay = make_overlay(rgb, mask)
    composite = np.concatenate([rgb, overlay], axis=1)
    label_h = 30
    canvas = np.full((h + label_h, w * 2, 3), 255, dtype=np.uint8)
    canvas[label_h:, :, :] = composite
    cv2.putText(canvas, "Original", (10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    cv2.putText(canvas, "v2 prediction (rouge transparent)", (w + 10, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return canvas


def main():
    if not CKPT.exists():
        print(f"ERROR: checkpoint manquant : {CKPT}")
        sys.exit(1)

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Loading model on {device}...")
    model = build_model(backbone=BACKBONE, num_classes=NUM_CLASSES)
    ckpt = load_checkpoint(CKPT, map_location=str(device))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    processor = get_processor(BACKBONE)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fr_files = sorted(FR_DIR.glob("*.png"))
    print(f"{len(fr_files)} FR plans")

    for i, plan in enumerate(fr_files, 1):
        rgb, mask = predict_wall_mask(model, processor, device, plan)
        comp = make_composite(rgb, mask)
        out_path = OUT_DIR / f"{plan.stem}_v2_overlay.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(comp, cv2.COLOR_RGB2BGR))
        pct = (mask > 0).mean() * 100
        print(f"  [{i}/{len(fr_files)}] {plan.name[:60]:60s}  walls={pct:.1f}%  →  {out_path.name}")

    print(f"\nOverlays : {OUT_DIR}/")


if __name__ == "__main__":
    main()
