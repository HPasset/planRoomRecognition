import numpy as np
from src.segmentation.preprocess import letterbox


def test_letterbox_preserves_aspect():
    img = np.full((600, 800, 3), 200, dtype=np.uint8)
    out, info = letterbox(img, target_size=768)
    assert out.shape == (768, 768, 3)
    assert info.scale == 768 / 800  # max dim
    # Padding asymmetric
    assert info.pad_top + info.pad_bottom > 0
