# tests/segmentation/test_config.py
from pathlib import Path
import pytest
from src.segmentation.config import TrainingConfig, load_config


def _write_yaml(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


VALID_YAML = """
run_name: stage_a_test
seed: 42

data:
  dataset_root: data/processed/cubicasa_panoptic
  image_size: 768
  batch_size: 4

model:
  backbone: facebook/mask2former-swin-small-coco-panoptic

optimizer:
  lr_backbone: 1.0e-5
  lr_head: 1.0e-4
  weight_decay: 0.05
  grad_accumulation: 4
  grad_clip_norm: 0.01

scheduler:
  warmup_steps: 1000

training:
  epochs: 80
  early_stop_patience: 10
  mixed_precision: bf16

logging:
  tracker: wandb
  project: batia-segmentation

checkpoint:
  output_dir: runs/segmentation/stage_a_test
"""


def test_load_valid_config(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML)
    cfg = load_config(p)
    assert isinstance(cfg, TrainingConfig)
    assert cfg.run_name == "stage_a_test"
    assert cfg.training.epochs == 80
    assert cfg.optimizer.lr_backbone == 1e-5


def test_invalid_image_size_rejected(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML.replace("image_size: 768", "image_size: 100"))
    with pytest.raises(ValueError):
        load_config(p)


def test_invalid_mixed_precision_rejected(tmp_path: Path):
    p = tmp_path / "config.yaml"
    _write_yaml(p, VALID_YAML.replace("mixed_precision: bf16", "mixed_precision: fp64"))
    with pytest.raises(ValueError):
        load_config(p)


def test_early_stop_patience_exceeds_epochs_rejected(tmp_path: Path):
    p = tmp_path / "config.yaml"
    bad = VALID_YAML.replace("epochs: 80", "epochs: 5")
    # early_stop_patience: 10 in VALID_YAML, now > epochs: 5
    _write_yaml(p, bad)
    with pytest.raises(ValueError, match="early_stop_patience"):
        load_config(p)
