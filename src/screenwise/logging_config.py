
import logging
import sys

from screenwise.config import settings


def configure_logging() -> None:
    """Configure consistent application logging."""

    logging.basicConfig(
        level=settings.log_level.upper(),
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
