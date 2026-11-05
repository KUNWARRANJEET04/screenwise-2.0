
from io import BytesIO

import pytest
from PIL import Image

from screenwise.config import settings
from screenwise.ingestion import ingest_image
from screenwise.schemas.ingestion import IngestionStatus


def create_test_image() -> bytes:
    buffer = BytesIO()

    image = Image.new(
        "RGB",
        (200, 300),
        color="white",
    )

    image.save(buffer, format="PNG")

    return buffer.getvalue()


@pytest.fixture
def temporary_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "upload_dir",
        tmp_path / "uploads",
    )

    monkeypatch.setattr(
        settings,
        "processed_dir",
        tmp_path / "processed",
    )

    monkeypatch.setattr(
        settings,
        "max_upload_mb",
        15,
    )


def test_valid_image_ingestion(temporary_storage):
    result = ingest_image(
        create_test_image(),
        "screentime.png",
    )

    assert result.status == IngestionStatus.ACCEPTED
    assert result.screenshot.original_filename == "screentime.png"
    assert result.screenshot.image_format == "PNG"
    assert result.screenshot.width == 200
    assert result.screenshot.height == 300
    assert len(result.screenshot.file_sha256) == 64


def test_duplicate_image_detection(temporary_storage):
    image = create_test_image()

    first = ingest_image(image, "first.png")
    second = ingest_image(image, "second.png")

    assert first.status == IngestionStatus.ACCEPTED
    assert second.status == IngestionStatus.DUPLICATE

    assert (
        first.screenshot.file_sha256
        == second.screenshot.file_sha256
    )


def test_invalid_image_rejected(temporary_storage):
    with pytest.raises(ValueError):
        ingest_image(
            b"this is not an image",
            "invalid.png",
        )


def test_extension_mismatch_rejected(temporary_storage):
    with pytest.raises(ValueError):
        ingest_image(
            create_test_image(),
            "screentime.jpg",
        )


def test_unsupported_extension_rejected(temporary_storage):
    with pytest.raises(ValueError):
        ingest_image(
            create_test_image(),
            "screentime.gif",
        )


def test_empty_file_rejected(temporary_storage):
    with pytest.raises(ValueError):
        ingest_image(
            b"",
            "empty.png",
        )


def test_oversized_file_rejected(temporary_storage, monkeypatch):
    monkeypatch.setattr(
        settings,
        "max_upload_mb",
        0,
    )

    with pytest.raises(ValueError):
        ingest_image(
            create_test_image(),
            "large.png",
        )


def test_filename_path_traversal_is_removed(temporary_storage):
    result = ingest_image(
        create_test_image(),
        "../../screentime.png",
    )

    assert result.screenshot.original_filename == "screentime.png"
