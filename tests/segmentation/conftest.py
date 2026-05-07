"""Shared fixtures for segmentation tests."""
from pathlib import Path
import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_run_dir(tmp_path: Path) -> Path:
    """Disposable run directory mimicking runs/segmentation/<run_name>/."""
    p = tmp_path / "run_test"
    (p / "checkpoints").mkdir(parents=True)
    return p
