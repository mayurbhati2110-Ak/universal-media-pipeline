from enum import Enum
from typing import Any, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from app.models.processing import ProcessingResult


if TYPE_CHECKING:
    from app.schemas.normalized import NormalizedMediaDocument


class MediaType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    PDF = "pdf"
    UNKNOWN = "unknown"


class InputSource(str, Enum):
    UPLOAD = "upload"
    URL = "url"


class ValidationStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"


class MediaMetadata(BaseModel):
    filename: Optional[str] = None
    original_filename: Optional[str] = None

    media_type: MediaType = MediaType.UNKNOWN
    mime_type: Optional[str] = None
    detected_format: Optional[str] = None

    size_bytes: int = 0

    width: Optional[int] = None
    height: Optional[int] = None

    duration_seconds: Optional[float] = None
    page_count: Optional[int] = None

    content_hash: Optional[str] = None


class ValidationResult(BaseModel):
    status: ValidationStatus

    is_readable: bool = False
    is_supported: bool = False
    integrity_valid: bool = False
    size_valid: bool = False

    errors: list[str] = Field(
        default_factory=list
    )

    warnings: list[str] = Field(
        default_factory=list
    )


class MediaInputResult(BaseModel):
    """
    Complete result of the input, detection, validation,
    and processing stages.
    """

    source_type: InputSource

    source: Optional[str] = None

    metadata: MediaMetadata

    validation: ValidationResult

    acquired: bool = False
    detected: bool = False

    processing: Optional[ProcessingResult] = None

    pipeline_metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    normalized: Optional["NormalizedMediaDocument"] = None


from app.schemas.normalized import NormalizedMediaDocument

MediaInputResult.model_rebuild()