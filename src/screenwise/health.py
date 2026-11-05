
from screenwise.config import settings, create_data_directories


def run_health_check() -> dict:
    """Check the basic application environment."""

    create_data_directories()

    return {
        "application": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "data_directory": settings.data_dir.exists(),
        "upload_directory": settings.upload_dir.exists(),
        "processed_directory": settings.processed_dir.exists(),
        "status": "healthy",
    }
