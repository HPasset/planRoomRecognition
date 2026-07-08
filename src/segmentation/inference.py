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

        # Walls (binary mask of class id 1, in letterboxed space).
        # Use SEMANTIC segmentation (per-pixel argmax) rather than panoptic
        # because Wall queries often have confidence < panoptic threshold (0.5)
        # on FR plans where Wall mIoU is only ~0.25 — panoptic would filter
        # them all out, leaving an empty mask.
        sem_pred_lb = self.processor.post_process_semantic_segmentation(
            out, target_sizes=[(self.image_size, self.image_size)],
        )[0].cpu().numpy()
        walls_mask_lb = (sem_pred_lb == CLASS_ID["Wall"]).astype(np.uint8)
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


class DualSegmentationInference:
    """Deux modèles dédiés : pièces (FR-only Swin-S) + murs (DWG-only Swin-T).

    Le modèle pièces `fr_only_v1` bat l'ancien combiné CubiCasa+FR (test mIoU
    0,66 vs 0,59) ET est 100 % license-clean, mais il n'est pas optimisé pour
    les murs. On dérive donc les murs d'un modèle dédié `wall_only_dwg_v3`
    (Wall IoU FR ~0,68). Contrat de sortie identique à `SegmentationInference` :
    `.predict(path) -> SegmentationOutput` — l'app en aval ne voit aucune
    différence (mêmes `.rooms`, même `.walls.mask_path`).

    Dégradation gracieuse : si le checkpoint mur est absent, on retombe sur les
    murs (médiocres) du modèle pièces et on l'annonce dans `warnings`.
    """

    def __init__(
        self,
        room_checkpoint: str | Path,
        wall_checkpoint: str | Path | None = None,
        room_backbone: str = "facebook/mask2former-swin-small-coco-panoptic",
        wall_backbone: str = "facebook/mask2former-swin-tiny-coco-panoptic",
        room_image_size: int = 768,
        wall_image_size: int = 640,
        device: str = "auto",
        walls_out_dir: str | Path = "runs/segmentation/inference_walls",
        model_version: str = "batia-dual-fr_only+walls_dwg-v0.1",
    ):
        self.model_version = model_version
        walls_out_dir = Path(walls_out_dir)

        # Modèle pièces : ses murs sont ignorés → scratch dir séparé pour ne
        # pas écraser le masque mur (le bon) produit par le modèle dédié.
        self.room_model = SegmentationInference(
            checkpoint_path=room_checkpoint,
            backbone=room_backbone,
            image_size=room_image_size,
            device=device,
            walls_out_dir=walls_out_dir / "_room_scratch",
            model_version=model_version,
        )

        self.wall_model: SegmentationInference | None = None
        if wall_checkpoint is not None and Path(wall_checkpoint).exists():
            self.wall_model = SegmentationInference(
                checkpoint_path=wall_checkpoint,
                backbone=wall_backbone,
                image_size=wall_image_size,
                device=device,
                walls_out_dir=walls_out_dir,
                model_version=model_version,
            )

    @property
    def image_size(self) -> int:
        return self.room_model.image_size

    def predict(self, image_path: str | Path) -> SegmentationOutput:
        t0 = time.time()
        room_out = self.room_model.predict(image_path)

        warnings = list(room_out.warnings)
        if self.wall_model is not None:
            wall_out = self.wall_model.predict(image_path)
            walls = wall_out.walls
            warnings += wall_out.warnings
        else:
            walls = room_out.walls
            warnings.append(
                "Checkpoint mur dédié absent : murs dérivés du modèle pièces "
                "(qualité dégradée)."
            )

        elapsed_ms = int((time.time() - t0) * 1000)
        return SegmentationOutput(
            plan_id=room_out.plan_id,
            image_size=room_out.image_size,
            model_version=self.model_version,
            inference_time_ms=elapsed_ms,
            rooms=room_out.rooms,
            walls=walls,
            warnings=warnings,
        )
