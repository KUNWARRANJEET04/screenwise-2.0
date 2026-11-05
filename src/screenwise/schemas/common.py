
# from enum import Enum

# from pydantic import BaseModel, ConfigDict, Field


# class ScreenWiseModel(BaseModel):
#     """Base model shared by ScreenWise schemas."""

#     model_config = ConfigDict(
#         extra="forbid",
#         str_strip_whitespace=True,
#         validate_assignment=True,
#     )


# class ExtractionStatus(str, Enum):
#     COMPLETE = "complete"
#     PARTIAL = "partial"
#     FAILED = "failed"


# class ValidationStatus(str, Enum):
#     VALID = "valid"
#     NEEDS_REVIEW = "needs_review"
#     INVALID = "invalid"


# class SourceEvidence(ScreenWiseModel):
#     """Evidence linking extracted information to its source."""

#     source_filename: str = Field(min_length=1)
#     field_path: str = Field(min_length=1)
#     raw_text: str | None = None

#     # Normalized coordinates between 0 and 1.
#     bounding_box: tuple[
#         float, float, float, float
#     ] | None = None

#     @classmethod
#     def validate_bounding_box(cls, value):
#         return value


from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScreenWiseModel(BaseModel):
    """Base model shared by ScreenWise schemas."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ExtractionStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class ValidationStatus(str, Enum):
    VALID = "valid"
    NEEDS_REVIEW = "needs_review"
    INVALID = "invalid"


class SourceEvidence(ScreenWiseModel):
    """Evidence linking extracted information to its source."""

    source_filename: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    raw_text: str | None = None

    # Normalized coordinates: x1, y1, x2, y2.
    bounding_box: tuple[
        float, float, float, float
    ] | None = None

    @field_validator("bounding_box")
    @classmethod
    def validate_bounding_box(cls, value):
        if value is None:
            return value

        x1, y1, x2, y2 = value

        if not all(0 <= coordinate <= 1 for coordinate in value):
            raise ValueError(
                "Bounding-box coordinates must be between 0 and 1."
            )

        if x1 >= x2 or y1 >= y2:
            raise ValueError(
                "Bounding box must have positive width and height."
            )

        return value
