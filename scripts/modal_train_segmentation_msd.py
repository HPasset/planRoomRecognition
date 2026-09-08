"""Modal Labs wrapper pour entraîner la segmentation **Stage A MSD** sur GPU.

Pré-entraînement Mask2Former Swin-S sur le jeu panoptique MSD (Modified Swiss
Dwellings) → renfort murs + pièces, domaine européen, licence CC BY 4.0.
Plus simple que le wrapper walls v3 : **pas de poids v2 à injecter** — Stage A
part du backbone COCO public (`facebook/mask2former-swin-small-coco-panoptic`),
chargé par le modèle lui-même.

Dataset local : data/processed/msd_panoptic (4834/269/269, ~155 Mo).
Config locale : configs/segmentation/stage_a_msd.yaml (chemins LOCAUX). Ce
wrapper réécrit `dataset_root`/`output_dir` vers les mounts Modal à la volée,
donc la config reste utilisable en local sans modification.

Volumes Modal :
  - batia-msd-panoptic : le dataset (monté sur /data → /data/msd_panoptic)
  - batia-seg-runs     : les checkpoints/runs (monté sur /runs)

Usage :
    # 1. Upload du dataset (une seule fois)
    modal volume create batia-msd-panoptic
    modal volume put batia-msd-panoptic data/processed/msd_panoptic /msd_panoptic

    # 2. Lance l'entraînement détaché (--detach OBLIGATOIRE, sinon tué à la
    #    sortie du local entrypoint car on utilise .spawn())
    modal run --detach scripts/modal_train_segmentation_msd.py::train

    # 3. Reprise après timeout : relancer la MÊME commande — le Trainer
    #    auto-resume depuis /runs/stage_a_msd_v1/checkpoints/last.pt (committé
    #    sur le volume à chaque save).

    # 4. Récupérer le best :
    modal volume get batia-seg-runs /stage_a_msd_v1/checkpoints/best.pt \
        runs/segmentation/stage_a_msd_v1/checkpoints/best.pt
"""
from __future__ import annotations

import sys
from pathlib import Path

import modal
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_LOCAL = PROJECT_ROOT / "data" / "processed" / "msd_panoptic"
CONFIG_LOCAL = PROJECT_ROOT / "configs" / "segmentation" / "stage_a_msd.yaml"

# Chemins côté Modal (mounts des volumes)
DATA_REMOTE = "/data/msd_panoptic"
OUTPUT_REMOTE = "/runs/stage_a_msd_v1"
CONFIG_FILENAME = "stage_a_msd_modal.yaml"


app = modal.App("batia-seg-msd-stage-a")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.4.1", "torchvision==0.19.1",
        "transformers==4.45.2",
        "albumentations==1.4.20",
        "opencv-python-headless==4.10.0.84",
        "pydantic==2.9.2",
        "pyyaml==6.0.2",
        "numpy==1.26.4",
        "pillow==10.4.0",
        "wandb==0.19.1",
    )
    .add_local_dir(str(PROJECT_ROOT / "src"), remote_path="/workspace/batia/src")
    .add_local_dir(str(PROJECT_ROOT / "scripts"), remote_path="/workspace/batia/scripts")
    .add_local_dir(str(PROJECT_ROOT / "configs"), remote_path="/workspace/batia/configs")
)

dataset_volume = modal.Volume.from_name("batia-msd-panoptic", create_if_missing=True)
runs_volume = modal.Volume.from_name("batia-seg-runs", create_if_missing=True)


@app.function(image=image, volumes={"/data": dataset_volume}, timeout=600)
def check_dataset() -> dict:
    import json
    p = Path(DATA_REMOTE)
    if not (p / "splits.json").exists():
        return {"present": False}
    splits = json.loads((p / "splits.json").read_text())
    return {
        "present": True,
        "n_train": len(splits.get("train", [])),
        "n_val": len(splits.get("val", [])),
        "n_test": len(splits.get("test", [])),
    }


@app.function(
    image=image,
    gpu="A100",
    volumes={"/data": dataset_volume, "/runs": runs_volume},
    timeout=3600 * 24,          # Stage A long (80 epochs) ; auto-resume si dépassé
    secrets=[modal.Secret.from_name("wandb-secret")],
)
def train_remote(config_yaml_text: str):
    """Stage A MSD : entraînement depuis le backbone COCO public (pas d'init v2)."""
    import os
    os.environ["PYTHONPATH"] = "/workspace/batia"
    os.environ.setdefault("WANDB_MODE", "online")   # stream live (pas offline)
    # Réduit la fragmentation mémoire CUDA (l'OOM A10G laissait ~774 Mo réservés
    # non-alloués) — combiné au bf16 de la config, donne de la marge en 768/batch4.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
    os.chdir("/workspace/batia")

    cfg_path = Path("/workspace/batia/configs/segmentation") / CONFIG_FILENAME
    cfg_path.write_text(config_yaml_text, encoding="utf-8")

    runs_volume.reload()

    sys.path.insert(0, "/workspace/batia")
    from src.segmentation.config import load_config
    from src.segmentation.trainer import Trainer

    cfg = load_config(str(cfg_path))

    # Fail-fast si wandb demandé mais clé absente : évite un wandb.init() headless
    # qui traîne/échoue après avoir déjà allumé le GPU (= GPU gaspillé).
    if cfg.logging.tracker == "wandb" and not os.environ.get("WANDB_API_KEY"):
        raise RuntimeError(
            "WANDB_API_KEY absent — vérifie le secret Modal 'wandb-secret' "
            "(doit contenir WANDB_API_KEY), ou mets logging.tracker: none."
        )
    print(f"[modal] wandb tracker={cfg.logging.tracker} "
          f"project={cfg.logging.project} run={cfg.run_name}", flush=True)

    # Commit du volume runs à chaque sauvegarde de checkpoint (persiste les
    # poids + permet l'auto-resume après timeout).
    _orig_save_state = Trainer._save_state

    def _save_state_and_commit(self, name: str):
        _orig_save_state(self, name)
        runs_volume.commit()
        print(f"[modal] volume committed après save {name}", flush=True)

    Trainer._save_state = _save_state_and_commit

    last_ckpt = Path(OUTPUT_REMOTE) / "checkpoints" / "last.pt"
    print(f"[modal] resume depuis {last_ckpt} ? {last_ckpt.exists()}", flush=True)

    trainer = Trainer(cfg, device="cuda")
    trainer.fit()
    runs_volume.commit()
    print("[modal] training terminé, volume committed.", flush=True)


def _build_modal_config_text() -> str:
    """Lit la config locale et réécrit dataset_root/output_dir vers les mounts
    Modal (la config locale reste intacte et utilisable hors Modal)."""
    raw = yaml.safe_load(CONFIG_LOCAL.read_text(encoding="utf-8"))
    raw["data"]["dataset_root"] = DATA_REMOTE
    raw["checkpoint"]["output_dir"] = OUTPUT_REMOTE
    return yaml.safe_dump(raw, sort_keys=False, allow_unicode=True)


@app.local_entrypoint()
def train():
    print("=== Étape 1 : Vérification du dataset sur le volume Modal ===")
    state = check_dataset.remote()
    print(f"  Dataset state: {state}")
    if not state["present"]:
        print("\n  ❌ Dataset absent du volume. Upload d'abord :")
        print("     modal volume create batia-msd-panoptic")
        print(f"     modal volume put batia-msd-panoptic {DATASET_LOCAL} /msd_panoptic")
        sys.exit(1)
    print(f"  Train/Val/Test : "
          f"{state['n_train']}/{state['n_val']}/{state['n_test']}")

    print("\n=== Étape 2 : Préparation de la config (mounts Modal) ===")
    if not CONFIG_LOCAL.exists():
        print(f"  ❌ Config absente : {CONFIG_LOCAL}")
        sys.exit(1)
    config_text = _build_modal_config_text()
    print(f"  dataset_root → {DATA_REMOTE}")
    print(f"  output_dir   → {OUTPUT_REMOTE}")

    print("\n=== Étape 3 : Training distant détaché (A10G) ===")
    print("  Stage A = 80 epochs depuis backbone COCO. .spawn() = détaché.")
    call = train_remote.spawn(config_text)
    print(f"  FunctionCall ID : {call.object_id}")
    print("  Run détaché lancé.")

    print("\n=== Suite ===")
    print("  modal app list")
    print("  modal volume get batia-seg-runs /stage_a_msd_v1/checkpoints/best.pt \\")
    print("    runs/segmentation/stage_a_msd_v1/checkpoints/best.pt")
    print("\nWandb : project batia-segmentation, run stage_a_msd_v1.")
