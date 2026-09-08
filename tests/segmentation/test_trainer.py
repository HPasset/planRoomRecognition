import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import torch

from src.segmentation.config import (
    TrainingConfig, DataConfig, ModelConfig, OptimizerConfig,
    SchedulerConfig, TrainingPhaseConfig, LoggingConfig, CheckpointConfig,
)
from src.segmentation.trainer import Trainer


def _make_tiny_dataset(root: Path, n: int = 4):
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (root / sub / split).mkdir(parents=True, exist_ok=True)
    ids = [f"x{i}" for i in range(n)]
    for sid in ids:
        img = np.full((400, 300, 3), 200, dtype=np.uint8)
        sem = np.zeros((400, 300), dtype=np.uint8)
        sem[100:200, 100:200] = 2  # Kitchen
        inst = np.zeros((400, 300), dtype=np.uint16)
        inst[100:200, 100:200] = 1
        cv2.imwrite(str(root / "images" / "train" / f"{sid}.png"), img)
        cv2.imwrite(str(root / "semantic" / "train" / f"{sid}.png"), sem)
        cv2.imwrite(str(root / "instance" / "train" / f"{sid}.png"), inst)
        cv2.imwrite(str(root / "images" / "val" / f"{sid}.png"), img)
        cv2.imwrite(str(root / "semantic" / "val" / f"{sid}.png"), sem)
        cv2.imwrite(str(root / "instance" / "val" / f"{sid}.png"), inst)
    (root / "splits.json").write_text(
        json.dumps({"train": ids, "val": ids[:2], "test": []})
    )


def _make_config(root: Path, ckpt_dir: Path) -> TrainingConfig:
    return TrainingConfig(
        run_name="smoke",
        seed=0,
        data=DataConfig(dataset_root=str(root), image_size=384, batch_size=1),
        model=ModelConfig(backbone="facebook/mask2former-swin-tiny-coco-panoptic"),
        optimizer=OptimizerConfig(
            lr_backbone=1e-5, lr_head=1e-4, weight_decay=0.05,
            grad_accumulation=1, grad_clip_norm=0.01,
        ),
        scheduler=SchedulerConfig(warmup_steps=0),
        training=TrainingPhaseConfig(
            epochs=1, early_stop_patience=0,
            mixed_precision="no",
        ),
        logging=LoggingConfig(tracker="none", project="test"),
        checkpoint=CheckpointConfig(output_dir=str(ckpt_dir)),
    )


@pytest.mark.slow
def test_one_epoch_smoke(tmp_path):
    data = tmp_path / "data"
    ckpt = tmp_path / "ckpt"
    _make_tiny_dataset(data)
    cfg = _make_config(data, ckpt)
    trainer = Trainer(cfg, device="cpu")  # CPU pour CI
    trainer.fit()
    assert (ckpt / "checkpoints" / "last.pt").exists()
