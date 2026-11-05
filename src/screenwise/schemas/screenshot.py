
from datetime import date, datetime

from pydantic import Field, model_validator

from screenwise.schemas.common import ScreenWiseModel


class ScreenshotMetadata(ScreenWiseModel):
    """Metadata associated with an uploaded screenshot."""

    original_filename: str = Field(min_length=1)

    subject_id: str | None = None
    session_id: str | None = None

    file_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
    )

    uploaded_at: datetime | None = None

    report_period_start: date | None = None
    report_period_end: date | None = None

    screenshot_type: str | None = None

    @model_validator(mode="after")
    def validate_report_period(self):
        if (
            self.report_period_start is not None
            and self.report_period_end is not None
            and self.report_period_start > self.report_period_end
        ):
            raise ValueError(
                "Report start date cannot be after end date."
            )

        return self
