"""Évaluation v2 sur les 8 plans FR avec seuil de probabilité variable
pour récupérer les murs que le modèle "hésite" à prédire.

Au lieu d'utiliser `processor.post_process_semantic_segmentation`
(argmax = équivalent seuil 0.5 sur la classe Wall), on extrait
manuellement la carte de probabilité du class Wall et on applique
plusieurs seuils.

Composite 5 colonnes :
1. Original
2. argmax baseline (= seuil 0.5) + Stage A
3. seuil 0.3 + Stage A
4. seuil 0.2 + Stage A
5. carte de probabilité du class Wall (heatmap)

Sortie : experiments/wall_detection_eval/outputs/v2_threshold_fr/
"""
from __future__ import annotations
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.segmentation.classes import CLASS_ID, NUM_CLASSES
from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.model import build_model, get_processor
from src.segmentation.preprocess import letterbox
from scripts.postprocess_walls import close_gaps, filter_cc

CKPT = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v2" / "checkpoints" / "best.pt"
FR_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "v2_threshold_fr"

BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
IMAGE_SIZE = 640

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Seuils à comparer (sur la probabilité de class Wall)
THRESHOLDS = [0.5, 0.3, 0.2]


def predict_wall_proba(model, processor, device, image_path: Path):
    """Renvoie (rgb, wall_proba) où wall_proba est une carte HxW [0,1]
    de probabilité de la classe Wall, à la résolution du letterbox."""
    bgr = cv2.imread(str(image_path))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    padded, info = letterbox(rgb, target_size=IMAGE_SIZE)
    norm = (padded.astype(np.float32) / 255.0 - _MEAN) / _STD
    tensor = torch.from_numpy(norm).permute(2, 0, 1).unsqueeze(0).float().to(device)
    with torch.no_grad():
        out = model(pixel_values=tensor)

    # Mask2Former — réplique la logique de post_process_semantic_segmentation
    # mais extrait la carte de probabilité de la classe Wall plutôt que argmax.
    # mask_logits : (1, Q, H', W') ; class_logits : (1, Q, C+1) avec dernière
    # classe = "no object".
    mask_logits = out.masks_queries_logits
    class_logits = out.class_queries_logits
    masks = mask_logits.sigmoid()                            # (1, Q, H', W')
    classes = class_logits.softmax(dim=-1)[..., :-1]         # (1, Q, C)

    # Pour chaque pixel et chaque classe c :
    #   seg[c, h, w] = sum_q (classes[q, c] * masks[q, h, w])
    seg = torch.einsum("bqc,bqhw->bchw", classes, masks)     # (1, C, H', W')
    seg = F.interpolate(seg, size=(IMAGE_SIZE, IMAGE_SIZE),
                        mode="bilinear", align_corners=False)
    wall_proba_lb = seg[0, CLASS_ID["Wall"]].cpu().numpy()   # (IMAGE_SIZE, IMAGE_SIZE)

    # Unletterbox + resize à la dim originale
    new_h = IMAGE_SIZE - info.pad_top - info.pad_bottom
    new_w = IMAGE_SIZE - info.pad_left - info.pad_right
    cropped = wall_proba_lb[info.pad_top:info.pad_top + new_h,
                            info.pad_left:info.pad_left + new_w]
    full = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)
    return rgb, np.clip(full, 0.0, 1.0)


def apply_stage_a(mask: np.ndarray, image_shape) -> np.ndarray:
    """Stage A = closing + CC filter, params adaptés à la taille de l'image."""
    h, w = image_shape[:2]
    closing_k = max(11, int(0.012 * min(h, w)) | 1)
    closed = close_gaps(mask, kernel_size=closing_k)
    min_area = max(200, int(0.0002 * h * w))
    return filter_cc(closed, min_area=min_area, min_aspect_ratio=3.0)


def tint_overlay(rgb, mask, color=(255, 0, 0), alpha=0.55):
    layer = np.zeros_like(rgb)
    layer[..., :] = color
    a = (mask > 0).astype(np.float32)[..., None] * alpha
    return (rgb * (1 - a) + layer * a).astype(np.uint8)


def proba_to_heatmap(proba: np.ndarray) -> np.ndarray:
    """Carte de proba [0,1] → heatmap RGB jet."""
    p8 = (np.clip(proba, 0, 1) * 255).astype(np.uint8)
    bgr = cv2.applyColorMap(p8, cv2.COLORMAP_JET)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def make_composite(rgb, proba):
    h, w = rgb.shape[:2]
    columns = [rgb]

    pcts = []
    for thr in THRESHOLDS:
        m = (proba >= thr).astype(np.uint8)
        m_a = apply_stage_a(m, rgb.shape)
        columns.append(tint_overlay(rgb, m_a))
        pcts.append((thr, (m_a > 0).mean() * 100))

    columns.append(proba_to_heatmap(proba))

    composite = np.concatenate(columns, axis=1)
    label_h = 35
    n_cols = len(columns)
    canvas = np.full((h + label_h, w * n_cols, 3), 255, dtype=np.uint8)
    canvas[label_h:, :, :] = composite
    titles = ["Original"]
    for thr, pct in pcts:
        titles.append(f"thr={thr:.1f} + Stage A ({pct:.1f}%)")
    titles.append("Carte proba Wall")
    for i, t in enumerate(titles):
        cv2.putText(canvas, t, (i * w + 10, 22),
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
    print(f"{len(fr_files)} FR plans  |  seuils testés : {THRESHOLDS}")

    for i, plan in enumerate(fr_files, 1):
        rgb, proba = predict_wall_proba(model, processor, device, plan)
        composite = make_composite(rgb, proba)
        out_path = OUT_DIR / f"{plan.stem}_thresholds.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(composite, cv2.COLOR_RGB2BGR))

        pcts = [(thr, ((proba >= thr).astype(np.uint8) > 0).mean() * 100)
                for thr in THRESHOLDS]
        s = "  ".join(f"thr{thr}={pct:.1f}%" for thr, pct in pcts)
        print(f"  [{i}/{len(fr_files)}] {plan.stem[:45]:45s}  {s}")

    print(f"\nComposites : {OUT_DIR}/")


if __name__ == "__main__":
    main()
