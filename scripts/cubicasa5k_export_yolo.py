import argparse
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

import cv2

try:
    from svgpathtools import parse_path
except Exception:  # pragma: no cover - optional dependency
    parse_path = None


LABEL_SYNONYMS = {
    "door": ["door", "door swing", "threshold"],
    "window": ["window", "window regular", "glass", "fenetre"],
    "bed": ["bed", "lit"],
}


@dataclass
class Box:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def scale(self, sx: float, sy: float) -> "Box":
        return Box(self.xmin * sx, self.ymin * sy, self.xmax * sx, self.ymax * sy)


def iter_svgs(root: Path) -> List[Path]:
    return sorted(root.rglob("model.svg"))


def normalize_label(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum() or ch.isspace()).strip()


def parse_points(points: str) -> Optional[Box]:
    coords = []
    for part in points.replace(",", " ").split():
        try:
            coords.append(float(part))
        except ValueError:
            return None
    if len(coords) < 4:
        return None
    xs = coords[0::2]
    ys = coords[1::2]
    return Box(min(xs), min(ys), max(xs), max(ys))


def parse_rect(elem) -> Optional[Box]:
    try:
        x = float(elem.get("x", "0"))
        y = float(elem.get("y", "0"))
        w = float(elem.get("width"))
        h = float(elem.get("height"))
    except (TypeError, ValueError):
        return None
    return Box(x, y, x + w, y + h)


def parse_circle(elem) -> Optional[Box]:
    try:
        cx = float(elem.get("cx"))
        cy = float(elem.get("cy"))
        r = float(elem.get("r"))
    except (TypeError, ValueError):
        return None
    return Box(cx - r, cy - r, cx + r, cy + r)


def parse_ellipse(elem) -> Optional[Box]:
    try:
        cx = float(elem.get("cx"))
        cy = float(elem.get("cy"))
        rx = float(elem.get("rx"))
        ry = float(elem.get("ry"))
    except (TypeError, ValueError):
        return None
    return Box(cx - rx, cy - ry, cx + rx, cy + ry)


def parse_line(elem) -> Optional[Box]:
    try:
        x1 = float(elem.get("x1"))
        y1 = float(elem.get("y1"))
        x2 = float(elem.get("x2"))
        y2 = float(elem.get("y2"))
    except (TypeError, ValueError):
        return None
    return Box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def parse_path_box(d: str) -> Optional[Box]:
    if parse_path is None:
        return None
    try:
        path = parse_path(d)
    except Exception:
        return None
    xmin, xmax, ymin, ymax = path.bbox()
    return Box(xmin, ymin, xmax, ymax)


def get_svg_size(root) -> Tuple[float, float]:
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [p for p in viewbox.replace(",", " ").split() if p]
        if len(parts) == 4:
            return float(parts[2]), float(parts[3])
    width = root.get("width")
    height = root.get("height")
    if width and height:
        return float(width), float(height)
    raise ValueError("SVG size not found")


def label_matches(candidates: Iterable[str], class_name: str) -> bool:
    synonyms = LABEL_SYNONYMS[class_name]
    for cand in candidates:
        c = normalize_label(cand)
        for syn in synonyms:
            if syn in c:
                return True
    return False


def extract_boxes(svg_path: Path, class_name: str) -> Tuple[List[Box], int]:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    parent_map = {c: p for p in root.iter() for c in p}
    boxes = []
    skipped_paths = 0

    for elem in root.iter():
        candidates = []
        for attr in ("class", "id", "{http://www.inkscape.org/namespaces/inkscape}label"):
            val = elem.get(attr)
            if val:
                candidates.append(val)
        parent = parent_map.get(elem)
        while parent is not None:
            for attr in ("class", "id", "{http://www.inkscape.org/namespaces/inkscape}label"):
                val = parent.get(attr)
                if val:
                    candidates.append(val)
            parent = parent_map.get(parent)

        if not label_matches(candidates, class_name):
            continue

        tag = elem.tag.split("}")[-1]
        box = None
        if tag == "polygon" and elem.get("points"):
            box = parse_points(elem.get("points"))
        elif tag == "rect":
            box = parse_rect(elem)
        elif tag == "circle":
            box = parse_circle(elem)
        elif tag == "ellipse":
            box = parse_ellipse(elem)
        elif tag == "line":
            box = parse_line(elem)
        elif tag == "path":
            d = elem.get("d")
            if d:
                box = parse_path_box(d)
                if box is None and parse_path is None:
                    skipped_paths += 1

        if box:
            boxes.append(box)

    return boxes, skipped_paths


def to_yolo(box: Box, w: int, h: int) -> Tuple[float, float, float, float]:
    xmin = max(0.0, min(box.xmin, w))
    ymin = max(0.0, min(box.ymin, h))
    xmax = max(0.0, min(box.xmax, w))
    ymax = max(0.0, min(box.ymax, h))

    bw = max(1.0, xmax - xmin)
    bh = max(1.0, ymax - ymin)
    cx = xmin + bw / 2.0
    cy = ymin + bh / 2.0

    return cx / w, cy / h, bw / w, bh / h


def find_image(folder: Path) -> Optional[Path]:
    for name in ("image.png", "image.jpg", "image.jpeg", "original.png", "original.jpg"):
        path = folder / name
        if path.exists():
            return path
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images = sorted(folder.glob(ext))
        if images:
            return images[0]
    return None


def split_paths(paths: List[Path], val_ratio: float, seed: int) -> Tuple[List[Path], List[Path]]:
    rng = random.Random(seed)
    paths = list(paths)
    rng.shuffle(paths)
    n_val = int(len(paths) * val_ratio)
    return paths[n_val:], paths[:n_val]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw/cubicasa5k", help="CubiCasa5K root folder")
    ap.add_argument("--out", default="data/processed/cubicasa5k_yolo", help="Output folder")
    ap.add_argument("--val_ratio", type=float, default=0.1, help="Validation split ratio")
    ap.add_argument("--seed", type=int, default=42, help="Shuffle seed")
    args = ap.parse_args()

    root = Path(args.root)
    svgs = iter_svgs(root)
    if not svgs:
        raise SystemExit(f"No model.svg found under {root}")

    out = Path(args.out)
    img_train = out / "images" / "train"
    img_val = out / "images" / "val"
    lbl_train = out / "labels" / "train"
    lbl_val = out / "labels" / "val"
    for p in (img_train, img_val, lbl_train, lbl_val):
        p.mkdir(parents=True, exist_ok=True)

    train_svgs, val_svgs = split_paths(svgs, args.val_ratio, args.seed)

    class_names = ["door", "window", "bed"]
    class_to_id = {c: i for i, c in enumerate(class_names)}

    def export_one(svg_path: Path, split: str):
        folder = svg_path.parent
        image_path = find_image(folder)
        if image_path is None:
            return 0, 0

        img = cv2.imread(str(image_path))
        if img is None:
            return 0, 0
        h, w = img.shape[:2]

        tree = ET.parse(svg_path)
        svg_root = tree.getroot()
        svg_w, svg_h = get_svg_size(svg_root)
        sx = w / svg_w
        sy = h / svg_h

        lines = []
        seen = set()
        skipped_paths = 0
        for class_name in class_names:
            boxes, skipped = extract_boxes(svg_path, class_name)
            skipped_paths += skipped
            for box in boxes:
                box_scaled = box.scale(sx, sy)
                cx, cy, bw, bh = to_yolo(box_scaled, w, h)
                if bw <= 0 or bh <= 0:
                    continue
                key = (
                    class_to_id[class_name],
                    round(cx, 6),
                    round(cy, 6),
                    round(bw, 6),
                    round(bh, 6),
                )
                if key in seen:
                    continue
                seen.add(key)
                lines.append(f"{key[0]} {key[1]:.6f} {key[2]:.6f} {key[3]:.6f} {key[4]:.6f}")

        if not lines:
            return 0, skipped_paths

        out_img = (img_train if split == "train" else img_val) / f"{folder.name}.png"
        out_lbl = (lbl_train if split == "train" else lbl_val) / f"{folder.name}.txt"
        cv2.imwrite(str(out_img), img)
        out_lbl.write_text("\n".join(lines), encoding="utf-8")
        return 1, skipped_paths

    total = 0
    total_skipped_paths = 0
    for svg in train_svgs:
        c, s = export_one(svg, "train")
        total += c
        total_skipped_paths += s
    for svg in val_svgs:
        c, s = export_one(svg, "val")
        total += c
        total_skipped_paths += s

    (out / "dataset.yaml").write_text(
        "\n".join(
            [
                f"path: {out.as_posix()}",
                "train: images/train",
                "val: images/val",
                f"nc: {len(class_names)}",
                "names: [door, window, bed]",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Exported {total} images to {out}")
    if total_skipped_paths and parse_path is None:
        print("WARNING: Some path elements were skipped. Install svgpathtools to handle paths.")


if __name__ == "__main__":
    main()
