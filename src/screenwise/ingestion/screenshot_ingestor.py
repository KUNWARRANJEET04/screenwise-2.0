
import hashlib
import json

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from screenwise.config import settings
from screenwise.schemas.ingestion import (
    IngestedScreenshot,
    IngestionResult,
    IngestionStatus,
)


ALLOWED_FORMATS = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".webp": "WEBP",
}

MAX_IMAGE_PIXELS = 40_000_000


def validate_image(
    image_bytes: bytes,
    filename: str,
) -> tuple[str, int, int]:

    if not image_bytes:
        raise ValueError("Uploaded file is empty.")

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_FORMATS:
        raise ValueError("Unsupported image extension.")

    max_bytes = settings.max_upload_mb * 1024 * 1024

    if len(image_bytes) > max_bytes:
        raise ValueError(
            f"File exceeds the {settings.max_upload_mb} MB limit."
        )

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            width, height = image.size

            if image_format != ALLOWED_FORMATS[extension]:
                raise ValueError(
                    "File extension does not match actual image format."
                )

            if width <= 0 or height <= 0:
                raise ValueError("Invalid image dimensions.")

            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Image dimensions exceed the allowed limit.")

            image.verify()

    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Uploaded file is not a valid image.") from exc

    return image_format, width, height


def ingest_image(
    image_bytes: bytes,
    original_filename: str,
) -> IngestionResult:
    """Validate, fingerprint and safely store an image."""

    if not isinstance(image_bytes, bytes):
        raise ValueError("Image content must be bytes.")

    if not isinstance(original_filename, str):
        raise ValueError("Filename must be a string.")

    safe_filename = Path(
        original_filename.replace("\\", "/")
    ).name

    if safe_filename in {"", ".", ".."}:
        raise ValueError("A valid filename is required.")

    image_format, width, height = validate_image(
        image_bytes,
        safe_filename,
    )

    file_hash = hashlib.sha256(image_bytes).hexdigest()

    extension = Path(safe_filename).suffix.lower()

    stored_filename = f"{file_hash}{extension}"

    upload_dir = settings.upload_dir
    manifest_dir = settings.processed_dir / "ingestion_manifests"

    upload_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    stored_file = upload_dir / stored_filename
    manifest_file = manifest_dir / f"{file_hash}.json"

    # Detect previously ingested content.
    if manifest_file.exists():
        existing_data = json.loads(
            manifest_file.read_text(encoding="utf-8")
        )

        existing_screenshot = IngestedScreenshot.model_validate(
            existing_data
        )

        return IngestionResult(
            status=IngestionStatus.DUPLICATE,
            screenshot=existing_screenshot,
            message="This screenshot has already been ingested.",
        )

    # Create screenshot metadata.
    screenshot = IngestedScreenshot(
        original_filename=safe_filename,
        stored_filename=stored_filename,
        stored_path=f"data/uploads/{stored_filename}",
        file_sha256=file_hash,
        image_format=image_format,
        width=width,
        height=height,
        byte_size=len(image_bytes),
        uploaded_at=datetime.now(timezone.utc),
    )

    # Write the image atomically.
    if not stored_file.exists():
        temporary_image = upload_dir / f".{uuid4().hex}.tmp"

        try:
            temporary_image.write_bytes(image_bytes)
            temporary_image.replace(stored_file)
        finally:
            temporary_image.unlink(missing_ok=True)

    # Write the metadata manifest atomically.
    temporary_manifest = manifest_dir / f".{uuid4().hex}.tmp"

    try:
        temporary_manifest.write_text(
            json.dumps(
                screenshot.model_dump(mode="json"),
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary_manifest.replace(manifest_file)

    finally:
        temporary_manifest.unlink(missing_ok=True)

    return IngestionResult(
        status=IngestionStatus.ACCEPTED,
        screenshot=screenshot,
        message="Screenshot successfully ingested.",
    )
