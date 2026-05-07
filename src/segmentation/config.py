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


class ModelConfig(BaseModel):
    backbone: str = "facebook/mask2former-swin-small-coco-panoptic"


class OptimizerConfig(BaseModel):
    lr_backbone: float = Field(gt=0, le=1e-2)
    lr_head: float = Field(gt=0, le=1e-2)
    weight_decay: float = Field(ge=0, le=1.0)
    grad_accumulation: int = Field(ge=1, le=64)
    grad_clip_norm: float = Field(gt=0, le=10.0)


class SchedulerConfig(BaseModel):
    type: Literal["cosine", "polynomial", "constant"] = "cosine"
    warmup_steps: int = Field(ge=0, le=10000)


class TrainingPhaseConfig(BaseModel):
    epochs: int = Field(ge=1, le=500)
    early_stop_patience: int = Field(ge=0, le=50)
    mixed_precision: Literal["bf16", "fp16", "no"] = "bf16"
    oversample_rare_classes: bool = True


class LoggingConfig(BaseModel):
    tracker: Literal["wandb", "tensorboard", "none"] = "wandb"
    project: str = "batia-segmentation"
    log_image_count: int = Field(ge=0, le=50)


class CheckpointConfig(BaseModel):
    output_dir: str
    save_every_n_epochs: int = Field(ge=1, le=100)


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
        if self.checkpoint.save_every_n_epochs > self.training.epochs:
            raise ValueError(
                f"save_every_n_epochs ({self.checkpoint.save_every_n_epochs}) "
                f"must be <= epochs ({self.training.epochs})"
            )
        return self


def load_config(path: str | Path) -> TrainingConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return TrainingConfig.model_validate(raw)
