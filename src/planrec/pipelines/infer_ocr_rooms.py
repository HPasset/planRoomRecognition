import argparse
import json
import sys
from pathlib import Path

import cv2

if __package__ is None:
    # Allow running as a script: add repo/src to sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from planrec.ocr.engine import OCREngine
from planrec.ocr.postprocess import postprocess_ocr_items


def make_jsonable(obj):
    """
    Convert recursively numpy types to native Python types
    so json.dumps() never crashes.
    """
    import numpy as np

    if isinstance(obj, dict):
        return {k: make_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [make_jsonable(v) for v in obj]

    if isinstance(obj, tuple):
        return [make_jsonable(v) for v in obj]

    if isinstance(obj, (np.integer,)):
        return int(obj)

    if isinstance(obj, (np.floating,)):
        return float(obj)

    return obj


def draw_boxes(img_bgr, hits):
    """Draw bbox + label on the original image."""
    out = img_bgr.copy()
    for h in hits:
        bbox = h["bbox"]  # [[x,y],...]
        pts = [(int(p[0]), int(p[1])) for p in bbox]
        for i in range(4):
            cv2.line(out, pts[i], pts[(i + 1) % 4], (0, 128, 0), 2)
        # label at top-left
        x, y = pts[0]
        cv2.putText(
            out,
            h["room_type"],
            (x, max(0, y - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 128, 0),
            2,
            cv2.LINE_AA,
        )
    return out


def list_images(input_path: Path):
    if input_path.is_dir():
        imgs = []
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.tif", "*.tiff"):
            imgs.extend(input_path.glob(ext))
        return sorted(imgs)
    return [input_path]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Image file or folder (png/jpg/...)")
    ap.add_argument("--output", required=True, help="Output folder for JSON results")
    ap.add_argument("--vis", action="store_true", help="Also export annotated images")
    ap.add_argument("--vis_dir", default="", help="Folder for visualizations (default: <output>/vis)")
    ap.add_argument("--lang", default="fr", help="OCR language, e.g. fr or fr,en")
    ap.add_argument("--confidence_min", type=float, default=0.35, help="Minimum OCR confidence")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    vis_dir = Path(args.vis_dir) if args.vis_dir else out_dir / "vis"
    if args.vis:
        vis_dir.mkdir(parents=True, exist_ok=True)

    langs = [x.strip() for x in args.lang.split(",") if x.strip()]
    engine = OCREngine(langs=langs, gpu=False)

    images = list_images(in_path)
    if not images:
        raise SystemExit("No images found. Put plan images in data/raw.")

    for img_path in images:
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            print(f"[SKIP] Unreadable: {img_path}")
            continue

        ocr_items = engine.read(img_bgr, preprocess=True)

        print("=== OCR RAW ===")
        for item in ocr_items:
            print(f"{item['confidence']:.2f} | {item['text']}")
        print("===============")

        hits = postprocess_ocr_items(ocr_items, confidence_min=args.confidence_min)

        payload = {
            "image": img_path.name,
            "num_ocr_items": len(ocr_items),
            "num_room_hits": len(hits),
            "detections": hits,
        }

        # secure JSON serialization (numpy types, etc.)
        payload = make_jsonable(payload)

        out_json = out_dir / f"{img_path.stem}.json"
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] {img_path.name} -> {out_json.name} (hits={len(hits)})")

        if args.vis:
            annotated = draw_boxes(img_bgr, hits)
            out_img = vis_dir / f"{img_path.stem}_vis.png"
            cv2.imwrite(str(out_img), annotated)


if __name__ == "__main__":
    main()
