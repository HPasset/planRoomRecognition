# tests/segmentation/test_tracker.py
from src.segmentation.tracker import build_tracker


def test_noop_tracker():
    tr = build_tracker("none", run_name="x", project="p", config={})
    tr.log_metrics({"loss": 1.0}, step=0)
    tr.finish()


def test_wandb_tracker_offline(tmp_path, monkeypatch):
    """Run W&B in offline mode to avoid cloud calls in tests."""
    monkeypatch.setenv("WANDB_MODE", "offline")
    monkeypatch.setenv("WANDB_DIR", str(tmp_path))
    tr = build_tracker("wandb", run_name="test", project="batia-test",
                      config={"lr": 1e-4})
    tr.log_metrics({"loss": 0.5, "miou": 0.6}, step=1)
    tr.finish()
    # Offline run dir should exist
    assert any(tmp_path.glob("offline-run-*")) or any(tmp_path.glob("wandb"))
