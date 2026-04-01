import argparse
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple
import xml.etree.ElementTree as ET

import cv2

try:
    from svgpathtools import parse_path
except Exception:  # pragma: no cover - optional dependency
    parse_path = None


LABEL_SYNONYMS = {
    "door": ["door", "door swing", "threshold"],
    "window": ["window", "window regular", "glass", "fenetre"],
}


@dataclass
class Box:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    def scale(self, sx: float, sy: float) -> "Box":
        return Box(self.xmin * sx, self.ymin * sy, self.xmax * sx, self.ymax * sy)

    def apply_matrix(self, m: Tuple[float, float, float, float, float, float]) -> "Box":
        pts = (
            _apply_matrix_point(self.xmin, self.ymin, m),
            _apply_matrix_point(self.xmax, self.ymin, m),
            _apply_matrix_point(self.xmax, self.ymax, m),
            _apply_matrix_point(self.xmin, self.ymax, m),
        )
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return Box(min(xs), min(ys), max(xs), max(ys))


IDENTITY_MATRIX = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _apply_matrix_point(
    x: float, y: float, m: Tuple[float, float, float, float, float, float]
) -> Tuple[float, float]:
    a, b, c, d, e, f = m
    return a * x + c * y + e, b * x + d * y + f


def _mul_matrix(
    left: Tuple[float, float, float, float, float, float],
    right: Tuple[float, float, float, float, float, float],
) -> Tuple[float, float, float, float, float, float]:
    la, lb, lc, ld, le, lf = left
    ra, rb, rc, rd, re, rf = right
    return (
        la * ra + lc * rb,
        lb * ra + ld * rb,
        la * rc + lc * rd,
        lb * rc + ld * rd,
        la * re + lc * rf + le,
        lb * re + ld * rf + lf,
    )


def _parse_floats(raw: str) -> List[float]:
    nums = []
    for token in re.split(r"[,\s]+", raw.strip()):
        if not token:
            continue
        try:
            nums.append(float(token))
        except ValueError:
            pass
    return nums


def parse_transform(transform: Optional[str]) -> Tuple[float, float, float, float, float, float]:
    if not transform:
        return IDENTITY_MATRIX
    out = IDENTITY_MATRIX
    for cmd, args in re.findall(r"([a-zA-Z]+)\(([^)]*)\)", transform):
        values = _parse_floats(args)
        cmd = cmd.lower()
        if cmd == "matrix" and len(values) == 6:
            out = _mul_matrix(out, tuple(values))  # type: ignore[arg-type]
        elif cmd == "translate" and values:
            tx = values[0]
            ty = values[1] if len(values) > 1 else 0.0
            out = _mul_matrix(out, (1.0, 0.0, 0.0, 1.0, tx, ty))
    return out


def _make_cumul_fn(root) -> Callable:
    """Return a cumulative_transform(elem) function for the given SVG root."""
    parent_map = {c: p for p in root.iter() for c in p}
    cache: dict = {}

    def cumulative_transform(elem):
        if elem in cache:
            return cache[elem]
        parent = parent_map.get(elem)
        base = cumulative_transform(parent) if parent is not None else IDENTITY_MATRIX
        cache[elem] = _mul_matrix(base, parse_transform(elem.get("transform")))
        return cache[elem]

    return cumulative_transform


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


def get_svg_viewbox(root) -> Tuple[float, float, float, float]:
    viewbox = root.get("viewBox")
    if viewbox:
        parts = [p for p in viewbox.replace(",", " ").split() if p]
        if len(parts) == 4:
            return float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
    width = root.get("width")
    height = root.get("height")
    if width and height:
        return 0.0, 0.0, float(width), float(height)
    raise ValueError("SVG size not found")


def get_svg_size(root) -> Tuple[float, float]:
    _, _, w, h = get_svg_viewbox(root)
    return w, h


def _align_to_frac(align: str) -> float:
    key = align.lower()
    if key in ("min", "xmin", "left", "xleft", "ymin", "top"):
        return 0.0
    if key in ("mid", "center", "middle", "xmid", "ymid"):
        return 0.5
    if key in ("max", "xmax", "right", "xright", "ymax", "bottom"):
        return 1.0
    raise ValueError(f"Unknown align: {align}")


def svg_to_image_transform(
    root,
    img_w: int,
    img_h: int,
    fit: str,
    align_x: str,
    align_y: str,
    offset_x: float,
    offset_y: float,
) -> tuple[float, float, float, float]:
    """Map SVG viewBox coords -> image coords.

    fit="stretch": non-uniform scale to fill (legacy behavior).
    fit="meet": preserve aspect ratio, center with padding.
    """
    svg_min_x, svg_min_y, svg_w, svg_h = get_svg_viewbox(root)
    if fit == "stretch":
        sx = img_w / svg_w
        sy = img_h / svg_h
        ox = -svg_min_x * sx + offset_x
        oy = -svg_min_y * sy + offset_y
        return sx, sy, ox, oy
    if fit == "meet":
        s = min(img_w / svg_w, img_h / svg_h)
        pad_x = (img_w - svg_w * s) * _align_to_frac(align_x)
        pad_y = (img_h - svg_h * s) * _align_to_frac(align_y)
        ox = pad_x - svg_min_x * s + offset_x
        oy = pad_y - svg_min_y * s + offset_y
        return s, s, ox, oy
    raise ValueError(f"Unknown fit mode: {fit}")


def get_floor_groups(root) -> dict:
    """Return {floor_num: element} for all 'Floorplan Floor-N' groups in the SVG.

    Falls back to {1: root} if no floor groups are found (single-floor SVGs).
    """
    floors = {}
    for elem in root.iter():
        cls = elem.get("class", "")
        if "Floorplan Floor-" in cls:
            try:
                n = int(cls.split("Floor-")[1].split()[0])
                floors[n] = elem
            except (IndexError, ValueError):
                pass
    if not floors:
        floors[1] = root
    return floors


def _collect_bbox_from_subtree(subtree, cumulative_transform, vx, vy, vw, vh):
    """Collect element bboxes from *subtree*, clip to viewBox, return xs, ys lists."""
    xs: List[float] = []
    ys: List[float] = []
    for elem in subtree.iter():
        tag = elem.tag.split("}")[-1]
        box: Optional[Box] = None
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
        if box is None:
            continue
        box = box.apply_matrix(cumulative_transform(elem))
        for px, py in [(box.xmin, box.ymin), (box.xmax, box.ymin),
                       (box.xmax, box.ymax), (box.xmin, box.ymax)]:
            if vx <= px <= vx + vw and vy <= py <= vy + vh:
                xs.append(px)
                ys.append(py)
    return xs, ys


def compute_svg_content_bbox(
    svg_path: Path, floor_num: Optional[int] = None
) -> Tuple[float, float, float, float]:
    """Return (xmin, ymin, xmax, ymax) of rendered elements, clipped to SVG viewBox.

    If *floor_num* is given, only elements within that floor's group are considered.
    Falls back to full viewBox if no elements are found.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()
    vx, vy, vw, vh = get_svg_viewbox(root)
    cumulative_transform = _make_cumul_fn(root)

    if floor_num is not None:
        floors = get_floor_groups(root)
        subtree = floors.get(floor_num, root)
    else:
        subtree = root

    xs, ys = _collect_bbox_from_subtree(subtree, cumulative_transform, vx, vy, vw, vh)

    if not xs:
        return vx, vy, vx + vw, vy + vh  # fallback: full viewBox

    return (
        max(vx, min(xs)),
        max(vy, min(ys)),
        min(vx + vw, max(xs)),
        min(vy + vh, max(ys)),
    )


def label_matches(candidates: Iterable[str], class_name: str) -> bool:
    synonyms = LABEL_SYNONYMS[class_name]
    for cand in candidates:
        c = normalize_label(cand)
        for syn in synonyms:
            if syn in c:
                return True
    return False


def _is_door_subcomponent(candidates: Iterable[str], door_mode: str) -> bool:
    for cand in candidates:
        c = cand.lower()
        if "threshold" in c:
            return True
        if door_mode == "robust" and "panel" in c:
            return True
    return False


def _is_window_subcomponent(candidates: Iterable[str]) -> bool:
    for cand in candidates:
        c = cand.lower()
        if "glass" in c:
            return True
    return False


def extract_boxes(
    svg_path: Path, class_name: str, door_mode: str = "robust",
    floor_num: Optional[int] = None,
) -> Tuple[List[Box], int]:
    tree = ET.parse(svg_path)
    root = tree.getroot()
    cumulative_transform = _make_cumul_fn(root)
    parent_map = {c: p for p in root.iter() for c in p}
    boxes = []
    skipped_paths = 0

    if floor_num is not None:
        floors = get_floor_groups(root)
        subtree = floors.get(floor_num, root)
    else:
        subtree = root
    for elem in subtree.iter():
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

        if class_name == "door" and not _is_door_subcomponent(candidates, door_mode):
            continue
        if class_name == "window" and not _is_window_subcomponent(candidates):
            continue

        tag = elem.tag.split("}")[-1]
        if class_name == "door" and tag == "path":
            continue
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
            box = box.apply_matrix(cumulative_transform(elem))
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
    """Legacy single-image finder kept for backward compatibility."""
    for name in ("image.png", "image.jpg", "image.jpeg", "original.png", "original.jpg"):
        path = folder / name
        if path.exists():
            return path
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.bmp"):
        images = sorted(folder.glob(ext))
        if images:
            return images[0]
    return None


def _floor_num_from_name(name: str) -> Optional[int]:
    """Extract floor number from filename like 'F1_original.png' → 1."""
    import re as _re
    m = _re.match(r"[Ff](\d+)[_\-]", name)
    return int(m.group(1)) if m else None


def get_floor_images(folder: Path) -> dict:
    """Return {floor_num: [candidate_paths...]} for all Fx_*.png/jpg in folder.

    Prefers *_scaled.* before *_original.* within each floor.
    """
    result: dict = {}
    for ext in ("*.png", "*.jpg", "*.jpeg"):
        for p in folder.glob(ext):
            n = _floor_num_from_name(p.name)
            if n is None:
                continue
            result.setdefault(n, []).append(p)
    # Sort each floor's candidates: _scaled first, then _original
    for n in result:
        result[n].sort(key=lambda p: (0 if "_scaled" in p.name else 1, p.name))
    return result


def select_best_image(folder: Path, content_w: float, content_h: float,
                      floor_num: int = 1) -> Optional[Tuple[Path, float]]:
    """Pick the best image for *floor_num* matching content_w/content_h aspect ratio.

    Returns (image_path, aspect_diff) or None.
    """
    target_aspect = content_w / content_h if content_h > 0 else 1.0
    floor_imgs = get_floor_images(folder)

    # Try exact floor match first, then any floor
    candidates_paths = floor_imgs.get(floor_num, [])
    if not candidates_paths:
        for paths in floor_imgs.values():
            candidates_paths.extend(paths)

    candidates = []
    for img_path in candidates_paths:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        img_aspect = w / h if h > 0 else 1.0
        aspect_diff = abs(img_aspect / target_aspect - 1.0)
        priority = 0 if "_scaled" in img_path.name else 1
        candidates.append((aspect_diff, priority, img_path))

    if not candidates:
        return None
    candidates.sort()
    best_diff, _, best_path = candidates[0]
    return best_path, best_diff


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
    ap.add_argument(
        "--door_mode",
        choices=("strict", "robust"),
        default="robust",
        help="Door label extraction: strict=threshold only, robust=threshold+panel (no arcs).",
    )
    ap.add_argument(
        "--max_aspect_diff",
        type=float,
        default=0.20,
        help=(
            "Maximum allowed aspect-ratio mismatch between SVG content bbox and chosen image "
            "(|img_aspect/content_aspect - 1|). Images exceeding this are skipped. "
            "Default 0.20 keeps high_quality/architectural (~5-8%%) and excludes colorful (~40%%)."
        ),
    )
    # Legacy overlay arguments kept for backward compatibility with overlay_svg_boxes.py
    ap.add_argument("--fit", choices=("meet", "stretch"), default="meet",
                    help="[overlay only] SVG->image fit mode.")
    ap.add_argument("--align_x", choices=("min", "mid", "max"), default="mid")
    ap.add_argument("--align_y", choices=("min", "mid", "max"), default="mid")
    ap.add_argument("--offset_x", type=float, default=0.0)
    ap.add_argument("--offset_y", type=float, default=0.0)
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

    class_names = ["door", "window"]
    class_to_id = {c: i for i, c in enumerate(class_names)}

    skipped_aspect = 0
    skipped_no_image = 0
    skipped_no_boxes = 0

    def export_one(svg_path: Path, split: str):
        nonlocal skipped_aspect, skipped_no_image, skipped_no_boxes

        folder = svg_path.parent

        # --- Get SVG viewBox dimensions (the coordinate space of annotations) ---
        try:
            tree = ET.parse(svg_path)
            svg_root = tree.getroot()
            _, _, svg_w, svg_h = get_svg_viewbox(svg_root)
        except Exception:
            return 0, 0
        if svg_w <= 0 or svg_h <= 0:
            return 0, 0

        # --- Select best image: prefer F1_scaled (closest aspect to SVG viewBox) ---
        result = select_best_image(folder, svg_w, svg_h, floor_num=1)
        if result is None:
            skipped_no_image += 1
            return 0, 0
        image_path, aspect_diff = result

        if aspect_diff > args.max_aspect_diff:
            skipped_aspect += 1
            return 0, 0

        img = cv2.imread(str(image_path))
        if img is None:
            skipped_no_image += 1
            return 0, 0
        img_h, img_w = img.shape[:2]

        # --- Direct stretch: SVG viewBox coords -> image pixels ---
        # CubiCasa5k annotations are in SVG viewBox coordinate space.
        # F1_scaled is the closest rendering; distortion is typically <3%.
        sx = img_w / svg_w
        sy = img_h / svg_h
        ox, oy = 0.0, 0.0

        # --- Extract all doors/windows (all floors) ---
        lines = []
        seen = set()
        skipped_paths = 0
        for class_name in class_names:
            boxes, skipped = extract_boxes(svg_path, class_name, door_mode=args.door_mode)
            skipped_paths += skipped
            for box in boxes:
                box_scaled = Box(
                    box.xmin * sx + ox,
                    box.ymin * sy + oy,
                    box.xmax * sx + ox,
                    box.ymax * sy + oy,
                )
                cx, cy, bw, bh = to_yolo(box_scaled, img_w, img_h)
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
            skipped_no_boxes += 1
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
                "names: [door, window]",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Exported {total} images to {out}")
    print(f"Skipped: {skipped_aspect} (aspect ratio > {args.max_aspect_diff:.0%}), "
          f"{skipped_no_image} (no image), {skipped_no_boxes} (no annotations)")
    if total_skipped_paths and parse_path is None:
        print("WARNING: Some path elements were skipped. Install svgpathtools to handle paths.")


if __name__ == "__main__":
    main()
