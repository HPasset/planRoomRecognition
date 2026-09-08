"""Convertit un export CVAT (format "Segmentation mask 1.1") en dataset
au format walls_dwg_only (consommable par scripts/build_walls_dwg_only_dataset.py
puis par la pipeline d'entraînement Mask2Former).

Format CVAT "Segmentation mask 1.1" attendu (après dézip) :
    <export_root>/
    ├── ImageSets/Segmentation/
    │   └── default.txt          (liste des noms d'images, 1 par ligne)
    ├── JPEGImages/               (images sources, souvent .png ici malgré le nom)
    │   └── <plan_name>.png
    ├── SegmentationClass/
    │   └── <plan_name>.png       (masque RGB, classe codée en couleur)
    └── labelmap.txt              (mapping nom_classe → R,G,B)

Output (format batIA `dwg_walls`) :
    <out>/
    ├── meta.json                 (1 entrée par paire)
    ├── train/
    │   ├── img_NNNN.png          (image source)
    │   └── mask_NNNN.png         (masque binaire 0/255)
    ├── val/
    └── test/

Usage :
    .venv/bin/python scripts/cvat_to_walls_dataset.py \\
        --cvat-export /Users/.../Downloads/batia-walls-fr-export \\
        --out data/processed/fr_walls \\
        --split-mode stratified \\
        --id-prefix fr_

Puis on combine avec dwg_walls_v2 via build_dwg_walls_v3.py (voir suite).
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED = 42
SPLITS = ("train", "val", "test")
SPLIT_RATIO = {"train": 0.70, "val": 0.15, "test": 0.15}


def parse_labelmap(path: Path) -> dict[str, tuple[int, int, int]]:
    """Lit labelmap.txt → {class_name: (R, G, B)}.

    Format CVAT labelmap.txt :
        <class_name>:<R>,<G>,<B>::<attributes>
    """
    label_to_rgb: dict[str, tuple[int, int, int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) < 2:
            continue
        cls = parts[0].strip()
        rgb_str = parts[1].strip()
        try:
            r, g, b = [int(x) for x in rgb_str.split(",")]
        except ValueError:
            continue
        label_to_rgb[cls] = (r, g, b)
    return label_to_rgb


def rgb_mask_to_binary(rgb_mask: np.ndarray, wall_rgb: tuple[int, int, int]) -> np.ndarray:
    """Convertit un masque RGB CVAT en masque binaire 0/255 pour la classe Wall."""
    r, g, b = wall_rgb
    match = (rgb_mask[..., 0] == r) & (rgb_mask[..., 1] == g) & (rgb_mask[..., 2] == b)
    return (match.astype(np.uint8) * 255)


def stratified_split(stems: list[str], ratio: dict, seed: int) -> dict[str, list[str]]:
    """Split simple sans stratification par taille (pas de signal taille ici).
    Si tu veux stratifier par densité de mur ou source, étendre cette fonction."""
    rng = random.Random(seed)
    shuffled = sorted(stems)
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = round(n * ratio["train"])
    n_val = round(n * ratio["val"])
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train:n_train + n_val],
        "test": shuffled[n_train + n_val:],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cvat-export", type=Path, required=True,
                    help="Dossier d'export CVAT dézippé")
    ap.add_argument("--out", type=Path, required=True,
                    help="Dossier de sortie au format dwg_walls")
    ap.add_argument("--source-images", type=Path, default=None,
                    help="Dossier alternatif où chercher les images sources "
                         "si le ZIP CVAT n'inclut pas JPEGImages/ "
                         "(cas free tier app.cvat.ai sans 'Save images'). "
                         "Le matching se fait par stem de filename.")
    ap.add_argument("--id-prefix", type=str, default="fr_",
                    help="Préfixe d'ID (utile pour distinguer la source)")
    ap.add_argument("--split-mode", choices=["stratified", "all-train"],
                    default="stratified",
                    help="stratified = 70/15/15, all-train = tout en train")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    cvat = args.cvat_export
    out = args.out

    if not cvat.exists():
        print(f"ERROR: Le dossier d'export CVAT n'existe pas : {cvat}")
        print("\nWorkflow attendu :")
        print("  1. Annoter les plans dans CVAT (project batia-walls-fr)")
        print("  2. Project Actions → Export project dataset")
        print("  3. Format = 'Segmentation mask 1.1'")
        print("     - Cloud free : DÉCOCHE 'Save images' puis utilise --source-images")
        print("     - Self-hosted / Paid : coche 'Save images' (tout dans le ZIP)")
        print("  4. Download ZIP, dézipper dans ce chemin")
        print("  5. Relancer ce script")
        sys.exit(1)

    # Si l'export contient un sous-dossier task (project-level export),
    # on trouve le bon répertoire qui contient labelmap.txt.
    candidates = [cvat] + list(cvat.iterdir() if cvat.is_dir() else [])
    cvat_root = next((c for c in candidates
                      if c.is_dir() and (c / "labelmap.txt").exists()), None)
    if cvat_root is None:
        print(f"ERROR: labelmap.txt introuvable dans {cvat} ou ses sous-dossiers.")
        print("  Vérifie que l'export CVAT est bien au format")
        print("  'Segmentation mask 1.1' (pas COCO, pas YOLO, etc.)")
        sys.exit(1)
    if cvat_root != cvat:
        print(f"Sous-dossier task détecté : {cvat_root.name}")

    labelmap_path = cvat_root / "labelmap.txt"
    cvat_images_dir = cvat_root / "JPEGImages"
    masks_dir = cvat_root / "SegmentationClass"

    if not masks_dir.exists():
        print(f"ERROR: SegmentationClass/ absent dans {cvat_root}")
        sys.exit(1)

    # Détermine d'où viennent les images sources :
    #   1. --source-images si fourni
    #   2. sinon JPEGImages/ dans l'export CVAT
    #   3. sinon erreur (cas free tier sans 'Save images' coché)
    if args.source_images is not None:
        if not args.source_images.exists():
            print(f"ERROR: --source-images n'existe pas : {args.source_images}")
            sys.exit(1)
        images_dir = args.source_images
        print(f"Images sources : {images_dir} (via --source-images)")
    elif cvat_images_dir.exists():
        images_dir = cvat_images_dir
        print(f"Images sources : {images_dir} (depuis JPEGImages/ du ZIP)")
    else:
        print(f"ERROR: JPEGImages/ absent dans {cvat_root} ET pas de --source-images.")
        print("  Cas typique : export CVAT cloud free tier sans 'Save images'.")
        print("  Utilise --source-images <dossier> avec les PNG sources.")
        sys.exit(1)

    # Output
    if out.exists():
        if args.overwrite:
            shutil.rmtree(out)
        else:
            print(f"ERROR: {out} existe déjà. Utilise --overwrite.")
            sys.exit(1)
    for split in SPLITS:
        (out / split).mkdir(parents=True, exist_ok=True)

    # Parse labelmap
    label_to_rgb = parse_labelmap(labelmap_path)
    print(f"Labels CVAT trouvés : {list(label_to_rgb.keys())}")
    if "Wall" not in label_to_rgb:
        print("ERROR: pas de label 'Wall' dans labelmap.txt. "
              f"Trouvés : {list(label_to_rgb.keys())}")
        sys.exit(1)
    wall_rgb = label_to_rgb["Wall"]
    print(f"Wall RGB : {wall_rgb}")

    # Liste des paires
    image_files = sorted(images_dir.glob("*.png")) + sorted(images_dir.glob("*.jpg"))
    pairs = []
    for img_path in image_files:
        mask_candidates = [
            masks_dir / f"{img_path.stem}.png",
            masks_dir / img_path.name,
        ]
        mask_path = next((p for p in mask_candidates if p.exists()), None)
        if mask_path is None:
            print(f"  ⚠ pas de masque pour {img_path.name}, skip")
            continue
        pairs.append((img_path, mask_path))
    print(f"{len(pairs)} paires (image, masque) trouvées")

    if not pairs:
        print("Aucune paire valide. Stop.")
        sys.exit(1)

    # Stems pour split
    stems = [img.stem for img, _ in pairs]
    if args.split_mode == "stratified":
        split_assign = stratified_split(stems, SPLIT_RATIO, SEED)
    else:
        split_assign = {"train": stems, "val": [], "test": []}

    # Reverse map stem → split
    stem_to_split = {}
    for split, ss in split_assign.items():
        for s in ss:
            stem_to_split[s] = split

    # Copie + conversion
    new_splits: dict[str, list[dict]] = {s: [] for s in SPLITS}
    pair_idx = 0
    for img_path, mask_path in pairs:
        pair_idx += 1
        split = stem_to_split[img_path.stem]
        new_id = pair_idx
        new_img_name = f"img_{new_id:04d}.png"
        new_mask_name = f"mask_{new_id:04d}.png"

        # Copie image (en PNG quelle que soit l'extension d'origine)
        rgb = cv2.imread(str(img_path))
        cv2.imwrite(str(out / split / new_img_name), rgb)

        # Convertit masque RGB → binaire
        rgb_mask = cv2.cvtColor(cv2.imread(str(mask_path)), cv2.COLOR_BGR2RGB)
        wall_mask = rgb_mask_to_binary(rgb_mask, wall_rgb)
        cv2.imwrite(str(out / split / new_mask_name), wall_mask)

        pixel_ratio = float((wall_mask > 0).mean())
        new_splits[split].append({
            "id": new_id,
            "img": new_img_name,
            "mask": new_mask_name,
            "source_image": img_path.name,
            "source_set": f"cvat_{args.id_prefix.rstrip('_')}",
            "wall_pixel_ratio": round(pixel_ratio, 4),
        })

    # Meta
    out_meta = {
        "seed": SEED,
        "split_mode": args.split_mode,
        "source_cvat_export": str(cvat),
        "id_prefix": args.id_prefix,
        "build_notes": (
            f"Converti depuis export CVAT 'Segmentation mask 1.1'. "
            f"{len(pairs)} paires. Split {args.split_mode} (seed=42)."
        ),
        "splits": new_splits,
    }
    (out / "meta.json").write_text(json.dumps(out_meta, indent=2))

    # Bilan
    totals = {s: len(new_splits[s]) for s in SPLITS}
    print(f"\n=== Bilan {out.name} ===")
    print(f"Total : {sum(totals.values())} paires")
    for s in SPLITS:
        print(f"  {s:5s}: {totals[s]}")
    print(f"\nOutput : {out}")


if __name__ == "__main__":
    main()
