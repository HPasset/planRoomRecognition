"""Checkpoint save/load with auto-resume support."""
from pathlib import Path
import re
import torch


def save_checkpoint(state: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(state, tmp)
    tmp.replace(path)  # atomic on POSIX


def load_checkpoint(path: str | Path, map_location: str = "cpu") -> dict:
    return torch.load(path, map_location=map_location, weights_only=False)


_EPOCH_RE = re.compile(r"epoch_(\d+)\.pt$")


def find_latest(checkpoint_dir: str | Path) -> Path | None:
    """Return the most relevant checkpoint to resume from.

    Priority:
        1. last.pt
        2. highest-numbered epoch_XX.pt
        3. None
    """
    d = Path(checkpoint_dir)
    if not d.exists():
        return None
    last = d / "last.pt"
    if last.exists():
        return last
    epoch_files = []
    for p in d.iterdir():
        m = _EPOCH_RE.search(p.name)
        if m:
            epoch_files.append((int(m.group(1)), p))
    if not epoch_files:
        return None
    epoch_files.sort()
    return epoch_files[-1][1]
