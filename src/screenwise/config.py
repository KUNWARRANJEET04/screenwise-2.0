from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "ScreenWise"
    app_version: str = "2.0.0"
    environment: str = "development"
    log_level: str = "INFO"

    data_dir: Path = PROJECT_ROOT / "data"
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"

    max_upload_mb: int = 15

    azure_vision_endpoint: str | None = None
    azure_vision_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


def create_data_directories() -> None:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)