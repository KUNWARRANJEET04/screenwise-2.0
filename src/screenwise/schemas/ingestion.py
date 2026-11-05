
from enum import Enum
from datetime import datetime

from pydantic import Field

from screenwise.schemas.common import ScreenWiseModel


class IngestionStatus(str, Enum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


class IngestedScreenshot(ScreenWiseModel):
    """Metadata for a successfully ingested screenshot."""

    original_filename: str = Field(min_length=1)
    stored_filename: str = Field(min_length=1)

    stored_path: str = Field(min_length=1)

    file_sha256: str = Field(
        pattern=r"^[a-fA-F0-9]{64}$"
    )

    image_format: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    byte_size: int = Field(gt=0)

    uploaded_at: datetime


class IngestionResult(ScreenWiseModel):
    """Result of a screenshot ingestion operation."""

    status: IngestionStatus
    screenshot: IngestedScreenshot
    message: str
