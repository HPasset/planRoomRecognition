"""CLI: train_segmentation.py --config configs/segmentation/stage_a_cubicasa.yaml [--resume latest]"""
import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/train_segmentation.py` from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.segmentation.config import load_config
from src.segmentation.trainer import Trainer


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True,
                    help="Path to YAML training config")
    ap.add_argument("--resume", default="latest", choices=["latest", "no"],
                    help="latest=auto-resume from last checkpoint; no=fresh start")
    ap.add_argument("--device", default="auto",
                    help="auto / mps / cpu / cuda (default auto)")
    args = ap.parse_args()

    cfg = load_config(args.config)
    trainer = Trainer(cfg, device=args.device)
    if args.resume == "no":
        trainer.epoch = 0
        trainer.global_step = 0
    trainer.fit()


if __name__ == "__main__":
    main()
