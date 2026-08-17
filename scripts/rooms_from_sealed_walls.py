"""Pièces = composantes connexes du masque de murs, ouvertures scellées.

La fermeture morphologique seule échoue (21 % des pièces à IoU>=0.5) : elle bouche
partout de la même façon et avale les petites pièces avant d'avoir fini de boucher
les baies vitrées. Ici on scelle *exactement* aux ouvertures détectées par le
modèle OBB, ce qui permet de garder un noyau de fermeture minimal.

Une boîte d'ouverture est plus fine que le mur qu'elle traverse (fenêtre ~9 px,
mur ~15-20 px) : elle est donc élargie sur son petit côté avant d'être remplie,
sinon le scellement laisse passer.

Usage :
    .venv/bin/python scripts/rooms_from_sealed_walls.py --margin 6 10 14
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.classes import CLASS_ID, CLASS_NAMES, NUM_CLASSES
from src.segmentation.model import build_model, get_processor
from src.segmentation.preprocess import letterbox, unletterbox_mask

WALL_CKPT = "runs/segmentation/wall_only_dwg_v3/checkpoints/best.pt"
WALL_BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
WALL_SIZE = 640
OBB_WEIGHTS = "runs/obb/fr_obb_v2/weights/best.pt"
OBB_SIZE = 2048
OPENINGS = {11: "Door", 12: "Window", 13: "french_door", 14: "sliding_door"}
GT_ROOT = Path("data/processed/fr_panoptic_lot01")


def wall_mask(model, processor, device, path: Path, size: int = WALL_SIZE) -> np.ndarray:
    """Masque de murs binaire, remonté à la résolution native du plan.

    `size` doit être celle de l'entraînement du checkpoint : évaluer un modèle
    entraîné à 1024 en lui donnant du 640 mesure autre chose que le modèle.
    """
    rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    pad, info = letterbox(rgb, target_size=size)
    t = (pad.astype(np.float32) / 255.0 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    t = torch.from_numpy(t).permute(2, 0, 1).unsqueeze(0).float().to(device)
    with torch.no_grad():
        out = model(pixel_values=t)
    sem = processor.post_process_semantic_segmentation(
        out, target_sizes=[(size, size)])[0].cpu().numpy()
    # Le letterbox pade en carré : le plan n'occupe qu'un sous-rectangle des
    # 640x640. Redimensionner le carré entier vers le plan étire la prédiction
    # et décale tous les murs — c'est ce qui faisait fuir les pièces.
    m = (sem == CLASS_ID["Wall"]).astype(np.uint8)
    return unletterbox_mask(m, info)


def seal(mask: np.ndarray, dets: np.ndarray, margin: int) -> np.ndarray:
    """Remplit chaque ouverture dans le masque de murs, élargie de `margin` px.

    L'élargissement porte sur les deux axes du rectangle orienté : sur le petit
    côté pour traverser toute l'épaisseur du mur, sur le grand pour rattraper une
    boîte légèrement trop courte aux extrémités.
    """
    out = mask.copy()
    for quad in dets:
        (cx, cy), (bw, bh), ang = cv2.minAreaRect(quad.astype(np.float32))
        box = cv2.boxPoints(((cx, cy), (bw + 2 * margin, bh + 2 * margin), ang))
        cv2.fillPoly(out, [np.int32(box)], 1)
    return out


def rooms(mask: np.ndarray, close_k: int, min_frac: float):
    if close_k > 1:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_k, close_k))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats((1 - mask).astype(np.uint8), 4)
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > min_frac * mask.size]
    return lab, keep


def gt_rooms(name: str):
    ins = np.array(Image.open(GT_ROOT / "instance/test" / name))
    sem = np.array(Image.open(GT_ROOT / "semantic/test" / name))
    h, w = ins.shape
    out = []
    for i in np.unique(ins):
        if i == 0:
            continue
        m = ins == i
        if m.sum() >= 0.001 * h * w:
            out.append((CLASS_NAMES[int(np.bincount(sem[m]).argmax())], m))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wall-ckpt", default=WALL_CKPT)
    ap.add_argument("--wall-size", type=int, default=WALL_SIZE,
                    help="résolution d'entraînement du checkpoint (640 pour v4, 1024 pour v5)")
    ap.add_argument("--margin", type=int, nargs="+", default=[0, 6, 10, 14])
    ap.add_argument("--close", type=int, default=5)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--min-frac", type=float, default=0.003)
    args = ap.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    wm = build_model(backbone=WALL_BACKBONE, num_classes=NUM_CLASSES)
    wm.load_state_dict(load_checkpoint(args.wall_ckpt, map_location=device)["model_state_dict"])
    wm.to(device).eval()
    proc = get_processor(WALL_BACKBONE)

    from ultralytics import YOLO
    yolo = YOLO(OBB_WEIGHTS)

    files = sorted(p.name for p in (GT_ROOT / "images/test").glob("*.png"))
    # même exclusion que le benchmark : ce plan a servi à décoder les conventions
    files = [f for f in files if not f.startswith("1-304783-83")]

    cache = {}
    for f in files:
        p = GT_ROOT / "images/test" / f
        r = yolo.predict(str(p), imgsz=OBB_SIZE, conf=args.conf, device=device, verbose=False)[0]
        quads = r.obb.xyxyxyxy.cpu().numpy() if r.obb is not None else np.empty((0, 4, 2))
        cls = r.obb.cls.cpu().numpy().astype(int) if r.obb is not None else np.empty(0, int)
        cache[f] = (wall_mask(wm, proc, device, p, args.wall_size),
                    quads[np.isin(cls, list(OPENINGS))],
                    gt_rooms(f))
        print(f"  {f[:38]:40s} {len(cache[f][1]):3d} ouvertures | {len(cache[f][2])} pièces GT",
              flush=True)

    print(f"\n{'marge':>6} {'régions/plan':>13} {'IoU moyen':>10} {'IoU>=.5':>8} {'IoU>=.7':>8}")
    for margin in args.margin:
        ious, nreg = [], []
        for f in files:
            mask, dets, gts = cache[f]
            lab, keep = rooms(seal(mask, dets, margin), args.close, args.min_frac)
            nreg.append(len(keep))
            for _, gm in gts:
                best = 0.0
                for i in keep:
                    rm = lab == i
                    inter = (rm & gm).sum()
                    if inter:
                        best = max(best, inter / ((rm | gm).sum()))
                ious.append(best)
        a = np.array(ious)
        print(f"{margin:6d} {np.mean(nreg):13.1f} {a.mean():10.3f} "
              f"{np.mean(a >= .5):8.1%} {np.mean(a >= .7):8.1%}")
    print(f"\nréférence : {np.mean([len(c[2]) for c in cache.values()]):.1f} pièces GT/plan | "
          f"sans scellement, le meilleur réglage plafonnait à 21,4 % (IoU>=.5)")


if __name__ == "__main__":
    main()
