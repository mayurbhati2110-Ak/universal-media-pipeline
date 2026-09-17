from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ArtifactType(str, Enum):
    ORIGINAL = "original"
    NORMALIZED = "normalized"
    AUDIO = "audio"
    IMAGE = "image"
    VIDEO = "video"
    PDF = "pdf"
    FRAME = "frame"
    THUMBNAIL = "thumbnail"
    TRANSCRIPT = "transcript"
    OCR_TEXT = "ocr_text"
    STRUCTURED_DATA = "structured_data"
    SUMMARY = "summary"


class ProcessingArtifact(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType

    file_path: Optional[str] = None
    mime_type: Optional[str] = None

    size_bytes: int = 0
    content_hash: Optional[str] = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ProcessingError(BaseModel):
    stage: str
    code: str
    message: str

    recoverable: bool = False

    details: Optional[dict[str, Any]] = None


class ProcessingResult(BaseModel):
    status: ProcessingStatus

    media_type: str

    artifacts: list[ProcessingArtifact] = Field(
        default_factory=list
    )

    extracted_data: dict[str, Any] = Field(
        default_factory=dict
    )

    warnings: list[str] = Field(
        default_factory=list
    )

    errors: list[ProcessingError] = Field(
        default_factory=list
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )