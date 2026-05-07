"""Mask2Former model wrapper for batIA 10-class panoptic segmentation."""
from transformers import Mask2FormerForUniversalSegmentation, Mask2FormerConfig

from src.segmentation.classes import CLASS_NAMES, NUM_CLASSES


def build_model(
    backbone: str = "facebook/mask2former-swin-small-coco-panoptic",
    num_classes: int = NUM_CLASSES,
) -> Mask2FormerForUniversalSegmentation:
    """Load Mask2Former pretrained on COCO-panoptic, replace head for our classes.

    HuggingFace `from_pretrained` with mismatched-size handling lets us swap the
    classification head while keeping all backbone + pixel decoder + transformer
    decoder weights.
    """
    id2label = {i: name for i, name in enumerate(CLASS_NAMES[:num_classes])}
    label2id = {name: i for i, name in id2label.items()}

    model = Mask2FormerForUniversalSegmentation.from_pretrained(
        backbone,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
        ignore_mismatched_sizes=True,
    )
    return model


def get_processor(backbone: str = "facebook/mask2former-swin-small-coco-panoptic"):
    """Return the matching image processor (used for inference postprocess)."""
    from transformers import Mask2FormerImageProcessor
    return Mask2FormerImageProcessor.from_pretrained(backbone)
