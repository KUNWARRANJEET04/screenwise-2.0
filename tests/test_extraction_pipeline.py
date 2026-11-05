
from datetime import datetime, timezone
from io import BytesIO

import pytest
from PIL import Image

from screenwise.config import settings
from screenwise.extraction.pipeline import process_screenshot
from screenwise.schemas.common import ExtractionStatus, ValidationStatus
from screenwise.schemas.ingestion import IngestedScreenshot


class FakeProvider:
    model_name = "fake-test-model"

    def __init__(self, response):
        self.response = response
        self.received_image = None
        self.received_filename = None

    def extract(self, image_bytes, original_filename):
        self.received_image = image_bytes
        self.received_filename = original_filename
        return self.response


def create_png_bytes():
    image = Image.new("RGB", (800, 600), "white")
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def create_screenshot(upload_dir):
    image_bytes = create_png_bytes()
    filename = "a" * 64 + ".png"
    (upload_dir / filename).write_bytes(image_bytes)

    return IngestedScreenshot(
        original_filename="screen-time-test.png",
        stored_filename=filename,
        stored_path=f"data/uploads/{filename}",
        file_sha256="a" * 64,
        image_format="PNG",
        width=800,
        height=600,
        byte_size=len(image_bytes),
        uploaded_at=datetime.now(timezone.utc),
    )


def test_pipeline_processes_screenshot_successfully(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)

    screenshot = create_screenshot(tmp_path)

    provider = FakeProvider({
        "app_usage": [
            {
                "app_name": "Instagram",
                "duration_seconds": 3600,
                "category": "Social",
            }
        ],
        "category_usage": [
            {
                "category_name": "Social",
                "duration_seconds": 3600,
            }
        ],
        "pickups": {
            "total_pickups": 120,
            "notifications": 45,
            "pickups_per_day": 120,
        },
        "confidence": 0.95,
        "warnings": [],
    })

    result = process_screenshot(screenshot, provider=provider)

    assert result.metadata.original_filename == "screen-time-test.png"
    assert result.app_usage[0].app_name == "Instagram"
    assert result.pickups.total_pickups == 120
    assert result.extraction_status == ExtractionStatus.COMPLETE
    assert result.validation_status == ValidationStatus.NEEDS_REVIEW
    assert result.provider == "fake"
    assert result.model_name == "fake-test-model"

    # The provider receives a normalized JPEG.
    with Image.open(BytesIO(provider.received_image)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"

    assert provider.received_filename == "screen-time-test.png"


def test_pipeline_marks_uncertain_extraction_as_partial(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)

    screenshot = create_screenshot(tmp_path)

    provider = FakeProvider({
        "app_usage": [
            {
                "app_name": "Instagram",
                "duration_seconds": 3600,
                "category": "Social",
            }
        ],
        "category_usage": [],
        "pickups": None,
        "confidence": 0.55,
        "warnings": ["Some values are difficult to read."],
    })

    result = process_screenshot(screenshot, provider=provider)

    assert result.extraction_status == ExtractionStatus.PARTIAL
    assert result.validation_status == ValidationStatus.NEEDS_REVIEW
    assert "Some values are difficult to read." in result.warnings


def test_pipeline_rejects_missing_stored_screenshot(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)

    screenshot = create_screenshot(tmp_path)
    (tmp_path / screenshot.stored_filename).unlink()

    provider = FakeProvider({})

    with pytest.raises(FileNotFoundError):
        process_screenshot(screenshot, provider=provider)


def test_pipeline_rejects_invalid_provider_response(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(settings, "upload_dir", tmp_path)

    screenshot = create_screenshot(tmp_path)

    provider = FakeProvider({
        "app_usage": [
            {
                "app_name": "Instagram",
                "duration_seconds": -500,
                "category": "Social",
            }
        ],
        "category_usage": [],
        "pickups": None,
        "confidence": 0.9,
        "warnings": [],
    })

    with pytest.raises(ValueError):
        process_screenshot(screenshot, provider=provider)
