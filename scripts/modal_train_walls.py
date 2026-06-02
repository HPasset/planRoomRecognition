"""Modal Labs wrapper pour entraîner wall_only_stage_a_v1 (mix CC+DWG)
sur GPU cloud.

Usage local :
    modal run scripts/modal_train_walls.py::train

Étapes :
1. Upload du dataset `data/processed/walls_combined/` vers un Modal Volume
   persistant `batia-walls-combined` (1x setup, réutilisable).
2. Sync du code source `src/segmentation/` + `scripts/train_segmentation.py`
   + `configs/segmentation/` via mount.
3. Run training sur A10G GPU 24 GB VRAM, image_size 768, epochs 30.
4. À la fin, download les checkpoints best.pt + last.pt en local dans
   `runs/segmentation/wall_only_stage_a_v1/checkpoints/`.

Coût estimé : A10G ~$1.10/hr × ~30 min = ~0.55 € total.
"""
from __future__ import annotations

import sys
from pathlib import Path

import modal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_LOCAL = PROJECT_ROOT / "data" / "processed" / "walls_combined"
RUNS_LOCAL = PROJECT_ROOT / "runs" / "segmentation" / "wall_only_stage_a_v1"

# --- Modal app + image + volumes ---

app = modal.App("batia-walls-training")

# Image : CUDA 12.1 + PyTorch 2.2 + dépendances training
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")  # cv2 deps
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
    # Mount notre code source dans /workspace/batia
    .add_local_dir(
        str(PROJECT_ROOT / "src"),
        remote_path="/workspace/batia/src",
    )
    .add_local_dir(
        str(PROJECT_ROOT / "scripts"),
        remote_path="/workspace/batia/scripts",
    )
    .add_local_dir(
        str(PROJECT_ROOT / "configs"),
        remote_path="/workspace/batia/configs",
    )
)

# Volume persistant pour le dataset (upload 1x, réutilisé)
dataset_volume = modal.Volume.from_name(
    "batia-walls-combined", create_if_missing=True,
)
# Volume persistant pour les outputs (checkpoints, wandb)
runs_volume = modal.Volume.from_name(
    "batia-walls-runs", create_if_missing=True,
)


# --- Upload helper ---

@app.function(
    image=image,
    volumes={"/data": dataset_volume},
    timeout=600,
)
def check_dataset() -> dict:
    """Vérifie l'état du dataset uploadé."""
    import json
    p = Path("/data/walls_combined")
    if not p.exists():
        return {"present": False}
    splits = json.loads((p / "splits.json").read_text())
    return {
        "present": True,
        "n_train": len(splits.get("train", [])),
        "n_val": len(splits.get("val", [])),
        "n_test": len(splits.get("test", [])),
        "has_origins": (p / "sample_origins.json").exists(),
    }


# --- Training job ---

@app.function(
    image=image,
    gpu="A10G",          # 24 GB VRAM, ~$1.10/hr — config image 640 batch 4 testée
    volumes={
        "/data": dataset_volume,
        "/runs": runs_volume,
    },
    timeout=3600 * 8,    # 8h safety
    secrets=[modal.Secret.from_name("wandb-secret")],  # WANDB_API_KEY
)
def train_remote(
    config_yaml_text: str,
    config_filename: str = "wall_only_stage_a.yaml",
):
    """Entraîne sur GPU distant. Le config est passé en string pour
    permettre des overrides faciles (dataset_root → /data/walls_combined,
    output_dir → /runs/...)."""
    import os
    os.environ["PYTHONPATH"] = "/workspace/batia"
    os.chdir("/workspace/batia")

    # Write config to disk
    cfg_path = Path("/workspace/batia/configs/segmentation") / config_filename
    cfg_path.write_text(config_yaml_text, encoding="utf-8")

    # Reload volume so any previously committed checkpoint (auto-resume target)
    # is visible before Trainer.__init__ calls find_latest.
    runs_volume.reload()

    # Run trainer
    sys.path.insert(0, "/workspace/batia")
    from src.segmentation.config import load_config
    from src.segmentation.trainer import Trainer

    cfg = load_config(str(cfg_path))

    # Monkey-patch _save_state pour committer le volume après chaque save.
    # Sans ça, les checkpoints écrits pendant le training restent dans le FS
    # éphémère du container et sont perdus si Modal kill/timeout. Avec commit
    # après chaque save, un crash à epoch N permet de reprendre à epoch N+1.
    _orig_save_state = Trainer._save_state

    def _save_state_and_commit(self, name: str):
        _orig_save_state(self, name)
        runs_volume.commit()
        print(f"[modal] volume committed après save {name}", flush=True)

    Trainer._save_state = _save_state_and_commit

    trainer = Trainer(cfg, device="cuda")
    # NE PAS reset epoch/step : laisse Trainer.fit() auto-resume depuis le
    # latest checkpoint s'il existe sur le volume.
    trainer.fit()

    # Final commit (safety)
    runs_volume.commit()


# --- Local entry point ---

@app.local_entrypoint()
def train():
    """Point d'entrée local. Vérifie dataset, build config override,
    lance training, download checkpoints."""
    print("=== Étape 1 : Vérification dataset Modal volume ===")
    state = check_dataset.remote()
    print(f"  Dataset state: {state}")

    if not state["present"]:
        print("\n  ❌ Dataset absent. Run d'abord :")
        print("     modal volume put batia-walls-combined "
              f"{DATASET_LOCAL} /walls_combined")
        sys.exit(1)

    print(f"\n=== Étape 2 : Build config override (cloud paths) ===")
    config_text = f"""
# Wall-only Mask2Former — CLOUD training (Modal A10G).
# Mix Cubicasa + DWG, oversample DWG ×30.
run_name: wall_only_stage_a_v1_cloud
seed: 42

data:
  dataset_root: /data/walls_combined
  image_size: 640                # A10G 22 GB → 768 OOM, 640 batch 4 testé OK
  batch_size: 4
  oversample_origin:
    cc: 1.0
    dwg: 30.0

model:
  backbone: facebook/mask2former-swin-tiny-coco-panoptic

optimizer:
  lr_backbone: 1.0e-5
  lr_head: 1.0e-4
  weight_decay: 0.05
  grad_accumulation: 2
  grad_clip_norm: 1.0

scheduler:
  type: cosine
  warmup_steps: 500

training:
  epochs: 30
  early_stop_patience: 5
  mixed_precision: "no"
  oversample_rare_classes: false

logging:
  tracker: wandb
  project: batia-segmentation
  log_image_count: 5

checkpoint:
  output_dir: /runs/wall_only_stage_a_v1_cloud
  save_every_n_epochs: 1     # save+commit après chaque epoch (robust resume)
""".strip()
    print("  Config built (cloud paths).")

    print("\n=== Étape 3 : Training distant détaché (A10G image 640 batch 4) ===")
    print("  (~5h estimé, ~5 €. .spawn() = survit toute déconnexion.)")
    # .spawn() = fire-and-forget. Run continue côté Modal même si local meurt.
    # Logs visibles via `modal app logs <APP_ID>` après coup.
    function_call = train_remote.spawn(config_text)
    print(f"  FunctionCall ID : {function_call.object_id}")
    print("  Run détaché lancé. Le local peut sortir.")

    print("\n=== Suite (demain matin) ===")
    print("  modal app list                # voir le statut")
    print(f"  modal volume get batia-walls-runs "
          f"/wall_only_stage_a_v1_cloud/checkpoints/best.pt "
          f"{RUNS_LOCAL}/checkpoints/best.pt")
    print("\nFait. Voir wandb pour les courbes.")
