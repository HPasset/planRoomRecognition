"""Évaluation visuelle de wall_only_dwg_v2 sur le test set (21 plans).

Pour chaque plan test :
1. Charge image + ground truth mask
2. Forward le modèle (best.pt)
3. Génère composite 4 colonnes : original | GT mask | Pred mask | overlay TP/FP/FN
4. Calcule per-image IoU (wall)

Sortie : experiments/wall_detection_eval/outputs/v2_test_set/
  per_image/<id>.png    — composite par plan
  summary.json          — IoU par image + agrégé
  summary.txt           — bilan lisible
"""
from __future__ import annotations
import json
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
TEST_IMG_DIR = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only_v2" / "images" / "test"
TEST_SEM_DIR = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only_v2" / "semantic" / "test"
OUT_DIR = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "outputs" / "v2_test_set"

BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
IMAGE_SIZE = 640  # même que la config v2

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def predict_wall_mask(model, processor, device, image_path: Path) -> np.ndarray:
    """Renvoie un mask binaire 0/1 à la résolution originale de l'image."""
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
    # Unletterbox : crop la zone valide + resize à la dim originale
    new_h = IMAGE_SIZE - info.pad_top - info.pad_bottom
    new_w = IMAGE_SIZE - info.pad_left - info.pad_right
    cropped = walls_lb[info.pad_top:info.pad_top + new_h,
                       info.pad_left:info.pad_left + new_w]
    full = cv2.resize(cropped, (w, h), interpolation=cv2.INTER_NEAREST)
    return full


def compute_iou(pred: np.ndarray, gt: np.ndarray) -> float:
    pred_b = pred.astype(bool)
    gt_b = gt.astype(bool)
    inter = (pred_b & gt_b).sum()
    union = (pred_b | gt_b).sum()
    return float(inter) / float(union) if union > 0 else float("nan")


def make_composite(rgb: np.ndarray, gt: np.ndarray, pred: np.ndarray) -> np.ndarray:
    """4 colonnes côte-à-côte : original | GT | Pred | TP/FP/FN overlay."""
    h, w = rgb.shape[:2]
    # GT et Pred en mask rouge transparent sur l'image
    def tint(mask, color):
        out = rgb.copy()
        m = (mask > 0).astype(np.float32)[..., None] * 0.55
        col = np.zeros_like(rgb)
        col[..., :] = color
        return (out * (1 - m) + col * m).astype(np.uint8)

    gt_overlay = tint(gt, (0, 200, 0))      # vert = GT
    pred_overlay = tint(pred, (255, 0, 0))  # rouge = Pred

    # TP/FP/FN composite : vert = TP, rouge = FP, bleu = FN
    diff = rgb.copy().astype(np.float32)
    tp = (gt > 0) & (pred > 0)
    fp = (gt == 0) & (pred > 0)
    fn = (gt > 0) & (pred == 0)
    alpha = 0.6
    diff[tp] = (1 - alpha) * diff[tp] + alpha * np.array([0, 200, 0])    # green TP
    diff[fp] = (1 - alpha) * diff[fp] + alpha * np.array([255, 60, 0])   # red FP
    diff[fn] = (1 - alpha) * diff[fn] + alpha * np.array([0, 80, 255])   # blue FN
    diff_overlay = diff.astype(np.uint8)

    composite = np.concatenate([rgb, gt_overlay, pred_overlay, diff_overlay], axis=1)
    # Petit padding+labels en haut
    label_h = 30
    canvas = np.full((h + label_h, w * 4, 3), 255, dtype=np.uint8)
    canvas[label_h:, :, :] = composite
    titles = ["Original", "Ground Truth (vert)", "Prediction (rouge)",
              "TP=vert  FP=rouge  FN=bleu"]
    for i, t in enumerate(titles):
        cv2.putText(canvas, t, (i * w + 10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return canvas


def main():
    if not CKPT.exists():
        print(f"ERROR: checkpoint manquant : {CKPT}")
        sys.exit(1)

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"Loading model ({BACKBONE}) on {device}...")
    model = build_model(backbone=BACKBONE, num_classes=NUM_CLASSES)
    ckpt = load_checkpoint(CKPT, map_location=str(device))
    model.load_state_dict(ckpt["model_state_dict"])
    model.to(device).eval()
    processor = get_processor(BACKBONE)

    (OUT_DIR / "per_image").mkdir(parents=True, exist_ok=True)

    test_files = sorted(TEST_IMG_DIR.glob("*.png"))
    print(f"{len(test_files)} test images")
    results = []
    for i, img_path in enumerate(test_files, 1):
        plan_id = img_path.stem  # dwg_NNNN
        gt_path = TEST_SEM_DIR / img_path.name
        gt = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        rgb = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB)

        pred = predict_wall_mask(model, processor, device, img_path)

        # Resize GT to match pred resolution if needed
        if gt.shape != pred.shape:
            gt = cv2.resize(gt, (pred.shape[1], pred.shape[0]),
                            interpolation=cv2.INTER_NEAREST)
        gt_bin = (gt > 0).astype(np.uint8)

        iou = compute_iou(pred, gt_bin)

        comp = make_composite(rgb, gt_bin, pred)
        out_path = OUT_DIR / "per_image" / f"{plan_id}.png"
        cv2.imwrite(str(out_path), cv2.cvtColor(comp, cv2.COLOR_RGB2BGR))
        results.append({"plan_id": plan_id, "iou_wall": iou})
        print(f"  [{i}/{len(test_files)}] {plan_id}  IoU={iou:.4f}")

    # Aggregate
    ious = [r["iou_wall"] for r in results if not np.isnan(r["iou_wall"])]
    summary = {
        "n_test": len(results),
        "mean_iou_wall": float(np.mean(ious)) if ious else None,
        "median_iou_wall": float(np.median(ious)) if ious else None,
        "min_iou_wall": float(np.min(ious)) if ious else None,
        "max_iou_wall": float(np.max(ious)) if ious else None,
        "per_image": sorted(results, key=lambda r: r["iou_wall"]),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    txt = [
        "=== Évaluation wall_only_dwg_v2 sur test set ===",
        f"Checkpoint  : {CKPT.name}  (epoch {ckpt.get('epoch', '?')})",
        f"Test plans  : {summary['n_test']}",
        "",
        f"IoU mur     : mean={summary['mean_iou_wall']:.4f}  "
        f"median={summary['median_iou_wall']:.4f}  "
        f"min={summary['min_iou_wall']:.4f}  max={summary['max_iou_wall']:.4f}",
        "",
        "Par plan (trié par IoU croissant) :",
    ]
    for r in summary["per_image"]:
        txt.append(f"  {r['plan_id']:12s}  IoU={r['iou_wall']:.4f}")
    (OUT_DIR / "summary.txt").write_text("\n".join(txt))

    print("\n" + "\n".join(txt[-20:]))
    print(f"\nComposites : {OUT_DIR / 'per_image'}/")
    print(f"Summary    : {OUT_DIR / 'summary.txt'}")


if __name__ == "__main__":
    main()
