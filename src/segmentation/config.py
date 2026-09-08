# src/segmentation/config.py
"""Typed YAML config for training runs."""
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, model_validator


class DataConfig(BaseModel):
    dataset_root: str
    image_size: int = Field(ge=256, le=1536)
    batch_size: int = Field(ge=1, le=64)
    # DataLoader worker processes. 0 (défaut) = chargement synchrone (sûr sur
    # Mac/MPS) ; >0 recommandé sur GPU cloud pour ne pas affamer le GPU.
    num_workers: int = Field(default=0, ge=0, le=32)
    # If set, train loader uses WeightedRandomSampler. Keys must match values in
    # <dataset_root>/sample_origins.json (e.g. {"fr": 8.0, "cc": 1.0}).
    oversample_origin: dict[str, float] | None = None


class ModelConfig(BaseModel):
    backbone: str = "facebook/mask2former-swin-small-coco-panoptic"


class OptimizerConfig(BaseModel):
    lr_backbone: float = Field(gt=0, le=1e-2)
    lr_head: float = Field(gt=0, le=1e-2)
    weight_decay: float = Field(ge=0, le=1.0)
    grad_accumulation: int = Field(ge=1, le=64)
    grad_clip_norm: float = Field(gt=0, le=10.0)


class SchedulerConfig(BaseModel):
    warmup_steps: int = Field(ge=0, le=10000)


class TrainingPhaseConfig(BaseModel):
    epochs: int = Field(ge=1, le=500)
    early_stop_patience: int = Field(ge=0, le=50)
    mixed_precision: Literal["bf16", "no"] = "bf16"
    # Path to a Stage A checkpoint. Loaded ONLY when no local resume checkpoint
    # exists in <output_dir>/checkpoints — pure weights init, optimizer/scheduler
    # start fresh.
    init_from_checkpoint: str | None = None


class LoggingConfig(BaseModel):
    tracker: Literal["wandb", "none"] = "wandb"
    project: str = "batia-segmentation"


class CheckpointConfig(BaseModel):
    output_dir: str


class TrainingConfig(BaseModel):
    run_name: str
    seed: int = 42
    data: DataConfig
    model: ModelConfig
    optimizer: OptimizerConfig
    scheduler: SchedulerConfig
    training: TrainingPhaseConfig
    logging: LoggingConfig
    checkpoint: CheckpointConfig

    @model_validator(mode="after")
    def _validate_cross_field_constraints(self):
        if self.training.early_stop_patience > self.training.epochs:
            raise ValueError(
                f"early_stop_patience ({self.training.early_stop_patience}) "
                f"must be <= epochs ({self.training.epochs})"
            )
        return self


def load_config(path: str | Path) -> TrainingConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return TrainingConfig.model_validate(raw)
