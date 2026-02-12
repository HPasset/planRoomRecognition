import argparse
from pathlib import Path
import sys

import cv2


if __package__ is None:
    # Allow running as a script: add repo root to sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.cubicasa5k_export_yolo import extract_boxes, get_svg_size, to_yolo


def draw_boxes(img_bgr, boxes, w, h, color, label):
    for box in boxes:
        cx, cy, bw, bh = to_yolo(box, w, h)
        x1 = int((cx - bw / 2) * w)
        y1 = int((cy - bh / 2) * h)
        x2 = int((cx + bw / 2) * w)
        y2 = int((cy + bh / 2) * h)
        cv2.rectangle(img_bgr, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            img_bgr,
            label,
            (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
            cv2.LINE_AA,
        )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--svg", required=True, help="Path to model.svg")
    ap.add_argument("--image", required=True, help="Path to image (e.g., F2_scaled.png)")
    ap.add_argument("--out", required=True, help="Output image path")
    ap.add_argument(
        "--door_mode",
        choices=("strict", "robust"),
        default="robust",
        help="Door label extraction mode (same as cubicasa5k_export_yolo.py).",
    )
    args = ap.parse_args()

    svg_path = Path(args.svg)
    img_path = Path(args.image)
    out_path = Path(args.out)

    if not svg_path.exists():
        raise SystemExit(f"SVG not found: {svg_path}")
    if not img_path.exists():
        raise SystemExit(f"Image not found: {img_path}")

    img = cv2.imread(str(img_path))
    if img is None:
        raise SystemExit(f"Unable to read image: {img_path}")
    h, w = img.shape[:2]

    # Compute scale from SVG to image.
    import xml.etree.ElementTree as ET

    tree = ET.parse(svg_path)
    svg_root = tree.getroot()
    svg_w, svg_h = get_svg_size(svg_root)
    sx = w / svg_w
    sy = h / svg_h

    classes = [("door", (0, 140, 0)), ("window", (255, 0, 0))]
    for class_name, color in classes:
        boxes, _ = extract_boxes(svg_path, class_name, door_mode=args.door_mode)
        boxes = [b.scale(sx, sy) for b in boxes]
        draw_boxes(img, boxes, w, h, color, class_name)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), img)
    print(f"Wrote overlay to {out_path}")


if __name__ == "__main__":
    main()
