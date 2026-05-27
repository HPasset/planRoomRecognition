"""CLI: predict_segmentation.py --image plan.png --checkpoint best.pt --out result.json"""
import os
# MUST be set before torch import (Mask2Former MPS fallback for grid_sampler_2d)
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import argparse
import sys
from pathlib import Path

# Allow running from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.segmentation.inference import SegmentationInference


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, help="Path to input plan image")
    ap.add_argument("--checkpoint", required=True, help="Path to model checkpoint .pt")
    ap.add_argument("--out", required=True, help="Path to output JSON")
    ap.add_argument("--backbone", default="facebook/mask2former-swin-small-coco-panoptic",
                    help="HuggingFace backbone id")
    ap.add_argument("--image_size", type=int, default=768,
                    help="Inference resolution (default 768)")
    ap.add_argument("--device", default="auto", help="auto / mps / cpu / cuda")
    ap.add_argument("--walls_dir", default="runs/segmentation/inference_walls",
                    help="Directory to dump walls mask PNGs")
    args = ap.parse_args()

    inf = SegmentationInference(
        checkpoint_path=args.checkpoint,
        backbone=args.backbone,
        image_size=args.image_size,
        device=args.device,
        walls_out_dir=args.walls_dir,
    )
    result = inf.predict(args.image)
    Path(args.out).write_text(result.model_dump_json(indent=2))
    print(f"Wrote {args.out} with {len(result.rooms)} rooms, "
          f"inference={result.inference_time_ms}ms")


if __name__ == "__main__":
    main()
