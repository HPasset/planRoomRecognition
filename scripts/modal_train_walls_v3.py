"""Modal Labs wrapper pour fine-tuner wall_only_dwg_v3 sur A10G.

Particularité v3 : **init depuis wall_only_dwg_v2/best.pt** (pas le baseline
COCO public). Le trainer charge les poids du checkpoint v2 dans le modèle
juste avant `fit()`, puis démarre l'entraînement avec epoch=0 et nouveau
optimizer (== fine-tune from v2 weights, pas resume v2 training).

Dataset : data/processed/walls_dwg_only_v3 (149 DWG + N FR annotés).
Volume Modal : batia-walls-dwg-v3 (séparé de v1/v2).

Usage :
    # 1. Upload dataset (une seule fois après build)
    modal volume create batia-walls-dwg-v3
    modal volume put batia-walls-dwg-v3 data/processed/walls_dwg_only_v3 /walls_dwg_only_v3

    # 2. Lance training détaché (--detach OBLIGATOIRE)
    modal run --detach scripts/modal_train_walls_v3.py::train
"""
from __future__ import annotations

import sys
from pathlib import Path

import modal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_LOCAL = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only_v3"
CONFIG_LOCAL = PROJECT_ROOT / "configs" / "segmentation" / "wall_only_dwg_v3.yaml"
V2_CKPT_LOCAL = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v2" / "checkpoints" / "best.pt"
RUNS_LOCAL = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v3"


app = modal.App("batia-walls-training-v3")

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

dataset_volume = modal.Volume.from_name(
    "batia-walls-dwg-v3", create_if_missing=True,
)
runs_volume = modal.Volume.from_name(
    "batia-walls-runs", create_if_missing=True,
)


@app.function(
    image=image,
    volumes={"/data": dataset_volume},
    timeout=600,
)
def check_dataset() -> dict:
    import json
    p = Path("/data/walls_dwg_only_v3")
    if not p.exists():
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
    gpu="A10G",
    volumes={
        "/data": dataset_volume,
        "/runs": runs_volume,
    },
    timeout=3600 * 4,
    secrets=[modal.Secret.from_name("wandb-secret")],
)
def train_remote(
    config_yaml_text: str,
    v2_ckpt_bytes: bytes,
    config_filename: str = "wall_only_dwg_v3.yaml",
):
    """Fine-tune depuis v2 best.pt sur dataset v3 (DWG + FR)."""
    import os
    import torch
    os.environ["PYTHONPATH"] = "/workspace/batia"
    os.chdir("/workspace/batia")

    cfg_path = Path("/workspace/batia/configs/segmentation") / config_filename
    cfg_path.write_text(config_yaml_text, encoding="utf-8")

    # Écrit v2 best.pt en local pour le charger ensuite
    v2_ckpt_path = Path("/workspace/batia/v2_init.pt")
    v2_ckpt_path.write_bytes(v2_ckpt_bytes)
    print(f"[modal] v2 init checkpoint reçu ({len(v2_ckpt_bytes)/1e6:.1f} MB)", flush=True)

    runs_volume.reload()

    sys.path.insert(0, "/workspace/batia")
    from src.segmentation.config import load_config
    from src.segmentation.trainer import Trainer

    cfg = load_config(str(cfg_path))

    # Si déjà un last.pt sur le volume v3, on laisse Trainer auto-resume
    # (cas reprise après timeout). Sinon, on init depuis v2.
    v3_last = Path("/runs/wall_only_dwg_v3/checkpoints/last.pt")

    # Setup commit hook
    _orig_save_state = Trainer._save_state

    def _save_state_and_commit(self, name: str):
        _orig_save_state(self, name)
        runs_volume.commit()
        print(f"[modal] volume committed après save {name}", flush=True)

    Trainer._save_state = _save_state_and_commit

    trainer = Trainer(cfg, device="cuda")

    if not v3_last.exists():
        # Premier run : on charge les poids v2 dans le modèle
        v2_ckpt = torch.load(v2_ckpt_path, map_location="cuda", weights_only=False)
        missing, unexpected = trainer.model.load_state_dict(
            v2_ckpt["model_state_dict"], strict=False,
        )
        print(f"[modal] v2 weights chargés. "
              f"missing={len(missing)}, unexpected={len(unexpected)}", flush=True)
    else:
        print("[modal] v3 last.pt présent → auto-resume", flush=True)

    trainer.fit()
    runs_volume.commit()


@app.local_entrypoint()
def train():
    print("=== Étape 1 : Vérification dataset Modal volume v3 ===")
    state = check_dataset.remote()
    print(f"  Dataset state: {state}")

    if not state["present"]:
        print("\n  ❌ Dataset absent. Run d'abord :")
        print(f"     modal volume put batia-walls-dwg-v3 "
              f"{DATASET_LOCAL} /walls_dwg_only_v3")
        sys.exit(1)

    print(f"\n  Train/Val/Test : "
          f"{state['n_train']}/{state['n_val']}/{state['n_test']}")

    print("\n=== Étape 2 : Lecture du config + checkpoint v2 ===")
    if not CONFIG_LOCAL.exists():
        print(f"  ❌ Config absent : {CONFIG_LOCAL}")
        sys.exit(1)
    if not V2_CKPT_LOCAL.exists():
        print(f"  ❌ Checkpoint v2 absent : {V2_CKPT_LOCAL}")
        print(f"     Download d'abord : modal volume get batia-walls-runs "
              f"/wall_only_dwg_v2/checkpoints/best.pt {V2_CKPT_LOCAL}")
        sys.exit(1)
    config_text = CONFIG_LOCAL.read_text(encoding="utf-8")
    v2_ckpt_bytes = V2_CKPT_LOCAL.read_bytes()
    print(f"  Config lu ({len(config_text)} bytes).")
    print(f"  v2 ckpt lu ({len(v2_ckpt_bytes)/1e6:.1f} MB).")

    print("\n=== Étape 3 : Training distant détaché (A10G, init from v2) ===")
    print("  (~30-45 min estimé selon N. .spawn() = détaché.)")
    function_call = train_remote.spawn(config_text, v2_ckpt_bytes)
    print(f"  FunctionCall ID : {function_call.object_id}")
    print("  Run détaché lancé.")

    print("\n=== Suite ===")
    print("  modal app list")
    print(f"  modal volume get batia-walls-runs "
          f"/wall_only_dwg_v3/checkpoints/best.pt "
          f"{RUNS_LOCAL}/checkpoints/best.pt")
    print("\nWandb : project batia-segmentation, run wall_only_dwg_v3.")
