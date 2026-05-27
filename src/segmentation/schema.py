"""Pydantic schemas — contract between segmentation (B) and downstream (A/OCR/NFC)."""
from typing import Annotated
from pydantic import BaseModel, Field, model_validator

from src.segmentation.classes import CLASS_NAMES, CLASS_ID


Polygon = Annotated[list[list[int]], Field(min_length=3)]
"""List of [x, y] pixel coords. At least 3 points (triangle minimum)."""

BBox = Annotated[list[int], Field(min_length=4, max_length=4)]
"""[xmin, ymin, xmax, ymax] pixel coords."""


class RoomDetection(BaseModel):
    id: str = Field(pattern=r"^room_\d{3,}$")
    type: str
    type_id: int = Field(ge=0, lt=len(CLASS_NAMES))
    polygon: Polygon
    bbox: BBox
    area_pixels: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _type_matches_id(self):
        if self.type not in CLASS_ID:
            raise ValueError(f"Unknown type: {self.type}")
        if CLASS_ID[self.type] != self.type_id:
            raise ValueError(
                f"type_id mismatch: type={self.type} expected id={CLASS_ID[self.type]}, got {self.type_id}"
            )
        return self


class WallsOutput(BaseModel):
    mask_rle: str  # COCO-style RLE
    mask_path: str  # absolute path to PNG on disk
    skeleton_paths_count: int = Field(ge=0)


class SegmentationOutput(BaseModel):
    plan_id: str
    image_size: list[int] = Field(min_length=2, max_length=2)  # [w, h]
    model_version: str
    inference_time_ms: int = Field(ge=0)
    rooms: list[RoomDetection]
    walls: WallsOutput
    warnings: list[str] = Field(default_factory=list)
