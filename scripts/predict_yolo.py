import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="runs/detect/weights/best.pt")
    ap.add_argument("--source", default="data/processed/cubicasa5k_yolo/images/val")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="0")
    ap.add_argument("--project", default="runs")
    ap.add_argument("--name", default="predict")
    ap.add_argument("--save", action="store_true", help="Save annotated images")
    args = ap.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}")

    model = YOLO(str(model_path))
    model.predict(
        source=args.source,
        conf=args.conf,
        device=args.device,
        project=args.project,
        name=args.name,
        save=args.save,
    )


if __name__ == "__main__":
    main()
