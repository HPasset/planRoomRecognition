"""End-to-end inference: image path -> SegmentationOutput JSON."""
from __future__ import annotations
import time
from pathlib import Path

import cv2
import numpy as np
import torch

from src.segmentation.checkpoint import load_checkpoint
from src.segmentation.classes import CLASS_ID, NUM_CLASSES
from src.segmentation.model import build_model, get_processor
from src.segmentation.preprocess import letterbox
from src.segmentation.postprocess import panoptic_to_rooms, walls_mask_to_output
from src.segmentation.schema import SegmentationOutput, RoomDetection, WallsOutput


_DEFAULT_NORM_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_DEFAULT_NORM_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class SegmentationInference:
    def __init__(
        self,
        checkpoint_path: str | Path,
        backbone: str = "facebook/mask2former-swin-small-coco-panoptic",
        image_size: int = 768,
        device: str = "auto",
        walls_out_dir: str | Path = "runs/segmentation/inference_walls",
        model_version: str = "mask2former-swin-s-batia-v0.1",
    ):
        self.image_size = image_size
        self.walls_out_dir = Path(walls_out_dir)
        self.walls_out_dir.mkdir(parents=True, exist_ok=True)
        self.model_version = model_version

        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = torch.device(device)

        self.model = build_model(backbone=backbone, num_classes=NUM_CLASSES)
        ckpt = load_checkpoint(checkpoint_path, map_location=str(self.device))
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.model.to(self.device).eval()
        self.processor = get_processor(backbone)

    @torch.no_grad()
    def predict(self, image_path: str | Path) -> SegmentationOutput:
        t0 = time.time()
        image_path = Path(image_path)
        bgr = cv2.imread(str(image_path))
        if bgr is None:
            raise ValueError(f"Cannot read image: {image_path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        # Preprocess
        padded, info = letterbox(rgb, target_size=self.image_size)
        normalized = padded.astype(np.float32) / 255.0
        normalized = (normalized - _DEFAULT_NORM_MEAN) / _DEFAULT_NORM_STD
        tensor = torch.from_numpy(normalized).permute(2, 0, 1).unsqueeze(0).float()
        tensor = tensor.to(self.device)

        # Forward
        out = self.model(pixel_values=tensor)

        # Mask2Former panoptic post-processing
        result = self.processor.post_process_panoptic_segmentation(
            out, target_sizes=[(self.image_size, self.image_size)],
            threshold=0.5,
        )[0]
        panoptic_seg = result["segmentation"].cpu().numpy()  # (H, W) int
        segments_info = result["segments_info"]

        # Rooms
        rooms_dicts = panoptic_to_rooms(
            panoptic_seg, segments_info, info, plan_size=(w, h),
        )
        rooms = [RoomDetection(**r) for r in rooms_dicts]

        # Walls (binary mask of class id 1, in letterboxed space)
        walls_mask_lb = np.zeros_like(panoptic_seg, dtype=np.uint8)
        for seg in segments_info:
            if seg.get("label_id") == CLASS_ID["Wall"]:
                walls_mask_lb |= (panoptic_seg == seg["id"]).astype(np.uint8)
        walls = walls_mask_to_output(
            walls_mask_lb, info, plan_id=image_path.name, out_dir=self.walls_out_dir,
        )

        elapsed_ms = int((time.time() - t0) * 1000)
        return SegmentationOutput(
            plan_id=image_path.name,
            image_size=[w, h],
            model_version=self.model_version,
            inference_time_ms=elapsed_ms,
            rooms=rooms,
            walls=walls,
            warnings=[],
        )
