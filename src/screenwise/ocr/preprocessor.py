
from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class ProcessedImage:
    image_bytes: bytes
    original_width: int
    original_height: int
    processed_width: int
    processed_height: int
    output_format: str
    was_resized: bool


def preprocess_image(
    image_bytes: bytes,
    max_dimension: int = 2400,
    jpeg_quality: int = 90,
) -> ProcessedImage:
    """Normalize a screenshot for visual extraction without changing its source file."""

    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("Image content must be non-empty bytes.")

    if max_dimension < 1:
        raise ValueError("Maximum dimension must be greater than zero.")

    if not 1 <= jpeg_quality <= 95:
        raise ValueError("JPEG quality must be between 1 and 95.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(BytesIO(image_bytes)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)

                original_width, original_height = image.size

                if original_width <= 0 or original_height <= 0:
                    raise ValueError("Invalid image dimensions.")

                # Composite transparent screenshots onto a white background.
                if image.mode in ("RGBA", "LA") or (
                    image.mode == "P" and "transparency" in image.info
                ):
                    rgba_image = image.convert("RGBA")
                    background = Image.new("RGB", rgba_image.size, "white")
                    background.paste(rgba_image, mask=rgba_image.getchannel("A"))
                    image = background
                else:
                    image = image.convert("RGB")

                image.thumbnail(
                    (max_dimension, max_dimension),
                    Image.Resampling.LANCZOS,
                )

                processed_width, processed_height = image.size
                output = BytesIO()

                image.save(
                    output,
                    format="JPEG",
                    quality=jpeg_quality,
                    optimize=True,
                )

                return ProcessedImage(
                    image_bytes=output.getvalue(),
                    original_width=original_width,
                    original_height=original_height,
                    processed_width=processed_width,
                    processed_height=processed_height,
                    output_format="JPEG",
                    was_resized=(
                        processed_width != original_width
                        or processed_height != original_height
                    ),
                )

    except (UnidentifiedImageError, OSError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("Could not safely preprocess this image.") from exc
