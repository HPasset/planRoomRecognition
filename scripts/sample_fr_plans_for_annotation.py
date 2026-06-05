"""Sélectionne un sous-ensemble représentatif de plans FR pour annotation
CVAT. Inclut systématiquement les 8 plans du test_plans/ existant (eval v2)
pour permettre une mesure IoU directe v3 vs v2.

Output :
- data/raw/plans_fr_annotation_batch_1/    (PNG prêts à uploader CVAT)
- data/raw/plans_fr_annotation_batch_1/manifest.md  (liste + provenance)
"""
from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_POOL = PROJECT_ROOT / "data" / "raw" / "plans_fr"
TEST_PLANS = PROJECT_ROOT / "experiments" / "wall_detection_eval" / "test_plans"
DEFAULT_OUT = PROJECT_ROOT / "data" / "raw" / "plans_fr_annotation_batch_1"

SEED = 42


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=25,
                    help="Nombre total de plans à sélectionner (8 forcés inclus)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if not SOURCE_POOL.exists():
        raise SystemExit(f"Source absente : {SOURCE_POOL}")

    if args.out.exists():
        if args.overwrite:
            shutil.rmtree(args.out)
        else:
            raise SystemExit(f"Output existe déjà : {args.out}. Utilise --overwrite.")
    args.out.mkdir(parents=True)

    # Pool source
    all_plans = sorted(SOURCE_POOL.glob("*.png")) + sorted(SOURCE_POOL.glob("*.jpg"))
    pool_names = {p.name for p in all_plans}
    print(f"Pool source plans_fr : {len(all_plans)} plans")

    # Forcer l'inclusion des 8 plans test (qu'on a utilisés en eval v2)
    forced_names = sorted(p.name for p in TEST_PLANS.glob("*.png"))
    forced_in_pool = [n for n in forced_names if n in pool_names]
    missing = [n for n in forced_names if n not in pool_names]
    if missing:
        print(f"⚠ {len(missing)} plans test absents du pool : {missing}")
    print(f"Forced (test_plans inclus) : {len(forced_in_pool)}")

    # Sample du reste
    remaining_pool = [p.name for p in all_plans if p.name not in forced_names]
    rng = random.Random(SEED)
    rng.shuffle(remaining_pool)
    n_to_sample = max(0, args.target - len(forced_in_pool))
    sampled = remaining_pool[:n_to_sample]
    print(f"Random sample (seed={SEED}) : {len(sampled)} plans")

    selected = forced_in_pool + sampled

    # Copy + manifest
    manifest_lines = [
        "# Batch 1 — sélection FR pour annotation CVAT",
        "",
        f"Total : **{len(selected)} plans** ({len(forced_in_pool)} forcés + "
        f"{len(sampled)} échantillonnés seed={SEED})",
        "",
        f"Source : `{SOURCE_POOL.relative_to(PROJECT_ROOT)}` ({len(all_plans)} plans)",
        "",
        "## Plans inclus",
        "",
    ]
    for i, name in enumerate(selected, 1):
        src = SOURCE_POOL / name
        dst = args.out / name
        shutil.copy2(src, dst)
        tag = "test_plans" if name in forced_names else "random"
        manifest_lines.append(f"{i:2d}. `{name}`  *({tag})*")
    manifest_lines.extend([
        "",
        "## Workflow",
        "",
        "1. Login CVAT (https://app.cvat.ai)",
        "2. Project `batia-walls-fr` → Create new task",
        "3. Drag-drop **tout le contenu** de ce dossier",
        "4. Annoter selon `docs/cvat_walls_annotation_guide.md`",
        "5. Export → conversion → fine-tune v3",
    ])
    (args.out / "manifest.md").write_text("\n".join(manifest_lines))

    print(f"\n=== {len(selected)} plans copiés dans {args.out} ===")
    print(f"Manifeste : {args.out / 'manifest.md'}")


if __name__ == "__main__":
    main()
