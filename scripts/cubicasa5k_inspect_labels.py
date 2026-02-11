import argparse
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET


def iter_svgs(root: Path):
    return sorted(root.rglob("model.svg"))


def normalize_label(s: str) -> str:
    return "".join(ch.lower() for ch in s if ch.isalnum() or ch.isspace()).strip()


def extract_labels(svg_path: Path):
    tree = ET.parse(svg_path)
    root = tree.getroot()
    parent_map = {c: p for p in root.iter() for c in p}

    labels = []
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
        for c in candidates:
            labels.append(normalize_label(c))
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="data/raw/cubicasa5k", help="CubiCasa5K root folder")
    ap.add_argument("--top", type=int, default=50, help="Top N labels")
    args = ap.parse_args()

    root = Path(args.root)
    svgs = iter_svgs(root)
    if not svgs:
        raise SystemExit(f"No model.svg found under {root}")

    counter = Counter()
    for svg in svgs:
        labels = extract_labels(svg)
        counter.update(labels)

    print(f"Found {len(counter)} unique labels")
    for label, count in counter.most_common(args.top):
        if not label:
            continue
        print(f"{count:6d} | {label}")


if __name__ == "__main__":
    main()
