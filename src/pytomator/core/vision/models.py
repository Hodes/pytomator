"""Pydantic models for template captures and vision-related data."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


class TemplateCapture(BaseModel):
    """Represents a single screen region capture used for template matching."""

    id: str = Field(default_factory=_generate_id, description="Unique identifier")
    name: str = Field(..., description="Template name (used as identifier in scripts)")
    image_path: str = Field(..., description="Relative path to saved image, e.g. 'templates/<id>.png'")
    region_abs: tuple[int, int, int, int] = Field(
        ..., description="Absolute region (x, y, w, h) on the full screen"
    )
    region_rel: tuple[int, int, int, int] = Field(
        default=(0, 0, 0, 0),
        description="Relative region (x, y, w, h) relative to the active window",
    )
    screen_width: int = Field(default=0, description="Screen width at capture time")
    screen_height: int = Field(default=0, description="Screen height at capture time")
    pct_abs: tuple[float, float, float, float] = Field(
        default=(0.0, 0.0, 0.0, 0.0),
        description="Absolute percentual region (x/w, y/h, w/w, h/h)",
    )
    pct_rel: tuple[float, float, float, float] = Field(
        default=(0.0, 0.0, 0.0, 0.0),
        description="Relative percentual region",
    )
    active_window_title: Optional[str] = Field(
        default=None, description="Title of the active window at capture time"
    )
    confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Default confidence threshold for template matching (0.0 to 1.0)",
    )
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")

    class Config:
        frozen = False  # Allow mutation at runtime