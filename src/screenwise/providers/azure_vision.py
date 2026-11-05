from __future__ import annotations

import logging
from io import BytesIO
from statistics import mean
from typing import Any

from PIL import Image

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import VisualFeatures
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from screenwise.config import settings


logger = logging.getLogger(__name__)


class AzureVisionOCRProvider:
    """
    Microsoft Azure AI Vision OCR provider.

    Extracts text, line-level bounding boxes, and confidence values
    from an image. It does not infer Screen Time categories or metrics.
    """

    provider_name = "azure_vision"
    model_name = "image-analysis-4.0-read"

    def __init__(self) -> None:
        endpoint = settings.azure_vision_endpoint
        key = settings.azure_vision_key

        if not endpoint or not key:
            raise RuntimeError(
                "Azure Vision is not configured. "
                "Set AZURE_VISION_ENDPOINT and AZURE_VISION_KEY in .env."
            )

        self.client = ImageAnalysisClient(
            endpoint=endpoint.rstrip("/"),
            credential=AzureKeyCredential(key),
        )

    @staticmethod
    def _point_coordinates(point: Any) -> tuple[float, float]:
        """
        Support SDK point objects and tuple-like points.
        """
        if hasattr(point, "x") and hasattr(point, "y"):
            return float(point.x), float(point.y)

        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return float(point[0]), float(point[1])

        raise ValueError("Azure returned an unsupported bounding point.")

    @classmethod
    def _normalise_polygon(
        cls,
        polygon: Any,
        image_width: int,
        image_height: int,
    ) -> tuple[float, float, float, float] | None:
        """
        Convert Azure polygon coordinates into normalised xyxy coordinates.
        """
        if not polygon:
            return None

        points = [cls._point_coordinates(point) for point in polygon]

        if not points:
            return None

        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]

        x1 = max(0.0, min(x_values)) / image_width
        y1 = max(0.0, min(y_values)) / image_height
        x2 = min(float(image_width), max(x_values)) / image_width
        y2 = min(float(image_height), max(y_values)) / image_height

        # Avoid creating invalid zero-sized boxes.
        if x2 <= x1 or y2 <= y1:
            return None

        return (
            max(0.0, min(1.0, x1)),
            max(0.0, min(1.0, y1)),
            max(0.0, min(1.0, x2)),
            max(0.0, min(1.0, y2)),
        )

    def extract(
        self,
        image_bytes: bytes,
        original_filename: str,
    ) -> dict:
        if not image_bytes:
            raise ValueError("Cannot run OCR on an empty image.")

        try:
            with Image.open(BytesIO(image_bytes)) as image:
                image_width, image_height = image.size

            result = self.client.analyze(
                image_data=image_bytes,
                visual_features=[VisualFeatures.READ],
            )

        except HttpResponseError as exc:
            status_code = getattr(exc, "status_code", "unknown")
            logger.exception(
                "Azure Vision OCR request failed for %s. HTTP status: %s",
                original_filename,
                status_code,
            )
            raise RuntimeError(
                f"Azure Vision OCR failed with HTTP status {status_code}. "
                "Check the endpoint, key, resource status, and quota."
            ) from exc

        except Exception:
            logger.exception(
                "Unexpected Azure OCR error for %s",
                original_filename,
            )
            raise

        lines: list[dict] = []
        evidence: list[dict] = []
        word_confidences: list[float] = []

        read_result = getattr(result, "read", None)

        if read_result is not None:
            for block_index, block in enumerate(read_result.blocks or []):
                for line_index, line in enumerate(block.lines or []):
                    line_text = (line.text or "").strip()

                    if not line_text:
                        continue

                    bounding_box = self._normalise_polygon(
                        getattr(line, "bounding_polygon", None),
                        image_width,
                        image_height,
                    )

                    words = []

                    for word in getattr(line, "words", None) or []:
                        word_text = (getattr(word, "text", "") or "").strip()
                        word_confidence = getattr(word, "confidence", None)

                        if word_confidence is not None:
                            word_confidences.append(float(word_confidence))

                        words.append(
                            {
                                "text": word_text,
                                "confidence": (
                                    float(word_confidence)
                                    if word_confidence is not None
                                    else None
                                ),
                                "bounding_box": self._normalise_polygon(
                                    getattr(word, "bounding_polygon", None),
                                    image_width,
                                    image_height,
                                ),
                            }
                        )

                    lines.append(
                        {
                            "text": line_text,
                            "block_index": block_index,
                            "line_index": line_index,
                            "bounding_box": bounding_box,
                            "words": words,
                        }
                    )

                    evidence.append(
                        {
                            "field_path": (
                                f"ocr.blocks[{block_index}].lines[{line_index}]"
                            ),
                            "raw_text": line_text,
                            "bounding_box": bounding_box,
                        }
                    )

        full_text = "\n".join(item["text"] for item in lines)

        confidence = (
            mean(word_confidences)
            if word_confidences
            else None
        )

        warnings = []

        if not lines:
            warnings.append(
                "Azure OCR completed but did not detect readable text."
            )

        return {
            "ocr_text": full_text,
            "ocr_lines": lines,
            "evidence": evidence,
            "confidence": confidence,
            "warnings": warnings,
            "app_usage": [],
            "category_usage": [],
            "pickups": None,
            "provider": self.provider_name,
            "model_name": self.model_name,
        }