"""Modal Labs wrapper pour entraîner wall_only_dwg_v2 (DWG-only) sur A10G.

Différences vs modal_train_walls.py (v1 mix CC+DWG) :
- Volume dataset : `batia-walls-dwg-v2` (séparé de `batia-walls-combined`)
- Source local : `data/processed/walls_dwg_only_v2/`
- Pas d'oversampling (149 paires DWG-only, pas besoin)
- Config : `configs/segmentation/wall_only_dwg_v2.yaml`

Usage :
    # 1. Upload dataset (une seule fois)
    modal volume create batia-walls-dwg-v2
    modal volume put batia-walls-dwg-v2 data/processed/walls_dwg_only_v2 /walls_dwg_only_v2

    # 2. Lance training détaché
    modal run scripts/modal_train_walls_v2.py::train
"""
from __future__ import annotations

import sys
from pathlib import Path

import modal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_LOCAL = PROJECT_ROOT / "data" / "processed" / "walls_dwg_only_v2"
CONFIG_LOCAL = PROJECT_ROOT / "configs" / "segmentation" / "wall_only_dwg_v2.yaml"
RUNS_LOCAL = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_dwg_v2"


app = modal.App("batia-walls-training-v2")

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
    "batia-walls-dwg-v2", create_if_missing=True,
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
    """Vérifie l'état du dataset uploadé."""
    import json
    p = Path("/data/walls_dwg_only_v2")
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
    timeout=3600 * 4,    # 4h safety (estim 45 min)
    secrets=[modal.Secret.from_name("wandb-secret")],
)
def train_remote(
    config_yaml_text: str,
    config_filename: str = "wall_only_dwg_v2.yaml",
):
    """Entraîne wall_only_dwg_v2 sur A10G."""
    import os
    os.environ["PYTHONPATH"] = "/workspace/batia"
    os.chdir("/workspace/batia")

    cfg_path = Path("/workspace/batia/configs/segmentation") / config_filename
    cfg_path.write_text(config_yaml_text, encoding="utf-8")

    runs_volume.reload()

    sys.path.insert(0, "/workspace/batia")
    from src.segmentation.config import load_config
    from src.segmentation.trainer import Trainer

    cfg = load_config(str(cfg_path))

    _orig_save_state = Trainer._save_state

    def _save_state_and_commit(self, name: str):
        _orig_save_state(self, name)
        runs_volume.commit()
        print(f"[modal] volume committed après save {name}", flush=True)

    Trainer._save_state = _save_state_and_commit

    trainer = Trainer(cfg, device="cuda")
    trainer.fit()

    runs_volume.commit()


@app.local_entrypoint()
def train():
    """Point d'entrée local. Vérifie dataset, build config, lance training."""
    print("=== Étape 1 : Vérification dataset Modal volume ===")
    state = check_dataset.remote()
    print(f"  Dataset state: {state}")

    if not state["present"]:
        print("\n  ❌ Dataset absent. Run d'abord :")
        print(f"     modal volume put batia-walls-dwg-v2 "
              f"{DATASET_LOCAL} /walls_dwg_only_v2")
        sys.exit(1)

    expected_train = 105
    expected_val = 23
    expected_test = 21
    if (state["n_train"] != expected_train or state["n_val"] != expected_val
            or state["n_test"] != expected_test):
        print(f"\n  ⚠️  Counts inattendus (attendu : {expected_train}/{expected_val}/"
              f"{expected_test}, vu : {state['n_train']}/{state['n_val']}/{state['n_test']}).")
        print("  Continue quand même.")

    print("\n=== Étape 2 : Lecture du config local ===")
    if not CONFIG_LOCAL.exists():
        print(f"  ❌ Config absent : {CONFIG_LOCAL}")
        sys.exit(1)
    config_text = CONFIG_LOCAL.read_text(encoding="utf-8")
    print(f"  Config lu ({len(config_text)} bytes).")

    print("\n=== Étape 3 : Training distant détaché (A10G image 640 batch 4) ===")
    print("  (~45 min estimé, ~0.85 €. .spawn() = survit toute déconnexion.)")
    function_call = train_remote.spawn(config_text)
    print(f"  FunctionCall ID : {function_call.object_id}")
    print("  Run détaché lancé. Le local peut sortir.")

    print("\n=== Suite ===")
    print("  modal app list               # voir le statut")
    print(f"  modal volume get batia-walls-runs "
          f"/wall_only_dwg_v2/checkpoints/best.pt "
          f"{RUNS_LOCAL}/checkpoints/best.pt")
    print("\nFait. Voir wandb (project batia-segmentation, run wall_only_dwg_v2).")
