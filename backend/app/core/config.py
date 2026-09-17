from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Universal AI Media Processing Pipeline"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Storage
    STORAGE_DIR: Path = Path("storage")
    TEMP_DIR: Path = Path("storage/temp")
    ORIGINALS_DIR: Path = Path("storage/originals")

    # Upload limits
    MAX_FILE_SIZE_MB: int = 500

    # URL acquisition limits
    MAX_DOWNLOAD_SIZE_MB: int = 500
    DOWNLOAD_TIMEOUT_SECONDS: int = 30
    MAX_REDIRECTS: int = 5

    # URL security
    ALLOWED_URL_SCHEMES: tuple[str, ...] = ("https",)

    # Supported media types
    SUPPORTED_MIME_TYPES: tuple[str, ...] = (
        # Video
        "video/mp4",
        "video/webm",
        "video/quicktime",
        "video/x-msvideo",
        "video/mpeg",

        # Audio
        "audio/mpeg",
        "audio/wav",
        "audio/x-wav",
        "audio/ogg",
        "audio/webm",
        "audio/mp4",
        "audio/aac",
        "audio/flac",

        # Images
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/tiff",

        # PDF
        "application/pdf",
    )

    # Detection limits
    MIME_SNIFF_BYTES: int = 8192

        # OCR
    TESSERACT_CMD: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def max_download_size_bytes(self) -> int:
        return self.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024


settings = Settings()