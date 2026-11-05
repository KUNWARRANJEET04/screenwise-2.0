
from typing import Protocol


class ExtractionProvider(Protocol):
    """Common interface for ScreenWise visual extraction providers."""

    def extract(
        self,
        image_bytes: bytes,
        original_filename: str,
    ) -> dict:
        """Extract structured Screen Time information from an image."""
        ...
