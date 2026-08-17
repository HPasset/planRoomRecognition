"""Pré-annotation des pièces pour CVAT : un polygone par pièce, label déduit de l'OCR.

Reprend la chaîne déjà mesurée dans `rooms_from_sealed_walls.py` (masque de murs
→ scellement des ouvertures → composantes connexes du vide) et la termine pour
l'annotation : contour simplifié, label posé par l'OCR FR, export XML importable
tel quel dans une task CVAT.

Le polygone est le bon primitif ici : une pièce est un contour fermé quelconque,
et CVAT permet de déplacer un sommet isolé — corriger une pré-annotation coûte
donc quelques clics, contre 6 à 12 pour tracer la pièce de zéro.

Ce qui reste manuel, et qui est compté dans le rapport de fin :
  - l'extérieur (terrasse, loggia, jardin) : non clos par des murs, il fusionne
    avec le fond de page et est donc écarté ;
  - l'escalier, qui n'est pas séparé du dégagement par une cloison ;
  - les plans à cloisons en trait fin quand on tourne sans checkpoint de murs.

Usage :
    # chaîne complète (murs Mask2Former + ouvertures YOLO OBB + OCR Paddle)
    .venv/bin/python scripts/preannotate_rooms_cvat.py \
        --images data/raw/plans_fr_lots/lot_03 --out /tmp/rooms_lot03 --viz

    # sans modèle : murs par seuillage, pour les plans à murs en aplat noir
    .venv/bin/python scripts/preannotate_rooms_cvat.py \
        --images data/raw/plans_fr_lots/lot_03 --out /tmp/rooms_lot03 --walls threshold

    # mesurer avant de lancer les 100 plans : IoU + justesse des labels sur le GT lot01
    .venv/bin/python scripts/preannotate_rooms_cvat.py \
        --images data/processed/fr_panoptic_lot01/images/test \
        --out /tmp/rooms_eval --eval-gt data/processed/fr_panoptic_lot01

Import dans CVAT : task → Actions → Upload annotations → « CVAT for images 1.1 »
→ rooms_preannotations.xml. Les labels du XML doivent exister dans la task.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.segmentation.classes import CLASS_NAMES  # noqa: E402

WALL_CKPT = "runs/segmentation/wall_only_dwg_v3/checkpoints/best.pt"
WALL_BACKBONE = "facebook/mask2former-swin-tiny-coco-panoptic"
WALL_SIZE = 640
OBB_WEIGHTS = "runs/obb/fr_obb_v2/weights/best.pt"
OBB_SIZE = 2048
OPENINGS = {11: "Door", 12: "Window", 13: "french_door", 14: "sliding_door"}

# marge de scellement retenue par le benchmark de rooms_from_sealed_walls.py
SEAL_MARGIN = 10


# --------------------------------------------------------------------------- murs

def solid_walls(img: np.ndarray) -> np.ndarray:
    """Murs en aplat : composantes sombres à la fois larges et étendues.

    Copie assumée de `preannotate_walls_cvat.solid_walls` — on ne veut pas que
    ce script dépende d'un autre script du dossier `scripts/`.
    """
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dark = (g < 60).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(dark, 8)
    out = np.zeros_like(dark)
    span = 0.25 * max(dark.shape)
    for i in range(1, n):
        if (st[i, cv2.CC_STAT_AREA] > 3000
                and max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) > span):
            out[lab == i] = 1
    return out


class WallModel:
    """Masque de murs par le checkpoint Mask2Former, à la résolution native."""

    def __init__(self, ckpt: str, device: str):
        import torch
        from src.segmentation.checkpoint import load_checkpoint
        from src.segmentation.classes import CLASS_ID, NUM_CLASSES
        from src.segmentation.model import build_model, get_processor

        self.torch, self.wall_id = torch, CLASS_ID["Wall"]
        self.device = device
        self.model = build_model(backbone=WALL_BACKBONE, num_classes=NUM_CLASSES)
        self.model.load_state_dict(
            load_checkpoint(ckpt, map_location=device)["model_state_dict"])
        self.model.to(device).eval()
        self.proc = get_processor(WALL_BACKBONE)

    def __call__(self, img: np.ndarray) -> np.ndarray:
        from src.segmentation.preprocess import letterbox, unletterbox_mask
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pad, info = letterbox(rgb, target_size=WALL_SIZE)
        t = (pad.astype(np.float32) / 255.0 - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
        t = self.torch.from_numpy(t).permute(2, 0, 1).unsqueeze(0).float().to(self.device)
        with self.torch.no_grad():
            out = self.model(pixel_values=t)
        sem = self.proc.post_process_semantic_segmentation(
            out, target_sizes=[(WALL_SIZE, WALL_SIZE)])[0].cpu().numpy()
        # Retirer les bandes de padding avant de remonter : sans ça la
        # prédiction est étirée et tous les murs sont décalés.
        m = (sem == self.wall_id).astype(np.uint8)
        return unletterbox_mask(m, info)


# ---------------------------------------------------------------------- ouvertures

def seal(mask: np.ndarray, quads: np.ndarray, margin: int = SEAL_MARGIN) -> np.ndarray:
    """Remplit chaque ouverture détectée, élargie de `margin` px sur les deux axes.

    Une boîte d'ouverture est plus fine que le mur qu'elle traverse (fenêtre
    ~9 px, mur ~15-20 px) : sans élargissement le scellement laisse passer, et
    la pièce fusionne avec sa voisine.
    """
    out = mask.copy()
    for quad in quads:
        (cx, cy), (bw, bh), ang = cv2.minAreaRect(quad.astype(np.float32))
        box = cv2.boxPoints(((cx, cy), (bw + 2 * margin, bh + 2 * margin), ang))
        cv2.fillPoly(out, [np.int32(box)], 1)
    return out


def detect_boxes(yolo, path: Path, device: str, conf: float) -> tuple[np.ndarray, np.ndarray]:
    """(ouvertures, mobilier) — une seule passe du modèle OBB pour les deux.

    Le mobilier sert à jeter les faux polygones : un lit ou une baignoire dont le
    contour touche un mur entre dans le masque de murs, et son intérieur blanc
    ressort ensuite comme une « pièce ». Le détecteur sait déjà les nommer.
    """
    r = yolo.predict(str(path), imgsz=OBB_SIZE, conf=conf, device=device, verbose=False)[0]
    if r.obb is None:
        return np.empty((0, 4, 2)), np.empty((0, 4, 2))
    quads = r.obb.xyxyxyxy.cpu().numpy()
    cls = r.obb.cls.cpu().numpy().astype(int)
    return quads[np.isin(cls, list(OPENINGS))], quads[~np.isin(cls, list(OPENINGS))]


# -------------------------------------------------------------------------- pièces

def extract_rooms(sealed: np.ndarray, close_k: int, min_frac: float,
                  border: int = 3) -> list[np.ndarray]:
    """Composantes connexes du vide, hors extérieur.

    Le fond de page est lui aussi une composante du vide. On l'écarte par le
    contact avec le bord de l'image plutôt que par la surface : sur un plan
    cadré serré, l'extérieur peut être plus petit que le séjour.
    """
    if close_k > 1:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (close_k, close_k))
        sealed = cv2.morphologyEx(sealed, cv2.MORPH_CLOSE, k)
    n, lab, st, _ = cv2.connectedComponentsWithStats((1 - sealed).astype(np.uint8), 4)
    h, w = sealed.shape
    out = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < min_frac * h * w:
            continue
        x, y = st[i, cv2.CC_STAT_LEFT], st[i, cv2.CC_STAT_TOP]
        bw, bh = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]
        if x < border or y < border or x + bw > w - border or y + bh > h - border:
            continue
        out.append((lab == i).astype(np.uint8))
    return out


def thick_walls(sealed: np.ndarray, k: int = 9) -> np.ndarray:
    """Ce qui reste du masque après ouverture : les murs en aplat, sans le trait fin."""
    return cv2.morphologyEx(sealed, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))


def boundary_solidity(mask: np.ndarray, thick: np.ndarray, ring: int = 4) -> float:
    """Part du pourtour d'une composante qui tombe sur du mur épais.

    Une vraie pièce est bordée d'aplat ; un arc de battement de porte, un lit ou
    un bac de douche sont bordés de trait fin. C'est le seul discriminant qui les
    sépare sans abîmer la géométrie : on ouvre le masque pour *juger* le pourtour,
    jamais pour découper. Ouvrir avant l'extraction détruit les cloisons fines et
    fait chuter le rappel de 31 % à 16 % — mesuré.
    """
    r = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=ring).astype(bool) & ~mask.astype(bool)
    return float((r & thick.astype(bool)).sum()) / max(r.sum(), 1)


def covered_by(mask: np.ndarray, quads: np.ndarray) -> float:
    """Part de `mask` recouverte par la plus englobante des boîtes `quads`."""
    best = 0.0
    for q in quads:
        box = cv2.fillPoly(np.zeros(mask.shape, np.uint8), [q.astype(np.int32)], 1).astype(bool)
        best = max(best, float((mask.astype(bool) & box).sum()) / max(mask.sum(), 1))
    return best


def polygonize(mask: np.ndarray, grow: int, eps_ratio: float) -> np.ndarray | None:
    """Contour externe simplifié, poussé jusqu'au milieu du mur.

    La composante connexe s'arrête à la face intérieure du mur ; l'annotation de
    référence, elle, est tracée sur le mur. On dilate donc d'une demi-épaisseur
    avant de contourner, sinon chaque pièce est systématiquement sous-estimée
    d'un liseré et le modèle apprend ce biais.
    """
    m = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=grow) if grow else mask
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    poly = cv2.approxPolyDP(c, eps_ratio * cv2.arcLength(c, True), True).reshape(-1, 2)
    return poly if len(poly) >= 3 else None


def half_thickness(walls: np.ndarray) -> int:
    """Demi-épaisseur médiane des murs, en px."""
    d = cv2.distanceTransform(walls, cv2.DIST_L2, 5)
    v = d[d > 0]
    return int(round(np.percentile(v, 75))) if v.size else 4


# --------------------------------------------------------------------------- label

class Labeller:
    """Label d'une pièce = libellé OCR tombant dans son polygone.

    Réutilise la chaîne OCR du projet (PaddleOCR FR + `postprocess_ocr_items` +
    `FR_TO_C2`) : le mapping libellé → classe est déjà documenté et testé là-bas,
    le dupliquer ici le ferait diverger.
    """

    def __init__(self, default: str = "Entry"):
        from src.planrec.ocr.engine_paddle import PaddleOCREngine
        from src.planrec.ocr.postprocess import postprocess_ocr_items
        from src.planrec.fusion import FR_TO_C2

        self.engine = PaddleOCREngine(langs=("fr",))
        self.post = postprocess_ocr_items
        self.fr_to_c2 = FR_TO_C2
        self.default = default

    def hits(self, img: np.ndarray) -> list[dict]:
        # preprocess=False : l'upscale x2 du preprocess porte la passe 1 à
        # 4800 px de large et coûte 340 s par plan, pour un résultat identique
        # ou pire — mesuré sur deux plans : 396 s -> 57 s, mêmes libellés, et un
        # « wc » retrouvé en plus sans lui. Le docstring de l'engine le dit déjà.
        return self.post(self.engine.read(img, preprocess=False))

    def label_for(self, poly: np.ndarray, hits: list[dict]) -> tuple[str, bool]:
        """(label, sûr) — `sûr` est False quand aucun libellé ne tombe dedans."""
        best, best_conf = None, -1.0
        p = poly.astype(np.int32)
        for h in hits:
            cid = self.fr_to_c2.get(h.get("room_type"))
            if cid is None:
                continue
            bb = h["bbox"]
            cx = sum(q[0] for q in bb) / len(bb)
            cy = sum(q[1] for q in bb) / len(bb)
            if cv2.pointPolygonTest(p, (cx, cy), False) < 0:
                continue
            conf = float(h.get("confidence", 0.0))
            if conf > best_conf:
                best, best_conf = CLASS_NAMES[cid], conf
        return (best, True) if best else (self.default, False)


# ----------------------------------------------------------------------------- io

SHAPE_TAGS = ("polygon", "box", "polyline", "points", "mask", "ellipse", "cuboid")


def load_existing(path: Path) -> dict[str, list]:
    """{nom de frame: shapes déjà tracées} depuis un export CVAT.

    L'upload d'annotations dans CVAT remplace celles du job — il ne les fusionne
    pas. Sans ce garde-fou, pré-annoter un lot déjà entamé efface le travail
    manuel déjà fait dessus.
    """
    root = ET.parse(path).getroot()
    out = {}
    for im in root.findall("image"):
        shapes = [c for c in im if c.tag in SHAPE_TAGS]
        if shapes:
            out[im.get("name")] = shapes
    return out


def xml_for(images: list[dict], existing: dict[str, list] | None = None) -> str:
    """CVAT for images 1.1 — <polygon points="x,y;x,y;...">.

    Une frame déjà annotée est recopiée telle quelle : on ne repasse jamais
    par-dessus du tracé manuel.
    """
    root = ET.Element("annotations")
    ET.SubElement(root, "version").text = "1.1"
    for idx, im in enumerate(images):
        el = ET.SubElement(root, "image", id=str(idx), name=im["name"],
                           width=str(im["w"]), height=str(im["h"]))
        kept = (existing or {}).get(im["name"])
        if kept:
            for sh in kept:
                el.append(sh)
            continue
        for label, poly in im["polys"]:
            ET.SubElement(el, "polygon", label=label, source="auto", occluded="0",
                          points=";".join(f"{x:.2f},{y:.2f}" for x, y in poly),
                          z_order="0")
    ET.indent(root, "  ")
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            + ET.tostring(root, encoding="unicode") + "\n")


def overlay(img: np.ndarray, polys: list[tuple[str, np.ndarray]]) -> np.ndarray:
    vis = img.copy()
    rng = np.random.default_rng(0)
    for label, poly in polys:
        c = rng.integers(60, 255, 3).tolist()
        layer = vis.copy()
        cv2.fillPoly(layer, [poly.astype(np.int32)], c)
        vis = cv2.addWeighted(layer, 0.35, vis, 0.65, 0)
        cv2.polylines(vis, [poly.astype(np.int32)], True, c, 3)
        cv2.putText(vis, label, tuple(poly[0].astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
    return vis


# ----------------------------------------------------------------------- eval (GT)

def gt_rooms(gt_root: Path, name: str) -> list[tuple[str, np.ndarray]]:
    from PIL import Image
    ins = np.array(Image.open(gt_root / "instance/test" / name))
    sem = np.array(Image.open(gt_root / "semantic/test" / name))
    h, w = ins.shape
    out = []
    for i in np.unique(ins):
        if i == 0:
            continue
        m = ins == i
        if m.sum() >= 0.001 * h * w:
            out.append((CLASS_NAMES[int(np.bincount(sem[m]).argmax())], m))
    return out


def score(pred: list[tuple[str, np.ndarray]],
          gts: list[tuple[str, np.ndarray]]) -> list[tuple[float, bool]]:
    """Pour chaque pièce GT : (meilleur IoU, label prédit correct)."""
    out = []
    for gname, gm in gts:
        best, best_ok = 0.0, False
        for pname, pm in pred:
            inter = float((pm & gm).sum())
            if not inter:
                continue
            iou = inter / float((pm | gm).sum())
            if iou > best:
                best, best_ok = iou, pname == gname
        out.append((best, best_ok))
    return out


# ---------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=Path, required=True, help="dossier de plans")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--walls", choices=("model", "threshold"), default="model")
    ap.add_argument("--wall-ckpt", default=WALL_CKPT)
    ap.add_argument("--obb-weights", default=OBB_WEIGHTS)
    ap.add_argument("--no-openings", action="store_true",
                    help="sauter la détection d'ouvertures (plus rapide, fuit aux portes)")
    ap.add_argument("--no-ocr", action="store_true",
                    help="ne pas labelliser : tous les polygones sortent en --default-label")
    ap.add_argument("--default-label", default="Entry")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--close", type=int, default=5)
    ap.add_argument("--min-frac", type=float, default=0.003)
    ap.add_argument("--eps", type=float, default=0.006, help="simplification du contour")
    ap.add_argument("--min-solid", type=float, default=0.3,
                    help="part minimale du pourtour tombant sur du mur épais "
                         "(0 = tout garder, 0.6 = 86 %% de précision mais 22 %% de rappel)")
    ap.add_argument("--merge-with", type=Path, default=None,
                    help="export CVAT existant : ses frames déjà annotées sont "
                         "recopiées telles quelles au lieu d'être pré-annotées")
    ap.add_argument("--viz", action="store_true", help="overlay PNG par plan dans out/viz")
    ap.add_argument("--eval-gt", type=Path, default=None,
                    help="racine d'un dataset panoptique pour mesurer IoU et labels")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    existing = load_existing(args.merge_with) if args.merge_with else {}

    files = sorted(p for p in args.images.iterdir()
                   if p.suffix.lower() in (".png", ".jpg", ".jpeg"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        sys.exit(f"aucune image dans {args.images}")

    device = "cpu"
    wall_fn = solid_walls
    if args.walls == "model":
        import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        wall_fn = WallModel(args.wall_ckpt, device)

    yolo = None
    if not args.no_openings:
        from ultralytics import YOLO
        yolo = YOLO(args.obb_weights)

    lab = None if args.no_ocr else Labeller(args.default_label)

    args.out.mkdir(parents=True, exist_ok=True)
    if args.viz:
        (args.out / "viz").mkdir(exist_ok=True)

    images, report, ious, label_ok = [], [], [], []
    for p in files:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        if p.name in existing:
            # déjà annotée à la main : on la recopie sans dépenser un passage
            # modèle + OCR dessus
            images.append({"name": p.name, "w": w, "h": h, "polys": []})
            print(f"  {p.name[:44]:46s} déjà annotée — conservée", flush=True)
            continue
        walls = wall_fn(img)
        quads, furn = detect_boxes(yolo, p, device, args.conf) if yolo is not None \
            else (np.empty((0, 4, 2)), np.empty((0, 4, 2)))
        sealed = seal(walls, quads)
        thick = thick_walls(sealed)
        masks = extract_rooms(sealed, args.close, args.min_frac)

        grow = half_thickness(walls)
        hits = lab.hits(img) if lab else []
        polys, unsure = [], 0
        for m in masks:
            # deux rejets, mesurés sur le split test de fr_panoptic_lot01 :
            # mobilier seul 43 % -> 52 % de précision à rappel constant,
            # + pourtour épais >= 30 % : 65 % pour 2 points de rappel.
            if boundary_solidity(m, thick) < args.min_solid:
                continue
            if len(furn) and covered_by(m, furn) >= 0.5:
                continue
            poly = polygonize(m, grow, args.eps)
            if poly is None:
                continue
            if lab:
                name, sure = lab.label_for(poly, hits)
                unsure += not sure
            else:
                name, sure = args.default_label, False
                unsure += 1
            polys.append((name, poly))

        images.append({"name": p.name, "w": w, "h": h, "polys": polys})
        report.append({"image": p.name, "pieces": len(polys),
                       "sans_label_ocr": unsure, "ouvertures": int(len(quads))})
        print(f"  {p.name[:44]:46s} {len(polys):2d} pièces | "
              f"{unsure:2d} sans libellé | {len(quads):3d} ouvertures", flush=True)

        if args.viz:
            cv2.imwrite(str(args.out / "viz" / p.name), overlay(img, polys))

        if args.eval_gt:
            pred = [(n, cv2.fillPoly(np.zeros((h, w), np.uint8),
                                     [pl.astype(np.int32)], 1).astype(bool))
                    for n, pl in polys]
            for iou, ok in score(pred, gt_rooms(args.eval_gt, p.name)):
                ious.append(iou)
                label_ok.append(ok)

    (args.out / "rooms_preannotations.xml").write_text(xml_for(images, existing))
    (args.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    total = sum(r["pieces"] for r in report)
    unsure = sum(r["sans_label_ocr"] for r in report)
    kept = sum(1 for im in images if im["name"] in existing)
    print(f"\n{len(images)} plans | {total} polygones "
          f"({total / max(len(images) - kept, 1):.1f} par plan pré-annoté)")
    if kept:
        print(f"  {kept} frames déjà annotées recopiées intactes")
    print(f"  labellisés par OCR : {total - unsure} ({(total - unsure) / max(total, 1):.0%}) — "
          f"le reste sort en « {args.default_label} », à corriger au clic droit")
    print(f"  XML : {args.out / 'rooms_preannotations.xml'}")
    if ious:
        a = np.array(ious)
        print(f"\néval sur {len(a)} pièces GT : IoU moyen {a.mean():.3f} | "
              f"IoU>=.5 {np.mean(a >= .5):.1%} | IoU>=.7 {np.mean(a >= .7):.1%}")
        m = a >= 0.5
        if m.any():
            print(f"  label correct sur les pièces retrouvées (IoU>=.5) : "
                  f"{np.mean(np.array(label_ok)[m]):.1%}")


if __name__ == "__main__":
    main()
