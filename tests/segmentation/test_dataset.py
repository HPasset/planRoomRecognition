# tests/segmentation/test_dataset.py
import json
from pathlib import Path
import cv2
import numpy as np
import pytest
import torch

from src.segmentation.dataset import PanopticDataset


@pytest.fixture
def fake_dataset(tmp_path: Path) -> Path:
    for split in ("train", "val", "test"):
        for sub in ("images", "semantic", "instance"):
            (tmp_path / sub / split).mkdir(parents=True, exist_ok=True)

    # 2 fake samples in train
    for i, sid in enumerate(["a", "b"]):
        # Textured image guarantees augmentations produce visible differences
        rng = np.random.default_rng(seed=i)
        img = rng.integers(0, 256, (400, 300, 3), dtype=np.uint8)
        sem = np.zeros((400, 300), dtype=np.uint8)
        sem[50:150, 50:150] = 2  # Kitchen
        sem[200:300, 100:200] = 5  # Bath
        inst = np.zeros((400, 300), dtype=np.uint16)
        inst[50:150, 50:150] = 1
        inst[200:300, 100:200] = 2
        cv2.imwrite(str(tmp_path / "images" / "train" / f"{sid}.png"), img)
        cv2.imwrite(str(tmp_path / "semantic" / "train" / f"{sid}.png"), sem)
        cv2.imwrite(str(tmp_path / "instance" / "train" / f"{sid}.png"), inst)

    (tmp_path / "splits.json").write_text(
        json.dumps({"train": ["a", "b"], "val": [], "test": []})
    )
    return tmp_path


def test_dataset_len(fake_dataset: Path):
    ds = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    assert len(ds) == 2


def test_dataset_returns_tensors(fake_dataset: Path):
    ds = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    sample = ds[0]
    assert isinstance(sample["pixel_values"], torch.Tensor)
    assert sample["pixel_values"].shape == (3, 256, 256)
    assert sample["semantic"].shape == (256, 256)
    assert sample["instance"].shape == (256, 256)
    assert sample["semantic"].dtype == torch.long
    # Class 2 (Kitchen) must survive
    assert (sample["semantic"] == 2).any()


def test_dataset_train_mode_applies_aug(fake_dataset: Path):
    ds_train = PanopticDataset(fake_dataset, split="train", image_size=256, train=True)
    ds_eval = PanopticDataset(fake_dataset, split="train", image_size=256, train=False)
    s_eval = ds_eval[0]["pixel_values"]
    # Sample multiple train transforms to be robust against RNG coin flips
    diffs = [not torch.equal(ds_train[0]["pixel_values"], s_eval) for _ in range(5)]
    assert any(diffs), "train mode should produce a different output at least once in 5 attempts"
