# tests/segmentation/test_augmentations.py
import numpy as np
from src.segmentation.augmentations import build_train_transform, build_eval_transform


def test_train_transform_preserves_shapes():
    aug = build_train_transform(image_size=768)
    img = np.random.randint(0, 256, (1000, 800, 3), dtype=np.uint8)
    sem = np.random.randint(0, 10, (1000, 800), dtype=np.uint8)
    inst = np.random.randint(0, 50, (1000, 800), dtype=np.int32).astype(np.int32)

    out = aug(image=img, mask=sem, instance_mask=inst.astype(np.uint16))
    assert out["image"].shape == (768, 768, 3)
    assert out["mask"].shape == (768, 768)
    assert out["instance_mask"].shape == (768, 768)


def test_eval_transform_letterbox_no_change_to_classes():
    aug = build_eval_transform(image_size=768)
    img = np.full((600, 800, 3), 128, dtype=np.uint8)
    sem = np.zeros((600, 800), dtype=np.uint8)
    sem[100:200, 100:200] = 5  # Bath patch
    out = aug(image=img, mask=sem)
    assert out["image"].shape == (768, 768, 3)
    assert out["mask"].shape == (768, 768)
    # Class 5 must still be present (letterbox preserves content)
    assert 5 in np.unique(out["mask"])


def test_no_mosaic_or_mixup():
    """Sanity: train transform should not contain mosaic/mixup."""
    aug = build_train_transform(image_size=512)
    txt = repr(aug).lower()
    assert "mosaic" not in txt
    assert "mixup" not in txt
    assert "elastic" not in txt
