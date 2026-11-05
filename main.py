
import logging

from screenwise.health import run_health_check
from screenwise.logging_config import configure_logging


def main() -> None:
    configure_logging()
    logger = logging.getLogger("screenwise")

    logger.info("Starting ScreenWise 2.0")

    health = run_health_check()

    for key, value in health.items():
        logger.info("%s: %s", key, value)

    logger.info("ScreenWise initialization completed.")


if __name__ == "__main__":
    main()
