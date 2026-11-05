
import pytest
from pydantic import ValidationError

from screenwise.schemas import (
    AppUsage,
    CategoryUsage,
    PickupMetrics,
    ScreenshotMetadata,
    ExtractionResult,
    SourceEvidence,
    ValidationStatus,
)


def test_valid_app_usage():
    app = AppUsage(
        app_name="Instagram",
        duration_seconds=3600,
        category="Social",
    )

    assert app.app_name == "Instagram"
    assert app.duration_minutes == 60


def test_negative_app_duration_rejected():
    with pytest.raises(ValidationError):
        AppUsage(
            app_name="Instagram",
            duration_seconds=-100,
        )


def test_valid_category_usage():
    category = CategoryUsage(
        category_name="Social",
        duration_seconds=7200,
    )

    assert category.duration_minutes == 120


def test_negative_pickups_rejected():
    with pytest.raises(ValidationError):
        PickupMetrics(total_pickups=-10)


def test_invalid_report_period_rejected():
    with pytest.raises(ValidationError):
        ScreenshotMetadata(
            original_filename="screen.png",
            report_period_start="2026-11-05",
            report_period_end="2026-11-01",
        )


def test_invalid_confidence_rejected():
    with pytest.raises(ValidationError):
        ExtractionResult(
            metadata=ScreenshotMetadata(
                original_filename="screen.png"
            ),
            confidence=1.5,
        )


def test_invalid_bounding_box_rejected():
    with pytest.raises(ValidationError):
        SourceEvidence(
            source_filename="screen.png",
            field_path="app_usage[0].duration_seconds",
            bounding_box=(0.8, 0.2, 0.3, 0.9),
        )


def test_extraction_result_defaults():
    result = ExtractionResult(
        metadata=ScreenshotMetadata(
            original_filename="screen.png"
        ),
        validation_status=ValidationStatus.NEEDS_REVIEW,
    )

    assert result.app_usage == []
    assert result.category_usage == []
    assert result.warnings == []
    assert result.confidence is None
