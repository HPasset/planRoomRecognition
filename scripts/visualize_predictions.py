"""Visualise les prédictions COCO 1.0 par-dessus les plans originaux.

Prend un fichier COCO 1.0 (généré par predict_for_annotation.py) + le dossier
des plans, et produit des PNG overlay (polygones semi-transparents + labels)
prêts à inspecter visuellement.

Usage :
    python scripts/visualize_predictions.py \\
        --coco_json /tmp/test_fr_domain_gap.json \\
        --plans_dir data/raw/plans_fr \\
        --out_dir /tmp/viz_fr
    open /tmp/viz_fr
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


# Palette par classe (même que eval_visualize.py)
PALETTE = np.array([
    [0,   0,   0],     # 0 Background
    [80,  80,  80],    # 1 Wall
    [255, 200, 100],   # 2 Kitchen     (orange)
    [120, 220, 100],   # 3 LivingRoom  (vert)
    [100, 150, 255],   # 4 BedRoom     (bleu)
    [200, 100, 200],   # 5 Bath        (rose)
    [255, 220, 0],     # 6 Entry       (jaune)
    [180, 120, 80],    # 7 Storage     (marron)
    [100, 100, 100],   # 8 Garage      (gris)
    [120, 220, 220],   # 9 Outdoor     (cyan)
], dtype=np.uint8)

ALPHA = 0.40   # transparence du remplissage polygone


def _label_for(category_id: int, categories: list[dict]) -> str:
    for c in categories:
        if c["id"] == category_id:
            return c["name"]
    return f"unknown_{category_id}"


def _polygon_centroid(points_xy: np.ndarray) -> tuple[int, int]:
    M = cv2.moments(points_xy.reshape(-1, 1, 2))
    if M["m00"] == 0:
        x = int(points_xy[:, 0].mean())
        y = int(points_xy[:, 1].mean())
    else:
        x = int(M["m10"] / M["m00"])
        y = int(M["m01"] / M["m00"])
    return x, y


def _draw_label_box(canvas: np.ndarray, text: str, x: int, y: int,
                     bg_color: tuple[int, int, int]):
    """Draw a small colored badge with white text behind, centered at (x, y)."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 1
    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    pad_x, pad_y = 6, 4
    x0 = max(0, x - tw // 2 - pad_x)
    y0 = max(0, y - th // 2 - pad_y)
    x1 = x0 + tw + 2 * pad_x
    y1 = y0 + th + 2 * pad_y + baseline
    # Background rectangle
    cv2.rectangle(canvas, (x0, y0), (x1, y1), bg_color, thickness=-1)
    cv2.rectangle(canvas, (x0, y0), (x1, y1), (255, 255, 255), thickness=1)
    # Text
    text_x = x0 + pad_x
    text_y = y1 - pad_y - baseline
    cv2.putText(canvas, text, (text_x, text_y), font, scale,
                (255, 255, 255), thickness, cv2.LINE_AA)


def visualize_one(
    plan_path: Path, image_id: int, annotations: list[dict],
    categories: list[dict], confidence_min: float,
) -> np.ndarray | None:
    """Build the overlay image for a single plan."""
    img = cv2.imread(str(plan_path))
    if img is None:
        return None
    overlay = img.copy()

    # Filter annotations for this image
    anns = [a for a in annotations if a["image_id"] == image_id]
    # Sort by area desc → bigger polygons drawn first (smaller on top)
    anns.sort(key=lambda a: -a.get("area", 0))

    # Pass 1 : remplissage semi-transparent
    for ann in anns:
        score = ann.get("score", 1.0)
        if score < confidence_min:
            continue
        cat_id = ann["category_id"]
        color = tuple(int(c) for c in PALETTE[cat_id])
        for seg in ann["segmentation"]:
            pts = np.asarray(seg, dtype=np.float32).reshape(-1, 2)
            if pts.shape[0] < 3:
                continue
            pts_int = np.round(pts).astype(np.int32)
            cv2.fillPoly(overlay, [pts_int], color)

    # Blend overlay onto original
    blended = cv2.addWeighted(overlay, ALPHA, img, 1 - ALPHA, 0)

    # Pass 2 : contours + labels
    for ann in anns:
        score = ann.get("score", 1.0)
        if score < confidence_min:
            continue
        cat_id = ann["category_id"]
        cat_name = _label_for(cat_id, categories)
        color = tuple(int(c) for c in PALETTE[cat_id])
        for seg in ann["segmentation"]:
            pts = np.asarray(seg, dtype=np.float32).reshape(-1, 2)
            if pts.shape[0] < 3:
                continue
            pts_int = np.round(pts).astype(np.int32)
            cv2.polylines(blended, [pts_int], True, color, thickness=2,
                          lineType=cv2.LINE_AA)
            cx, cy = _polygon_centroid(pts_int)
            label = f"{cat_name} {score:.2f}" if score < 1.0 else cat_name
            _draw_label_box(blended, label, cx, cy, color)

    return blended


def build_index_html(out_dir: Path, viz_files: list[Path], coco: dict):
    """Generate a small HTML page to browse all visualizations side-by-side."""
    rows = []
    for f in sorted(viz_files):
        # Find image_id from filename
        original = next((img for img in coco["images"]
                         if Path(img["file_name"]).stem == f.stem.replace("_viz", "")),
                        None)
        n_anns = 0
        if original:
            n_anns = sum(1 for a in coco["annotations"]
                         if a["image_id"] == original["id"])
        rows.append(
            f'<div class="card"><h3>{f.stem}</h3>'
            f'<p class="meta">{n_anns} polygones détectés</p>'
            f'<img src="{f.name}" /></div>'
        )

    legend = " · ".join(
        f'<span class="lg" style="background:rgb({PALETTE[i,0]},{PALETTE[i,1]},{PALETTE[i,2]})">'
        f'{cat["name"]}</span>'
        for i, cat in enumerate(coco["categories"])
    )

    html = f"""<!doctype html>
<html><head><meta charset='utf-8'>
<title>Visualisation prédictions — domain gap test FR</title>
<style>
  body {{ font-family: -apple-system, sans-serif; padding: 20px; background: #f5f5f7; color: #222; }}
  h1 {{ color: #211B57; }}
  .legend {{ margin: 20px 0; }}
  .lg {{ display: inline-block; padding: 4px 8px; margin: 2px; color: white; border-radius: 4px; font-size: 12px; }}
  .card {{ margin: 30px 0; padding: 16px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
  .card h3 {{ margin: 0 0 4px; color: #211B57; }}
  .meta {{ color: #666; font-size: 13px; margin: 0 0 12px; }}
  .card img {{ max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px; }}
</style></head>
<body>
<h1>Stage A — visualisation prédictions sur plans FR</h1>
<p>Modèle : <code>best.pt</code> (CubiCasa val mIoU ~0.51).
   Plans : {len(coco["images"])}.
   Polygones totaux : {len(coco["annotations"])}.</p>
<div class="legend">{legend}</div>
{''.join(rows)}
</body></html>"""

    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coco_json", required=True,
                    help="JSON COCO 1.0 généré par predict_for_annotation.py")
    ap.add_argument("--plans_dir", required=True,
                    help="Dossier des plans originaux")
    ap.add_argument("--out_dir", required=True,
                    help="Dossier de sortie pour les visualisations")
    ap.add_argument("--confidence_min", type=float, default=0.0,
                    help="Filtre les annotations < ce score (default 0.0 = toutes)")
    args = ap.parse_args()

    coco_path = Path(args.coco_json)
    plans_dir = Path(args.plans_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    coco = json.loads(coco_path.read_text())
    images = coco.get("images", [])
    annotations = coco.get("annotations", [])
    categories = coco.get("categories", [])

    if not images:
        raise SystemExit("No images in COCO JSON")

    print(f"Visualizing {len(images)} plans...")
    viz_files: list[Path] = []
    for img in images:
        plan_path = plans_dir / img["file_name"]
        if not plan_path.exists():
            print(f"  ⚠ Skipping (not found): {plan_path}")
            continue
        out_img = visualize_one(plan_path, img["id"], annotations, categories,
                                 args.confidence_min)
        if out_img is None:
            print(f"  ⚠ Skipping (unreadable): {plan_path}")
            continue
        out_path = out_dir / f"{plan_path.stem}_viz.png"
        cv2.imwrite(str(out_path), out_img)
        viz_files.append(out_path)
        n = sum(1 for a in annotations if a["image_id"] == img["id"])
        print(f"  ✓ {plan_path.name} → {out_path.name} ({n} polygones)")

    if viz_files:
        build_index_html(out_dir, viz_files, coco)
        print(f"\n✓ Wrote {len(viz_files)} visualizations + index.html to {out_dir}")
        print(f"  Open with: open '{out_dir / 'index.html'}'")
    else:
        print("\n⚠ No visualizations produced.")


if __name__ == "__main__":
    main()
