from pydantic import Field

from screenwise.schemas.common import (
    ScreenWiseModel,
    ExtractionStatus,
    ValidationStatus,
    SourceEvidence,
)
from screenwise.schemas.screenshot import ScreenshotMetadata
from screenwise.schemas.usage import (
    AppUsage,
    CategoryUsage,
    PickupMetrics,
)


class ExtractionResult(ScreenWiseModel):
    metadata: ScreenshotMetadata

    # Structured Screen Time fields.
    app_usage: list[AppUsage] = Field(default_factory=list)
    category_usage: list[CategoryUsage] = Field(default_factory=list)
    pickups: PickupMetrics | None = None

    # Raw OCR output retained for parsing and auditing.
    raw_ocr_text: str | None = None
    ocr_lines: list[dict] = Field(default_factory=list)

    extraction_status: ExtractionStatus = ExtractionStatus.PARTIAL
    validation_status: ValidationStatus = ValidationStatus.NEEDS_REVIEW

    confidence: float | None = Field(default=None, ge=0, le=1)

    evidence: list[SourceEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    provider: str | None = None
    model_name: str | None = None