"""
Standalone inference script for FloorplanTransformation (FT) PyTorch model.

Loads pretrained checkpoint, runs forward pass on each PNG in test_plans/,
extracts heatmaps (corners/icons/rooms), runs IP post-processing to recover
vectorized floorplan, and writes 4 PNG outputs per plan under
outputs/ft/<plan_name>/.

Run with the project venv:
    /Users/hadrienpasset/Developer/planRoomRecognition/.venv/bin/python \
        /Users/hadrienpasset/Developer/planRoomRecognition/experiments/wall_detection_eval/run_ft_inference.py
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import argparse
import traceback
import contextlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import cv2
import torch

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

EVAL_ROOT = Path(__file__).resolve().parent
FT_ROOT = EVAL_ROOT / "models_src" / "FloorplanTransformation"
FT_PY = FT_ROOT / "pytorch"
CHECKPOINT = FT_PY / "checkpoint" / "checkpoint.pth"
TEST_PLANS_DIR = EVAL_ROOT / "test_plans"
OUTPUTS_DIR = EVAL_ROOT / "outputs" / "ft"

# --------------------------------------------------------------------------- #
# numpy 2.x compatibility shims for the 2018 code
# --------------------------------------------------------------------------- #
# IP.py / utils.py use deprecated aliases (np.bool, np.int, np.float)
for _alias, _target in (
    ("bool", bool),
    ("int", int),
    ("float", float),
    ("object", object),
    ("complex", complex),
):
    if not hasattr(np, _alias):
        setattr(np, _alias, _target)

# Make `from utils import *`, `from models.X import Y`, `from IP import ...` work
sys.path.insert(0, str(FT_PY))
sys.path.insert(0, str(FT_PY / "models"))


# Patch drn loader so it does NOT try to download ImageNet pretrained weights;
# our full checkpoint already supplies them.
def _patch_drn_no_download():
    import models.drn as drn_mod

    _orig = drn_mod.drn_d_54

    def drn_d_54(pretrained=False, **kwargs):
        # Always disable the model-zoo download; we restore from checkpoint.
        return _orig(pretrained=False, **kwargs)

    drn_mod.drn_d_54 = drn_d_54


_patch_drn_no_download()


from utils import (  # noqa: E402  (imports after sys.path tweak)
    NUM_CORNERS,
    NUM_ICONS,
    NUM_ROOMS,
    NUM_WALL_CORNERS,
    drawSegmentationImage,
)
from models.model import Model  # noqa: E402

# IP.py mutates module-level globals; import lazily so it doesn't crash startup
import IP as ip_mod  # noqa: E402

# IP.py is missing an `import os` (uses os.path.join inside functions)
import os as _os
ip_mod.os = _os


# --------------------------------------------------------------------------- #
# Heatmap visualization helpers
# --------------------------------------------------------------------------- #

def _normalize_for_viz(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize a 2D array to uint8 [0, 255]."""
    a = arr.astype(np.float32)
    lo, hi = float(a.min()), float(a.max())
    if hi - lo < 1e-8:
        return np.zeros_like(a, dtype=np.uint8)
    return ((a - lo) / (hi - lo) * 255.0).clip(0, 255).astype(np.uint8)


def visualize_corner_heatmaps(corner_pred: np.ndarray) -> np.ndarray:
    """corner_pred: HxWxNUM_CORNERS sigmoid probs. Returns BGR image.

    Use max over channels -> apply COLORMAP_JET on top of a grayscale base.
    """
    h, w, _ = corner_pred.shape
    # Aggregate per-pixel max corner probability
    agg = corner_pred.max(axis=-1)
    agg_u8 = (agg.clip(0, 1) * 255).astype(np.uint8)
    color = cv2.applyColorMap(agg_u8, cv2.COLORMAP_JET)
    # Mask low values to black for clarity
    mask = (agg > 0.05).astype(np.uint8)[..., None]
    return color * mask


def visualize_softmax_heatmap(logits: np.ndarray, num_classes: int) -> np.ndarray:
    """logits: HxWx(num_classes+2). Use drawSegmentationImage on argmax."""
    # softmax along last axis
    e = np.exp(logits - logits.max(axis=-1, keepdims=True))
    probs = e / e.sum(axis=-1, keepdims=True)
    # drawSegmentationImage handles argmax visualization in BGR
    return drawSegmentationImage(probs, blackIndex=0).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Image preprocessing (mirrors datasets/floorplan_dataset.augmentSample for test)
# --------------------------------------------------------------------------- #

def preprocess_image(img_path: Path, size: int = 256):
    """Load PNG, letterbox to size x size with white padding, return:
        - tensor (1, 3, size, size) normalized to (x/255 - 0.5)
        - canvas uint8 image used for visualization (size x size x 3, BGR)
        - the original BGR image
    """
    image_bgr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise RuntimeError(f"Could not read image: {img_path}")
    h, w = image_bgr.shape[:2]
    scale = size / max(h, w)
    new_w, new_h = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(image_bgr, (new_w, new_h))
    canvas = np.full((size, size, 3), 255, dtype=np.uint8)
    off_y = (size - new_h) // 2
    off_x = (size - new_w) // 2
    canvas[off_y:off_y + new_h, off_x:off_x + new_w] = resized
    # Model expects BGR (cv2.imread output), normalized
    arr = (canvas.astype(np.float32) / 255.0 - 0.5).transpose(2, 0, 1)
    tensor = torch.from_numpy(arr).unsqueeze(0)
    return tensor, canvas, image_bgr


# --------------------------------------------------------------------------- #
# Checkpoint loading
# --------------------------------------------------------------------------- #

def build_model(width: int = 256, height: int = 256) -> Model:
    opts = SimpleNamespace(
        width=width,
        height=height,
        outputWidth=width,
        outputHeight=height,
    )
    model = Model(opts)
    return model


def load_checkpoint(model: Model, ckpt_path: Path):
    """Load state_dict; return list of mismatch messages."""
    state = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
    # If wrapped, unwrap
    if isinstance(state, dict) and "state_dict" in state and not any(
        k.startswith(("drn.", "pyramid.", "feature_conv.", "segmentation_pred."))
        for k in state.keys()
    ):
        state = state["state_dict"]

    incompatible = model.load_state_dict(state, strict=False)
    msgs = []
    if incompatible.missing_keys:
        msgs.append(f"missing_keys ({len(incompatible.missing_keys)}): "
                    f"{incompatible.missing_keys[:5]}")
    if incompatible.unexpected_keys:
        msgs.append(f"unexpected_keys ({len(incompatible.unexpected_keys)}): "
                    f"{incompatible.unexpected_keys[:5]}")
    return msgs


# --------------------------------------------------------------------------- #
# IP post-processing wrapper
# --------------------------------------------------------------------------- #

def run_ip_postprocess(
    corner_pred: np.ndarray,
    icon_logits: np.ndarray,
    room_logits: np.ndarray,
    canvas_bgr: np.ndarray,
    debug_dir: Path,
) -> Path | None:
    """Run IP solver and produce a 'vectorized.png' rendering on top of canvas.

    Returns path to a debug image suitable for use as vectorized.png, or None.
    """
    debug_dir.mkdir(parents=True, exist_ok=True)

    # softmax along last axis for icon / room heatmaps
    def softmax(x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max(axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    icon_heatmaps = softmax(icon_logits)
    room_heatmaps = softmax(room_logits)

    wallCornerHeatmaps = corner_pred[:, :, :NUM_WALL_CORNERS]
    doorCornerHeatmaps = corner_pred[:, :, NUM_WALL_CORNERS:NUM_WALL_CORNERS + 4]
    iconCornerHeatmaps = corner_pred[:, :, -4:]

    output_prefix = str(debug_dir) + "/"

    # Silence IP.py / PuLP / CBC chatter
    with open(os.devnull, "w") as devnull, \
            contextlib.redirect_stdout(devnull), \
            contextlib.redirect_stderr(devnull):
        ip_mod.reconstructFloorplan(
            wallCornerHeatmaps,
            doorCornerHeatmaps,
            iconCornerHeatmaps,
            icon_heatmaps,
            room_heatmaps,
            output_prefix=output_prefix,
            densityImage=cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2GRAY),
            gt_dict=None,
            gt=False,
            gap=-1,
            distanceThreshold=-1,
            lengthThreshold=-1,
            debug_prefix=str(debug_dir),
            heatmapValueThresholdWall=None,
            heatmapValueThresholdDoor=None,
            heatmapValueThresholdIcon=None,
            enableAugmentation=True,
        )

    # IP writes 'result_line.png' (final wall vectors), plus 'result_door.png'
    # and 'result_icon.png'. Compose an overlay on the original canvas.
    composed = canvas_bgr.copy()
    found_any = False
    for fname, color_boost in (
        ("result_line.png", (1.0, 0.2, 0.2)),
        ("result_door.png", (0.2, 1.0, 0.2)),
        ("result_icon.png", (0.2, 0.2, 1.0)),
    ):
        p = debug_dir / fname
        if not p.exists():
            continue
        layer = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if layer is None or layer.shape[:2] != composed.shape[:2]:
            continue
        # Treat non-black pixels as foreground; tint and blend.
        mask = (layer.sum(axis=-1) > 5).astype(np.uint8)[..., None]
        b, g, r = color_boost
        tinted = (layer.astype(np.float32) * np.array([b, g, r], dtype=np.float32)
                  ).clip(0, 255).astype(np.uint8)
        composed = np.where(mask.astype(bool),
                            (0.4 * composed + 0.6 * tinted).clip(0, 255).astype(np.uint8),
                            composed)
        found_any = True

    if found_any:
        out_path = debug_dir / "_composed_vectorized.png"
        cv2.imwrite(str(out_path), composed)
        return out_path

    # Fallback: any wall-line-only render
    for candidate in ("result_line.png", "lines.png", "points.png"):
        p = debug_dir / candidate
        if p.exists():
            return p
    return None


# --------------------------------------------------------------------------- #
# Main per-plan inference
# --------------------------------------------------------------------------- #

def process_plan(
    model: Model,
    img_path: Path,
    out_dir: Path,
    device: torch.device,
) -> dict:
    """Run end-to-end on a single plan, write 4 outputs into out_dir."""
    info = {"plan": img_path.name, "ok_heatmaps": False, "ok_vectorized": False,
            "errors": []}

    out_dir.mkdir(parents=True, exist_ok=True)

    tensor, canvas_bgr, _ = preprocess_image(img_path)
    tensor = tensor.to(device)

    with torch.no_grad():
        corner_pred, icon_pred, room_pred = model(tensor)

    # shapes: (1, H, W, C)
    corner_np = corner_pred[0].detach().cpu().numpy()  # sigmoid probs
    icon_np = icon_pred[0].detach().cpu().numpy()      # raw logits
    room_np = room_pred[0].detach().cpu().numpy()      # raw logits

    # raw heatmap visualizations
    try:
        cv2.imwrite(str(out_dir / "raw_corners.png"),
                    visualize_corner_heatmaps(corner_np))
        cv2.imwrite(str(out_dir / "raw_icons.png"),
                    visualize_softmax_heatmap(icon_np, NUM_ICONS))
        cv2.imwrite(str(out_dir / "raw_rooms.png"),
                    visualize_softmax_heatmap(room_np, NUM_ROOMS))
        info["ok_heatmaps"] = True
    except Exception as e:
        info["errors"].append(f"heatmap viz: {e}")
        traceback.print_exc()

    # IP post-processing (best-effort)
    ip_debug = out_dir / "_ip_debug"
    try:
        result_path = run_ip_postprocess(
            corner_np, icon_np, room_np, canvas_bgr, ip_debug,
        )
        target = out_dir / "vectorized.png"
        if result_path is not None and result_path.exists():
            shutil.copyfile(result_path, target)
            info["ok_vectorized"] = True
        else:
            # Fall back: overlay the corner heatmap on the canvas
            overlay = canvas_bgr.copy()
            corners_viz = visualize_corner_heatmaps(corner_np)
            mask = (corners_viz.sum(axis=-1) > 0)[..., None]
            overlay = np.where(mask, (0.5 * overlay + 0.5 * corners_viz).astype(np.uint8),
                               overlay)
            cv2.imwrite(str(target), overlay)
            info["errors"].append("IP produced no final vector image; wrote fallback overlay")
    except Exception as e:
        info["errors"].append(f"IP solver failed: {e}")
        traceback.print_exc()
        # Fallback: corner-heatmap overlay
        overlay = canvas_bgr.copy()
        corners_viz = visualize_corner_heatmaps(corner_np)
        mask = (corners_viz.sum(axis=-1) > 0)[..., None]
        overlay = np.where(mask, (0.5 * overlay + 0.5 * corners_viz).astype(np.uint8),
                           overlay)
        cv2.imwrite(str(out_dir / "vectorized.png"), overlay)

    return info


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans-dir", default=str(TEST_PLANS_DIR))
    parser.add_argument("--out-dir", default=str(OUTPUTS_DIR))
    parser.add_argument("--checkpoint", default=str(CHECKPOINT))
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda", "mps"])
    args = parser.parse_args()

    plans_dir = Path(args.plans_dir)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    device = torch.device(args.device)

    print(f"[FT] Building model on {device}")
    model = build_model()

    print(f"[FT] Loading checkpoint: {args.checkpoint}")
    mismatch_msgs = load_checkpoint(model, Path(args.checkpoint))
    for m in mismatch_msgs:
        print(f"  ! {m}")
    if not mismatch_msgs:
        print("  state_dict loaded with no mismatches")

    model = model.to(device).eval()

    plan_paths = sorted(plans_dir.glob("*.png"))
    print(f"[FT] {len(plan_paths)} plans found in {plans_dir}")

    summary = []
    t0 = time.time()
    for p in plan_paths:
        plan_name = p.stem
        out_dir = out_root / plan_name
        print(f"\n--- {plan_name} ---")
        t_start = time.time()
        try:
            info = process_plan(model, p, out_dir, device)
        except Exception as e:
            info = {"plan": p.name, "ok_heatmaps": False, "ok_vectorized": False,
                    "errors": [f"top-level: {e}"]}
            traceback.print_exc()
        info["elapsed_s"] = round(time.time() - t_start, 2)
        summary.append(info)
        print(f"  done in {info['elapsed_s']}s  ok_heatmaps={info['ok_heatmaps']}  "
              f"ok_vectorized={info['ok_vectorized']}")
        if info["errors"]:
            for e in info["errors"]:
                print(f"    err: {e}")

    total = time.time() - t0
    print(f"\n=== FT inference summary ===")
    print(f"Total time: {total:.1f}s for {len(summary)} plans")
    n_heat = sum(1 for s in summary if s["ok_heatmaps"])
    n_vec = sum(1 for s in summary if s["ok_vectorized"])
    print(f"Heatmaps OK: {n_heat}/{len(summary)}    Vectorized OK: {n_vec}/{len(summary)}")
    for s in summary:
        print(f"  - {s['plan']}: heat={s['ok_heatmaps']} vec={s['ok_vectorized']} "
              f"t={s['elapsed_s']}s errs={len(s['errors'])}")


if __name__ == "__main__":
    main()
