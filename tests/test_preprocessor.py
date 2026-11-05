
from io import BytesIO

import pytest
from PIL import Image

from screenwise.ocr.preprocessor import preprocess_image


def create_image_bytes(
    width: int = 800,
    height: int = 600,
    image_format: str = "PNG",
    mode: str = "RGB",
) -> bytes:
    image = Image.new(mode, (width, height), "white")
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_preprocess_converts_png_to_jpeg():
    result = preprocess_image(create_image_bytes())

    assert result.output_format == "JPEG"
    assert result.processed_width == 800
    assert result.processed_height == 600

    with Image.open(BytesIO(result.image_bytes)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"


def test_preprocess_resizes_large_image_without_distortion():
    result = preprocess_image(
        create_image_bytes(4000, 2000),
        max_dimension=2000,
    )

    assert result.processed_width == 2000
    assert result.processed_height == 1000
    assert result.was_resized is True


def test_preprocess_does_not_upscale_small_image():
    result = preprocess_image(
        create_image_bytes(800, 600),
        max_dimension=2000,
    )

    assert result.processed_width == 800
    assert result.processed_height == 600
    assert result.was_resized is False


def test_preprocess_rejects_empty_input():
    with pytest.raises(ValueError, match="non-empty bytes"):
        preprocess_image(b"")


def test_preprocess_rejects_invalid_image():
    with pytest.raises(ValueError, match="Could not safely preprocess"):
        preprocess_image(b"this is not an image")


def test_preprocess_rejects_invalid_quality():
    with pytest.raises(ValueError, match="JPEG quality"):
        preprocess_image(create_image_bytes(), jpeg_quality=100)


def test_preprocess_rejects_invalid_max_dimension():
    with pytest.raises(ValueError, match="Maximum dimension"):
        preprocess_image(create_image_bytes(), max_dimension=0)
