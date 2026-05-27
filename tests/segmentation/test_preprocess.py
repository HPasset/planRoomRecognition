import numpy as np
from src.segmentation.preprocess import letterbox, unletterbox_polygon


def test_letterbox_preserves_aspect():
    img = np.full((600, 800, 3), 200, dtype=np.uint8)
    out, info = letterbox(img, target_size=768)
    assert out.shape == (768, 768, 3)
    assert info.scale == 768 / 800  # max dim
    # Padding asymmetric
    assert info.pad_top + info.pad_bottom > 0


def test_unletterbox_polygon_inverse():
    img = np.full((600, 800, 3), 200, dtype=np.uint8)
    _, info = letterbox(img, target_size=768)
    # Polygon in letterboxed space
    poly_lb = [[100, 100], [700, 100], [700, 700], [100, 700]]
    poly_orig = unletterbox_polygon(poly_lb, info)
    # Should be within original image bounds
    for x, y in poly_orig:
        assert 0 <= x <= 800
        assert 0 <= y <= 600
