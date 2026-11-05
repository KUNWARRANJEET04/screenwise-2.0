"""ScreenWise extraction package."""

__all__ = ["process_screenshot"]


def process_screenshot(*args, **kwargs):
    """Import the OCR pipeline only when it is actually requested."""
    from screenwise.extraction.pipeline import process_screenshot as _process_screenshot
    return _process_screenshot(*args, **kwargs)
