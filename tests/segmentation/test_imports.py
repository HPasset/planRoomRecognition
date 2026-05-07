def test_imports_basic():
    import torch
    import transformers
    import albumentations
    import wandb
    import pycocotools
    import shapely
    import cv2
    assert torch.backends.mps.is_available(), "MPS backend required"
