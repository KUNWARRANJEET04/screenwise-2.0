import logging
from pathlib import Path

from screenwise.config import settings
from screenwise.ocr.preprocessor import preprocess_image
from screenwise.providers.azure_vision import AzureVisionOCRProvider

from screenwise.schemas.common import (
    ExtractionStatus,
    ValidationStatus,
    SourceEvidence,
)
from screenwise.schemas.extraction import ExtractionResult
from screenwise.schemas.ingestion import IngestedScreenshot
from screenwise.schemas.screenshot import ScreenshotMetadata


logger = logging.getLogger(__name__)


def process_screenshot(
    screenshot: IngestedScreenshot,
    provider=None,
) -> ExtractionResult:
    """
    Process an already-ingested screenshot.

    Default provider: Microsoft Azure AI Vision OCR.

    A provider can still be injected during tests.
    """

    safe_filename = Path(screenshot.stored_filename).name

    if safe_filename != screenshot.stored_filename:
        raise ValueError("Invalid stored screenshot filename.")

    image_path = settings.upload_dir / safe_filename

    if not image_path.is_file():
        raise FileNotFoundError(
            f"Stored screenshot was not found: {safe_filename}"
        )

    original_image_bytes = image_path.read_bytes()

    processed_image = preprocess_image(original_image_bytes)

    if provider is None:
        provider = AzureVisionOCRProvider()

    logger.info(
        "Starting OCR extraction for %s using %s",
        screenshot.original_filename,
        provider.__class__.__name__,
    )

    extracted_data = provider.extract(
        image_bytes=processed_image.image_bytes,
        original_filename=screenshot.original_filename,
    )

    app_usage = extracted_data.get("app_usage") or []
    category_usage = extracted_data.get("category_usage") or []
    pickups = extracted_data.get("pickups")

    raw_ocr_text = extracted_data.get("ocr_text")
    ocr_lines = extracted_data.get("ocr_lines") or []

    warnings = list(extracted_data.get("warnings") or [])

    has_structured_data = bool(
        app_usage or category_usage or pickups
    )

    if not has_structured_data:
        if not raw_ocr_text:
            warnings.append(
                "No readable text was extracted from this screenshot."
            )

    # This pipeline retains OCR evidence. The deterministic Screen Time
    # parser enriches the result in the Streamlit application layer.
    extraction_status = (
        ExtractionStatus.COMPLETE
        if has_structured_data and not warnings
        else ExtractionStatus.PARTIAL
    )

    metadata = ScreenshotMetadata(
        original_filename=screenshot.original_filename,
        file_sha256=screenshot.file_sha256,
        uploaded_at=screenshot.uploaded_at,
    )

    evidence_items = []

    for item in extracted_data.get("evidence") or []:
        evidence_items.append(
            SourceEvidence(
                source_filename=screenshot.original_filename,
                field_path=item["field_path"],
                raw_text=item.get("raw_text"),
                bounding_box=item.get("bounding_box"),
            )
        )

    result = ExtractionResult(
        metadata=metadata,
        app_usage=app_usage,
        category_usage=category_usage,
        pickups=pickups,
        raw_ocr_text=raw_ocr_text,
        ocr_lines=ocr_lines,
        extraction_status=extraction_status,
        validation_status=ValidationStatus.NEEDS_REVIEW,
        confidence=extracted_data.get("confidence"),
        evidence=evidence_items,
        warnings=warnings,
        provider=(
            extracted_data.get("provider")
            or getattr(
                provider,
                "provider_name",
                provider.__class__.__name__.replace("Provider", "").lower(),
            )
        ),
        model_name=(
            extracted_data.get("model_name")
            or getattr(provider, "model_name", None)
        ),
    )

    logger.info(
        "Extraction completed for %s. Status: %s. OCR lines: %s",
        screenshot.original_filename,
        result.extraction_status.value,
        len(result.ocr_lines),
    )

    return result