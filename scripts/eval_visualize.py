"""Generate an HTML report of predictions sorted by worst mIoU.

Usage:
  python scripts/eval_visualize.py \\
    --checkpoint runs/segmentation/stage_a_cubicasa_v1/checkpoints/best.pt \\
    --dataset_root data/processed/cubicasa_panoptic \\
    --split val \\
    --out runs/segmentation/stage_a_cubicasa_v1/eval_report.html \\
    --max_samples 50
"""
import argparse
import base64
import sys
from io import BytesIO
from pathlib import Path

# Allow running from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cv2
import numpy as np
from PIL import Image
from tqdm import tqdm

from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES
from src.segmentation.dataset import PanopticDataset
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.inference import SegmentationInference


_PALETTE = np.array([
    [0, 0, 0],         # 0 Background
    [80, 80, 80],      # 1 Wall
    [255, 200, 100],   # 2 Kitchen
    [120, 220, 100],   # 3 LivingRoom
    [100, 150, 255],   # 4 BedRoom
    [200, 100, 200],   # 5 Bath
    [255, 220, 0],     # 6 Entry
    [180, 120, 80],    # 7 Storage
    [100, 100, 100],   # 8 Garage
    [120, 220, 220],   # 9 Outdoor
], dtype=np.uint8)


def colorize(mask: np.ndarray) -> np.ndarray:
    return _PALETTE[mask.clip(0, NUM_CLASSES - 1)]


def to_b64(img: np.ndarray) -> str:
    buf = BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--dataset_root", required=True)
    ap.add_argument("--split", default="val")
    ap.add_argument("--out", required=True)
    ap.add_argument("--max_samples", type=int, default=50)
    ap.add_argument("--image_size", type=int, default=768)
    args = ap.parse_args()

    inf = SegmentationInference(
        checkpoint_path=args.checkpoint,
        image_size=args.image_size, device="auto",
    )
    ds = PanopticDataset(args.dataset_root, args.split, args.image_size, train=False)

    rows: list[dict] = []
    for i in tqdm(range(min(len(ds), args.max_samples * 3))):
        sid = ds.ids[i]
        img_path = Path(args.dataset_root) / "images" / args.split / f"{sid}.png"
        gt_path = Path(args.dataset_root) / "semantic" / args.split / f"{sid}.png"
        bgr = cv2.imread(str(img_path))
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        gt = cv2.imread(str(gt_path), cv2.IMREAD_UNCHANGED)

        # Quick prediction (uses inference pipeline; we extract sem map by reading walls + rooms)
        out = inf.predict(img_path)
        # Reconstruct a semantic map from rooms + walls for IoU
        pred_sem = np.zeros_like(gt)
        for r in out.rooms:
            poly = np.asarray(r.polygon, dtype=np.int32)
            cv2.fillPoly(pred_sem, [poly], r.type_id)
        walls_mask = cv2.imread(out.walls.mask_path, cv2.IMREAD_UNCHANGED)
        if walls_mask is not None:
            pred_sem[walls_mask > 0] = 1

        ious = compute_iou_per_class(pred_sem, gt, NUM_CLASSES)
        miou = compute_miou(ious)
        rows.append({
            "id": sid, "miou": miou,
            "img_b64": to_b64(rgb),
            "gt_b64": to_b64(colorize(gt)),
            "pred_b64": to_b64(colorize(pred_sem)),
        })

    rows.sort(key=lambda r: r["miou"])  # worst first
    rows = rows[: args.max_samples]

    html_parts = ["<!doctype html><meta charset='utf-8'>",
                  "<style>body{font-family:sans-serif} .row{display:flex;gap:8px;align-items:center;border-bottom:1px solid #ccc;padding:8px} img{max-width:300px;border:1px solid #888} .legend{font-size:12px} .miou{font-weight:bold;color:#a00}</style>",
                  "<h1>Eval Visualisation — worst mIoU first</h1>"]
    legend = " · ".join(f"{i}={n}" for i, n in enumerate(CLASS_NAMES))
    html_parts.append(f"<div class='legend'>{legend}</div>")
    for r in rows:
        html_parts.append(
            f"<div class='row'><div>{r['id']}<br><span class='miou'>mIoU={r['miou']:.3f}</span></div>"
            f"<img src='data:image/png;base64,{r['img_b64']}' alt='input'>"
            f"<img src='data:image/png;base64,{r['gt_b64']}' alt='gt'>"
            f"<img src='data:image/png;base64,{r['pred_b64']}' alt='pred'></div>"
        )
    Path(args.out).write_text("\n".join(html_parts), encoding="utf-8")
    print(f"Wrote {args.out} with {len(rows)} samples")


if __name__ == "__main__":
    main()
