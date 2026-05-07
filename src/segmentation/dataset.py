# src/segmentation/dataset.py
"""PyTorch Dataset for panoptic segmentation training."""
import json
from pathlib import Path
from typing import Optional
import cv2
import numpy as np
import torch
from torch.utils.data import Dataset

from src.segmentation.augmentations import build_train_transform, build_eval_transform


class PanopticDataset(Dataset):
    """Loads (image, semantic_mask, instance_mask) triples and applies transforms.

    Expected layout under root:
        images/{split}/<id>.png
        semantic/{split}/<id>.png  (uint8, class ids)
        instance/{split}/<id>.png  (uint16, instance ids; 0 = no instance / stuff)
        splits.json
    """

    def __init__(
        self,
        root: str | Path,
        split: str,
        image_size: int,
        train: bool,
    ):
        self.root = Path(root)
        self.split = split
        self.image_size = image_size
        with open(self.root / "splits.json") as f:
            splits = json.load(f)
        self.ids: list[str] = splits[split]

        self.transform = (
            build_train_transform(image_size) if train
            else build_eval_transform(image_size)
        )

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> dict:
        sid = self.ids[idx]
        img = cv2.imread(str(self.root / "images" / self.split / f"{sid}.png"))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        sem = cv2.imread(
            str(self.root / "semantic" / self.split / f"{sid}.png"),
            cv2.IMREAD_UNCHANGED,
        )
        inst = cv2.imread(
            str(self.root / "instance" / self.split / f"{sid}.png"),
            cv2.IMREAD_UNCHANGED,
        )

        out = self.transform(image=img, mask=sem, instance_mask=inst)
        # image: HWC float -> CHW float tensor
        pixel_values = torch.from_numpy(out["image"]).permute(2, 0, 1).float()
        semantic = torch.from_numpy(out["mask"]).long()
        instance = torch.from_numpy(out["instance_mask"]).long()

        return {
            "id": sid,
            "pixel_values": pixel_values,
            "semantic": semantic,
            "instance": instance,
        }
