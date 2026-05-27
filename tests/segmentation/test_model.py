import torch
import pytest
from src.segmentation.model import build_model
from src.segmentation.classes import NUM_CLASSES


@pytest.fixture(scope="module")
def model():
    return build_model(
        backbone="facebook/mask2former-swin-tiny-coco-panoptic",  # tiny for tests
        num_classes=NUM_CLASSES,
    )


def test_model_loads(model):
    assert model is not None


def test_model_forward_shape(model):
    model.eval()
    img = torch.randn(1, 3, 384, 384)  # tiny input for fast test
    with torch.no_grad():
        out = model(pixel_values=img)
    # Outputs: class_queries_logits + masks_queries_logits
    assert hasattr(out, "class_queries_logits")
    assert hasattr(out, "masks_queries_logits")
    n_queries = out.class_queries_logits.shape[1]
    # +1 for "no object" class
    assert out.class_queries_logits.shape == (1, n_queries, NUM_CLASSES + 1)
