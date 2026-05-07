# src/segmentation/tracker.py
"""Pluggable training tracker. Wraps W&B with a no-op fallback."""
from typing import Protocol
import numpy as np


class Tracker(Protocol):
    def log_metrics(self, metrics: dict, step: int) -> None: ...
    def log_image(self, key: str, image: np.ndarray, step: int) -> None: ...
    def finish(self) -> None: ...


class _NoOpTracker:
    def log_metrics(self, metrics, step): pass
    def log_image(self, key, image, step): pass
    def finish(self): pass


class _WandbTracker:
    def __init__(self, run_name: str, project: str, config: dict):
        import wandb
        self._wandb = wandb
        self._run = wandb.init(project=project, name=run_name, config=config,
                               reinit=True)

    def log_metrics(self, metrics: dict, step: int) -> None:
        self._wandb.log(metrics, step=step)

    def log_image(self, key: str, image: np.ndarray, step: int) -> None:
        img = self._wandb.Image(image)
        self._wandb.log({key: img}, step=step)

    def finish(self) -> None:
        self._wandb.finish()


def build_tracker(kind: str, run_name: str, project: str, config: dict) -> Tracker:
    if kind == "wandb":
        return _WandbTracker(run_name=run_name, project=project, config=config)
    if kind in ("none", "tensorboard"):
        # tensorboard placeholder; project does not require it for MVP.
        return _NoOpTracker()
    raise ValueError(f"Unknown tracker: {kind}")
