"""Eval YOLO Brique A sur le test set + génère overlays prédictions.

Usage:
    python scripts/eval_brique_a.py

Sortie:
    - runs/detect/brique_a_v1_eval_test/ : métriques per-class sur test set
    - runs/detect/brique_a_v1_pred_test/ : images test avec bbox + labels dessinés
"""
from __future__ import annotations
import os
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from pathlib import Path
from ultralytics import YOLO


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = PROJECT_ROOT / "runs/detect/runs/detect/brique_a_v1/weights/best.pt"
DATA_YAML = PROJECT_ROOT / "data/processed/datasets/brique_a/dataset.yaml"
TEST_IMAGES_DIR = PROJECT_ROOT / "data/processed/datasets/brique_a/images/test"

OUT_PROJECT = PROJECT_ROOT / "runs/detect"
EVAL_NAME = "brique_a_v1_eval_test"
PRED_NAME = "brique_a_v1_pred_test"


def main():
    if not MODEL_PATH.exists():
        raise SystemExit(f"❌ Modèle introuvable : {MODEL_PATH}")
    if not DATA_YAML.exists():
        raise SystemExit(f"❌ dataset.yaml introuvable : {DATA_YAML}")

    print(f"📦 Chargement modèle : {MODEL_PATH}")
    model = YOLO(str(MODEL_PATH))

    # === Étape 1 : Eval métriques sur test set ===
    print("\n" + "=" * 70)
    print("📊 ÉVALUATION SUR TEST SET (17 plans)")
    print("=" * 70)
    metrics = model.val(
        data=str(DATA_YAML),
        split="test",
        device="mps",
        project=str(OUT_PROJECT),
        name=EVAL_NAME,
        exist_ok=True,
        verbose=True,
    )
    print(f"\n✓ Métriques test set sauvegardées : {OUT_PROJECT / EVAL_NAME}")

    # === Étape 2 : Prédictions avec overlay sur images test ===
    print("\n" + "=" * 70)
    print("🎨 GÉNÉRATION OVERLAYS PRÉDICTIONS")
    print("=" * 70)
    model.predict(
        source=str(TEST_IMAGES_DIR),
        conf=0.25,           # seuil confiance pour afficher une bbox
        iou=0.45,            # NMS threshold
        device="mps",
        project=str(OUT_PROJECT),
        name=PRED_NAME,
        save=True,            # sauvegarde images annotées
        save_txt=False,       # pas besoin des .txt YOLO format
        save_conf=False,
        line_width=2,
        exist_ok=True,
        verbose=False,
    )
    out_dir = OUT_PROJECT / PRED_NAME
    images = sorted(out_dir.glob("*.png")) + sorted(out_dir.glob("*.jpg"))
    print(f"\n✓ {len(images)} overlays générés dans : {out_dir}")
    print(f"\n📂 Pour les voir : open {out_dir}")


if __name__ == "__main__":
    main()
