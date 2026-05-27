"""Train YOLO (ultralytics) with a YAML config or CLI args.

Supports two modes:
  1. With --config: read all params from a YAML config
     python scripts/train_yolo.py --config configs/yolo/brique_a.yaml

  2. CLI args (legacy, for ad-hoc experiments):
     python scripts/train_yolo.py --data <dataset.yaml> --model yolo11m.pt --epochs 100
"""
from __future__ import annotations
import argparse
import os
# MPS fallback for ops that may not be supported natively
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from pathlib import Path

import yaml
from ultralytics import YOLO


def load_yaml_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="YAML config (overrides all CLI args below)")
    # Legacy CLI args (used if --config not provided)
    ap.add_argument("--data", default="data/processed/cubicasa5k_yolo/dataset.yaml")
    ap.add_argument("--model", default="yolo11m.pt")
    ap.add_argument("--imgsz", type=int, default=1024)
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--project", default="runs/detect")
    ap.add_argument("--name", default="train")
    args = ap.parse_args()

    if args.config:
        cfg = load_yaml_config(Path(args.config))
        print(f"Config loaded from {args.config}")
        print(f"  run_name: {cfg.get('run_name', '(unset)')}")
    else:
        # Build cfg from CLI args
        cfg = {
            "data": args.data,
            "model": args.model,
            "imgsz": args.imgsz,
            "epochs": args.epochs,
            "batch": args.batch,
            "device": args.device,
            "project": args.project,
            "name": args.name,
        }

    data_path = Path(cfg["data"])
    if not data_path.exists():
        raise SystemExit(f"Dataset not found: {data_path}")

    model_name = cfg.get("model", "yolo11m.pt")
    model = YOLO(model_name)

    # Filter out keys that aren't valid train() args (run_name, seed, etc.)
    # ultralytics .train() accepts most names verbatim — we keep only known ones.
    train_kwargs = {}
    valid_keys = {
        "data", "imgsz", "epochs", "batch", "device", "project", "name",
        "patience", "lr0", "lrf", "warmup_epochs", "weight_decay",
        "hsv_h", "hsv_s", "hsv_v", "degrees", "translate", "scale",
        "fliplr", "flipud", "mosaic", "mixup", "copy_paste",
        "optimizer", "seed", "resume", "exist_ok", "single_cls",
    }
    for k, v in cfg.items():
        if k in valid_keys:
            train_kwargs[k] = v
    # Force resolve data path to absolute (avoid surprises depending on CWD)
    train_kwargs["data"] = str(data_path.resolve())

    print("\nTraining with:")
    for k, v in sorted(train_kwargs.items()):
        print(f"  {k}: {v}")
    print()

    model.train(**train_kwargs)


if __name__ == "__main__":
    main()
