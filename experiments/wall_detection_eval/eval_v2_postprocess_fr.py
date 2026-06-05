"""Évaluation visuelle wall_only_dwg_v2 + post-processing (A puis B) sur
les 8 plans FR architectes.

Pour chaque plan FR, génère un composite 4 colonnes :
1. Original
2. Pred raw v2 (rouge transparent)
3. Stage A : closing + CC filter (rouge transparent)
4. Stage B : skeleton vectorisé → segments dessinés sur l'original

Sortie : experiments/wall_detection_eval/outputs/v2_postprocess_fr/
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
from scripts.postprocess_walls import (
    close_gaps, filter_cc, skeletonize_walls,
    vectorize_skeleton, draw_segments,
)

CKPT = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v2" / "checkpoints" / "best.pt"
FR_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "v2_postprocess_fr"

BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
IMAGE_SIZE = 640

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def predict_wall_mask(model, processor, device, image_path: Path):
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


def tint_overlay(rgb: np.ndarray, mask: np.ndarray, color, alpha: float = 0.55) -> np.ndarray:
    layer = np.zeros_like(rgb)
    layer[..., :] = color
    a = (mask > 0).astype(np.float32)[..., None] * alpha
    return (rgb * (1 - a) + layer * a).astype(np.uint8)


def draw_segments_overlay(rgb: np.ndarray, segments, color=(255, 0, 0), thickness=3) -> np.ndarray:
    out = rgb.copy()
    for x1, y1, x2, y2 in segments:
        cv2.line(out, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)
    return out


def make_composite(rgb, raw, stage_a, segments):
    h, w = rgb.shape[:2]
    col_raw = tint_overlay(rgb, raw, (255, 0, 0))
    col_a = tint_overlay(rgb, stage_a, (255, 0, 0))
    col_b = draw_segments_overlay(rgb, segments, color=(255, 0, 0), thickness=3)

    composite = np.concatenate([rgb, col_raw, col_a, col_b], axis=1)
    label_h = 35
    canvas = np.full((h + label_h, w * 4, 3), 255, dtype=np.uint8)
    canvas[label_h:, :, :] = composite
    titles = ["Original", "v2 brut", "Stage A : closing + CC filter",
              f"Stage B : vectoris\xe9 ({len(segments)} segments)"]
    for i, t in enumerate(titles):
        cv2.putText(canvas, t, (i * w + 10, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)
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
        rgb, raw = predict_wall_mask(model, processor, device, plan)

        # Stage A : closing pour reboucher les trous, puis CC filter pour
        # dégager le bruit (texte, pictogrammes, patches isolés).
        # Kernel closing scale avec l'image : ~1% du min(h, w).
        closing_k = max(11, int(0.012 * min(rgb.shape[:2])) | 1)  # impair
        closed = close_gaps(raw, kernel_size=closing_k)
        min_area = max(200, int(0.0002 * rgb.shape[0] * rgb.shape[1]))
        stage_a = filter_cc(closed, min_area=min_area, min_aspect_ratio=3.0)

        # Stage B : skeleton + HoughLinesP
        skel = skeletonize_walls(stage_a)
        segments = vectorize_skeleton(
            skel,
            hough_threshold=30,
            min_line_length=max(25, int(0.015 * min(rgb.shape[:2]))),
            max_line_gap=15,
        )

        composite = make_composite(rgb, raw, stage_a, segments)
        out_path = OUT_DIR / f"{plan.stem}_postprocess.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(composite, cv2.COLOR_RGB2BGR))

        raw_pct = (raw > 0).mean() * 100
        a_pct = (stage_a > 0).mean() * 100
        print(f"  [{i}/{len(fr_files)}] {plan.stem[:50]:50s}  "
              f"raw={raw_pct:.1f}%  A={a_pct:.1f}%  B={len(segments)} segs"
              f"  closing_k={closing_k}  min_area={min_area}")

    print(f"\nComposites : {OUT_DIR}/")


if __name__ == "__main__":
    main()
