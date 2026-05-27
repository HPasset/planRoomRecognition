import torch
from torch import nn
from src.segmentation.checkpoint import save_checkpoint, load_checkpoint, find_latest


def test_save_and_load_roundtrip(tmp_path):
    model = nn.Linear(4, 2)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    state = {
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": opt.state_dict(),
        "epoch": 7,
        "best_metric": 0.42,
        "rng_state": torch.get_rng_state(),
    }
    p = tmp_path / "ckpt.pt"
    save_checkpoint(state, p)
    loaded = load_checkpoint(p, map_location="cpu")
    assert loaded["epoch"] == 7
    assert abs(loaded["best_metric"] - 0.42) < 1e-9


def test_find_latest_picks_highest_epoch(tmp_path):
    (tmp_path / "epoch_05.pt").write_text("x")
    (tmp_path / "epoch_30.pt").write_text("x")
    (tmp_path / "epoch_12.pt").write_text("x")
    (tmp_path / "best.pt").write_text("x")
    (tmp_path / "last.pt").write_text("x")
    latest = find_latest(tmp_path)
    assert latest is not None
    assert latest.name == "last.pt"


def test_find_latest_falls_back_to_epoch(tmp_path):
    (tmp_path / "epoch_05.pt").write_text("x")
    (tmp_path / "epoch_30.pt").write_text("x")
    latest = find_latest(tmp_path)
    assert latest.name == "epoch_30.pt"


def test_find_latest_returns_none_if_empty(tmp_path):
    assert find_latest(tmp_path) is None
