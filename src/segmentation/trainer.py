"""Training loop: 2 stages of Mask2Former with checkpointing + tracker."""
from __future__ import annotations
from contextlib import nullcontext
from pathlib import Path
import math
import random

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader

from src.segmentation.checkpoint import save_checkpoint, load_checkpoint, find_latest
from src.segmentation.classes import NUM_CLASSES, ROOM_CLASS_IDS
from src.segmentation.config import TrainingConfig
from src.segmentation.dataset import PanopticDataset
from src.segmentation.metrics import compute_iou_per_class, compute_miou
from src.segmentation.model import build_model, get_processor
from src.segmentation.tracker import build_tracker


def _build_targets_for_mask2former(semantic: torch.Tensor, instance: torch.Tensor):
    """Convert (semantic, instance) per-pixel masks to Mask2Former target format.

    Mask2Former expects, per image:
      - mask_labels: list of binary masks (one per instance + one per stuff class present)
      - class_labels: corresponding class id (long)

    We treat ROOM classes as 'things' (per-instance) and Wall as 'stuff' (single mask).
    """
    out_mask_labels: list[torch.Tensor] = []
    out_class_labels: list[int] = []
    H, W = semantic.shape

    # Things: rooms (one mask per instance)
    for inst_id in instance.unique().tolist():
        if inst_id == 0:
            continue
        m = (instance == inst_id)
        if m.sum() == 0:
            continue
        cls = int(semantic[m].mode().values.item())
        if cls in ROOM_CLASS_IDS:
            out_mask_labels.append(m.float())
            out_class_labels.append(cls)

    # Stuff: walls (single mask if any pixels)
    wall_mask = (semantic == 1)
    if wall_mask.sum() > 0:
        out_mask_labels.append(wall_mask.float())
        out_class_labels.append(1)

    if not out_mask_labels:
        # Empty image (very rare): single dummy background to avoid NaN
        out_mask_labels.append(torch.zeros((H, W)))
        out_class_labels.append(0)

    return (
        torch.stack(out_mask_labels),
        torch.tensor(out_class_labels, dtype=torch.long),
    )


class Trainer:
    def __init__(self, cfg: TrainingConfig, device: str = "auto"):
        self.cfg = cfg
        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.device = torch.device(device)
        self._set_seed(cfg.seed)

        self.model = build_model(
            backbone=cfg.model.backbone, num_classes=NUM_CLASSES,
        ).to(self.device)
        self.processor = get_processor(cfg.model.backbone)

        self.train_ds = PanopticDataset(cfg.data.dataset_root, "train",
                                        cfg.data.image_size, train=True)
        self.val_ds = PanopticDataset(cfg.data.dataset_root, "val",
                                      cfg.data.image_size, train=False)
        self.train_loader = DataLoader(
            self.train_ds, batch_size=cfg.data.batch_size,
            shuffle=True, num_workers=0, drop_last=True,
            collate_fn=self._collate,
        )
        self.val_loader = DataLoader(
            self.val_ds, batch_size=1, shuffle=False, num_workers=0,
            collate_fn=self._collate,
        )

        # Param groups: backbone (lower LR) vs the rest (head LR)
        backbone_params, other_params = [], []
        for name, p in self.model.named_parameters():
            if "backbone" in name or "pixel_level_module.encoder" in name:
                backbone_params.append(p)
            else:
                other_params.append(p)
        self.optimizer = AdamW([
            {"params": backbone_params, "lr": cfg.optimizer.lr_backbone},
            {"params": other_params, "lr": cfg.optimizer.lr_head},
        ], weight_decay=cfg.optimizer.weight_decay)

        self.scheduler = self._build_scheduler()
        self.global_step = 0
        self.epoch = 0
        self.best_metric = -math.inf

        self.use_amp = cfg.training.mixed_precision in ("bf16", "fp16")
        self.amp_dtype = (
            torch.bfloat16 if cfg.training.mixed_precision == "bf16"
            else torch.float16 if cfg.training.mixed_precision == "fp16"
            else torch.float32
        )

        self.ckpt_dir = Path(cfg.checkpoint.output_dir) / "checkpoints"
        self.ckpt_dir.mkdir(parents=True, exist_ok=True)

        self.tracker = build_tracker(
            cfg.logging.tracker,
            run_name=cfg.run_name,
            project=cfg.logging.project,
            config=cfg.model_dump(),
        )

        # Guard against latent footguns
        if cfg.training.mixed_precision == "fp16" and self.device.type == "cuda":
            raise NotImplementedError(
                "fp16 on CUDA requires GradScaler which is not implemented; "
                "use bf16 instead, or extend the trainer."
            )
        if cfg.scheduler.type not in ("constant", "cosine"):
            raise NotImplementedError(
                f"Scheduler '{cfg.scheduler.type}' not implemented; supported: constant, cosine."
            )

    @staticmethod
    def _set_seed(seed: int):
        random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)

    def _build_scheduler(self):
        steps_per_epoch = max(1, len(self.train_ds) // self.cfg.data.batch_size)
        total = self.cfg.training.epochs * steps_per_epoch
        warmup = self.cfg.scheduler.warmup_steps

        def lr_lambda(step: int) -> float:
            if step < warmup:
                return step / max(1, warmup)
            if self.cfg.scheduler.type == "constant":
                return 1.0
            progress = (step - warmup) / max(1, total - warmup)
            return 0.5 * (1.0 + math.cos(math.pi * progress))

        return torch.optim.lr_scheduler.LambdaLR(self.optimizer, lr_lambda)

    @staticmethod
    def _collate(batch: list[dict]) -> dict:
        return {
            "ids": [b["id"] for b in batch],
            "pixel_values": torch.stack([b["pixel_values"] for b in batch]),
            "semantic": torch.stack([b["semantic"] for b in batch]),
            "instance": torch.stack([b["instance"] for b in batch]),
        }

    def _build_batch_targets(self, batch):
        mask_labels, class_labels = [], []
        for sem, inst in zip(batch["semantic"], batch["instance"]):
            ml, cl = _build_targets_for_mask2former(sem, inst)
            mask_labels.append(ml.to(self.device))
            class_labels.append(cl.to(self.device))
        return mask_labels, class_labels

    def fit(self):
        # Auto-resume
        latest = find_latest(self.ckpt_dir)
        if latest is not None:
            self._load_state(latest)
            print(f"Resumed from {latest} at epoch {self.epoch}")

        no_improve_epochs = 0
        for epoch in range(self.epoch, self.cfg.training.epochs):
            self.epoch = epoch
            self._train_one_epoch()
            metric = self._validate()
            self._save_state(name=f"epoch_{epoch:02d}.pt")
            self._save_state(name="last.pt")
            if metric > self.best_metric:
                self.best_metric = metric
                self._save_state(name="best.pt")
                no_improve_epochs = 0
            else:
                no_improve_epochs += 1
                if no_improve_epochs >= self.cfg.training.early_stop_patience:
                    print(f"Early stopping at epoch {epoch}")
                    break
        self.tracker.finish()

    def _train_one_epoch(self):
        self.model.train()
        accum = self.cfg.optimizer.grad_accumulation
        self.optimizer.zero_grad()
        running_loss = 0.0

        for step, batch in enumerate(self.train_loader):
            mask_labels, class_labels = self._build_batch_targets(batch)
            pixel_values = batch["pixel_values"].to(self.device)

            ctx = (
                torch.autocast(device_type=self.device.type, dtype=self.amp_dtype)
                if self.use_amp else nullcontext()
            )
            with ctx:
                out = self.model(
                    pixel_values=pixel_values,
                    mask_labels=mask_labels,
                    class_labels=class_labels,
                )
                loss = out.loss / accum

            loss.backward()
            running_loss += float(loss.item())  # already the per-micro-batch /accum slice

            if (step + 1) % accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    self.model.parameters(), self.cfg.optimizer.grad_clip_norm,
                )
                self.optimizer.step()
                self.scheduler.step()
                self.optimizer.zero_grad()
                self.global_step += 1

                self.tracker.log_metrics(
                    {"train/loss": running_loss,  # average across the accum window
                     "train/lr_backbone": self.optimizer.param_groups[0]["lr"],
                     "train/lr_head": self.optimizer.param_groups[1]["lr"]},
                    step=self.global_step,
                )
                running_loss = 0.0

    @torch.no_grad()
    def _validate(self) -> float:
        self.model.eval()
        ious = []
        for batch in self.val_loader:
            pixel_values = batch["pixel_values"].to(self.device)
            out = self.model(pixel_values=pixel_values)
            sem_pred = self.processor.post_process_semantic_segmentation(
                out, target_sizes=[batch["semantic"].shape[-2:]],
            )[0].cpu().numpy()
            sem_gt = batch["semantic"][0].numpy()
            ious.append(compute_iou_per_class(sem_pred, sem_gt, NUM_CLASSES))

        ious = np.stack(ious)
        per_class = np.nanmean(ious, axis=0)
        miou = compute_miou(per_class)

        log = {"val/mIoU": miou}
        for cid, v in enumerate(per_class):
            if not np.isnan(v):
                log[f"val/IoU_class_{cid}"] = float(v)
        self.tracker.log_metrics(log, step=self.global_step)
        return miou

    def _save_state(self, name: str):
        state = {
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict(),
            "epoch": self.epoch + 1,
            "global_step": self.global_step,
            "best_metric": self.best_metric,
            "config": self.cfg.model_dump(),
        }
        save_checkpoint(state, self.ckpt_dir / name)

    def _load_state(self, path: Path):
        ckpt = load_checkpoint(path, map_location=str(self.device))
        self.model.load_state_dict(ckpt["model_state_dict"])
        self.optimizer.load_state_dict(ckpt["optimizer_state_dict"])
        self.scheduler.load_state_dict(ckpt["scheduler_state_dict"])
        self.epoch = ckpt["epoch"]
        self.global_step = ckpt["global_step"]
        self.best_metric = ckpt["best_metric"]
