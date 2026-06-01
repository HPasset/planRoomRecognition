"""Wall detection comparison: M2F (batIA) vs FT (FloorplanTransformation).

Runs M2F inference on 8 test plans and builds comparison visualizations.

Run from /Users/hadrienpasset/Developer/planRoomRecognition with the venv:
    .venv/bin/python experiments/wall_detection_eval/run_comparison.py
"""
from __future__ import annotations
import time
import traceback
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

from src.segmentation.inference import SegmentationInference
from src.segmentation.schema import RoomDetection


# ---- Constants reused from app/streamlit_app.py (do NOT modify batIA code) ----
PALETTE = np.array([
    [0, 0, 0],         # 0 Background
    [255, 0, 255],     # 1 Wall
    [255, 200, 100],   # 2 Kitchen
    [120, 220, 100],   # 3 LivingRoom
    [100, 150, 255],   # 4 BedRoom
    [200, 100, 200],   # 5 Bath
    [255, 220, 0],     # 6 Entry
    [180, 120, 80],    # 7 Storage
    [100, 100, 100],   # 8 Garage
    [120, 220, 220],   # 9 Outdoor
], dtype=np.uint8)
ALPHA = 0.40

DEFAULT_CHECKPOINT = "runs/segmentation/stage_b_finetune_v1/checkpoints/best.pt"
IMAGE_SIZE = 768

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_ROOT = Path(__file__).resolve().parent
TEST_PLANS_DIR = EVAL_ROOT / "test_plans"
OUTPUTS_DIR = EVAL_ROOT / "outputs"
M2F_OUT_DIR = OUTPUTS_DIR / "m2f"
FT_OUT_DIR = OUTPUTS_DIR / "ft"
PER_PLAN_DIR = OUTPUTS_DIR / "per_plan"


def _polygon_centroid(pts: np.ndarray) -> tuple[int, int]:
    M = cv2.moments(pts)
    if M["m00"] == 0:
        x = int(np.mean(pts[:, 0]))
        y = int(np.mean(pts[:, 1]))
        return x, y
    return int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])


def render_m2f_overlay(image_bgr: np.ndarray, rooms: list[RoomDetection],
                       threshold: float = 0.5) -> np.ndarray:
    """Render rooms on image: filled polygons + outline + label."""
    overlay = image_bgr.copy()
    visible = [r for r in rooms if r.confidence >= threshold]
    visible.sort(key=lambda r: -r.area_pixels)

    polys: dict[str, np.ndarray] = {}
    for r in visible:
        polys[r.id] = np.array(r.polygon, dtype=np.int32)

    for r in visible:
        color = tuple(int(c) for c in PALETTE[r.type_id])
        cv2.fillPoly(overlay, [polys[r.id]], color)

    blended = cv2.addWeighted(overlay, ALPHA, image_bgr, 1 - ALPHA, 0)

    for r in visible:
        color = tuple(int(c) for c in PALETTE[r.type_id])
        pts = polys[r.id]
        cv2.polylines(blended, [pts], True, color, thickness=2,
                      lineType=cv2.LINE_AA)
        cx, cy = _polygon_centroid(pts)
        label = f"{r.type} {r.confidence:.2f}"
        # simple label
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(blended, (cx - tw // 2 - 3, cy - th - 5),
                      (cx + tw // 2 + 3, cy + 3), color, -1)
        # contrast text color
        txt_color = (0, 0, 0) if sum(color) > 450 else (255, 255, 255)
        cv2.putText(blended, label, (cx - tw // 2, cy - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, txt_color, 1, cv2.LINE_AA)
    return blended


def _find_checkpoint() -> Path:
    """Default checkpoint; fall back to most recent best.pt under runs/."""
    primary = REPO_ROOT / DEFAULT_CHECKPOINT
    if primary.exists():
        return primary
    print(f"[WARN] Default checkpoint not found at {primary}; searching for best.pt")
    candidates = list((REPO_ROOT / "runs").rglob("best.pt"))
    if not candidates:
        raise FileNotFoundError("No best.pt found anywhere under runs/")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    print(f"[INFO] Using fallback checkpoint: {candidates[0]}")
    return candidates[0]


def run_m2f_inference():
    """Run M2F on each plan, save overlay PNG, return per-plan stats."""
    checkpoint = _find_checkpoint()
    print(f"[INFO] Loading SegmentationInference from {checkpoint}")
    inference = SegmentationInference(
        checkpoint_path=str(checkpoint),
        image_size=IMAGE_SIZE,
        device="auto",
    )
    print(f"[INFO] Model loaded on device={inference.device}")

    plans = sorted(TEST_PLANS_DIR.glob("*.png"))
    if not plans:
        plans = sorted(TEST_PLANS_DIR.iterdir())
    results: dict[str, dict] = {}
    for plan in plans:
        stem = plan.stem
        out_dir = M2F_OUT_DIR / stem
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "segmentation.png"
        print(f"[RUN]  {stem}")
        t0 = time.time()
        try:
            seg = inference.predict(plan)
            elapsed = time.time() - t0
            bgr = cv2.imread(str(plan))
            overlay = render_m2f_overlay(bgr, seg.rooms, threshold=0.5)
            cv2.imwrite(str(out_path), overlay)
            results[stem] = {
                "ok": True,
                "elapsed": elapsed,
                "n_rooms": len(seg.rooms),
                "overlay_path": out_path,
            }
            print(f"  -> OK  {elapsed:.2f}s  {len(seg.rooms)} rooms")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  -> FAIL after {elapsed:.2f}s: {exc}")
            traceback.print_exc()
            results[stem] = {
                "ok": False,
                "elapsed": elapsed,
                "error": str(exc),
                "overlay_path": None,
            }
    return results


# ---------- Visualizations ----------

def _load_rgb(path: Path) -> np.ndarray | None:
    if path is None or not Path(path).exists():
        return None
    bgr = cv2.imread(str(path))
    if bgr is None:
        return None
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _placeholder_img(text: str, shape=(400, 600, 3)) -> np.ndarray:
    img = np.full(shape, 240, dtype=np.uint8)
    h, w = shape[:2]
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)
    cv2.putText(img, text, ((w - tw) // 2, (h + th) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (180, 30, 30), 2, cv2.LINE_AA)
    return img


def build_comparison_grid(plan_stems: list[str], m2f_results: dict[str, dict],
                          out_path: Path):
    n = len(plan_stems)
    fig_w = 18
    fig_h = 5.5 * n
    fig = plt.figure(figsize=(fig_w, fig_h))
    gs = GridSpec(n + 1, 3, figure=fig,
                  height_ratios=[0.15] + [1.0] * n, hspace=0.15, wspace=0.05)

    # Column titles row
    for j, title in enumerate(["Original plan", "M2F (batIA Mask2Former)",
                               "FT (FloorplanTransformation)"]):
        ax = fig.add_subplot(gs[0, j])
        ax.axis("off")
        ax.text(0.5, 0.3, title, ha="center", va="center",
                fontsize=18, fontweight="bold")

    for i, stem in enumerate(plan_stems):
        # original
        orig = _load_rgb(_find_plan_path(stem))
        m2f_path = m2f_results.get(stem, {}).get("overlay_path")
        m2f_img = _load_rgb(m2f_path) if m2f_path else None
        ft_img = _load_rgb(FT_OUT_DIR / stem / "vectorized.png")

        for j, (img, fallback_text) in enumerate([
            (orig, "Plan not found"),
            (m2f_img, "M2F: Failed"),
            (ft_img, "FT: not available"),
        ]):
            ax = fig.add_subplot(gs[i + 1, j])
            if img is None:
                shape = (400, 600, 3)
                ax.imshow(_placeholder_img(fallback_text, shape))
            else:
                ax.imshow(img)
            ax.set_xticks([])
            ax.set_yticks([])
            if j == 0:
                ax.set_ylabel(stem, fontsize=10, rotation=0,
                              ha="right", va="center", labelpad=10)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_per_plan_dashboard(stem: str, m2f_path: Path | None, out_path: Path):
    orig = _load_rgb(_find_plan_path(stem))
    m2f = _load_rgb(m2f_path) if m2f_path else None
    ft_vec = _load_rgb(FT_OUT_DIR / stem / "vectorized.png")
    ft_corn = _load_rgb(FT_OUT_DIR / stem / "raw_corners.png")

    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    panels = [
        (orig, "Original"),
        (m2f, "M2F segmentation"),
        (ft_vec, "FT vectorized"),
        (ft_corn, "FT raw_corners"),
    ]
    for ax, (img, title) in zip(axes.ravel(), panels):
        if img is None:
            ax.imshow(_placeholder_img(f"{title}: missing"))
        else:
            ax.imshow(img)
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.set_xticks([])
        ax.set_yticks([])
    fig.suptitle(stem, fontsize=12)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=100, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _find_plan_path(stem: str) -> Path:
    """Return the original plan path for a given stem (png expected)."""
    for ext in (".png", ".jpg", ".jpeg"):
        p = TEST_PLANS_DIR / f"{stem}{ext}"
        if p.exists():
            return p
    matches = list(TEST_PLANS_DIR.glob(f"{stem}.*"))
    return matches[0] if matches else TEST_PLANS_DIR / f"{stem}.png"


def main():
    print(f"[INFO] Repo root: {REPO_ROOT}")
    print(f"[INFO] Test plans: {TEST_PLANS_DIR}")
    plan_paths = sorted(TEST_PLANS_DIR.glob("*.png"))
    plan_stems = [p.stem for p in plan_paths]
    print(f"[INFO] Found {len(plan_stems)} plans")

    # 1. M2F inference
    m2f_results = run_m2f_inference()

    # 2. Comparison grid
    grid_path = OUTPUTS_DIR / "comparison_grid.png"
    print(f"[INFO] Building comparison grid -> {grid_path}")
    build_comparison_grid(plan_stems, m2f_results, grid_path)

    # 3. Per-plan dashboards
    for stem in plan_stems:
        dash_path = PER_PLAN_DIR / f"{stem}_dashboard.png"
        print(f"[INFO] Dashboard -> {dash_path}")
        m2f_path = m2f_results.get(stem, {}).get("overlay_path")
        build_per_plan_dashboard(stem, m2f_path, dash_path)

    # Summary
    n_ok = sum(1 for r in m2f_results.values() if r.get("ok"))
    avg_time = (
        sum(r["elapsed"] for r in m2f_results.values() if r.get("ok"))
        / max(n_ok, 1)
    )
    print("\n=== SUMMARY ===")
    print(f"M2F succeeded: {n_ok}/{len(m2f_results)}")
    print(f"Average inference time: {avg_time:.2f}s")
    if grid_path.exists():
        size_mb = grid_path.stat().st_size / 1024 / 1024
        print(f"Grid: {grid_path} ({size_mb:.2f} MB)")
    for stem, r in m2f_results.items():
        status = "OK" if r.get("ok") else f"FAIL ({r.get('error')})"
        print(f"  {stem}: {status} ({r.get('elapsed', 0):.2f}s)")


if __name__ == "__main__":
    main()
