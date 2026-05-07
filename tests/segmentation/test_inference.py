import os
from pathlib import Path
import pytest
from src.segmentation.inference import SegmentationInference
from src.segmentation.schema import SegmentationOutput


@pytest.mark.skipif(
    not os.environ.get("BATIA_TEST_CHECKPOINT"),
    reason="Set BATIA_TEST_CHECKPOINT=path/to/checkpoint.pt to run",
)
def test_inference_returns_valid_schema(fixtures_dir: Path, tmp_path: Path):
    inf = SegmentationInference(
        checkpoint_path=os.environ["BATIA_TEST_CHECKPOINT"],
        backbone="facebook/mask2former-swin-small-coco-panoptic",
        image_size=768,
        device="cpu",
        walls_out_dir=tmp_path,
    )
    out: SegmentationOutput = inf.predict(fixtures_dir / "sample_plan.png")
    assert isinstance(out, SegmentationOutput)
    assert out.image_size == [800, 600]
    assert isinstance(out.rooms, list)
