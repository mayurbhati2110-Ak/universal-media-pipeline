from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.media import MediaType, InputSource
from app.models.processing import (
    ProcessingArtifact,
    ProcessingError,
    ProcessingStatus,
)
from app.models.provenance import Evidence, Provenance


# ============================================================
# Universal Source
# ============================================================

class NormalizedSource(BaseModel):
    """
    Describes where the media originally came from.
    """

    source_type: InputSource
    filename: Optional[str] = None
    url: Optional[str] = None

    content_hash: Optional[str] = None

    acquisition: dict[str, Any] = Field(
        default_factory=dict
    )


# ============================================================
# Universal Metadata
# ============================================================

class NormalizedMetadata(BaseModel):
    """
    Common metadata shared across all media types.
    """

    filename: Optional[str] = None
    mime_type: Optional[str] = None
    detected_format: Optional[str] = None

    size_bytes: int = 0

    duration_seconds: Optional[float] = None
    page_count: Optional[int] = None

    width: Optional[int] = None
    height: Optional[int] = None

    content_hash: Optional[str] = None

    extra: dict[str, Any] = Field(
        default_factory=dict
    )


# ============================================================
# Structured Elements
# ============================================================

class StructuredElement(BaseModel):
    """
    Generic structured content element.

    Used for things such as:
    - OCR text
    - headings
    - labels
    - values
    - table cells
    - other extracted structures
    """

    element_id: Optional[str] = None

    type: str = "text"

    text: Optional[str] = None

    value: Any = None

    bbox: Optional[list[int]] = None

    confidence: Optional[float] = None

    provenance: Optional[Any] = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class ImageStructuredElement(StructuredElement):
    """
    Structured element extracted from an image.

    Extends the universal StructuredElement model while
    allowing image-specific metadata such as OCR regions,
    bounding boxes, and visual element types.
    """

    type: str = "image_element"

    bbox: Optional[list[int]] = None

    text: Optional[str] = None

    confidence: Optional[float] = None


# ============================================================
# Normalized Content
# ============================================================

class NormalizedContent(BaseModel):
    """
    Common content representation produced by every processor.
    """

    segments: list[Evidence] = Field(
        default_factory=list
    )

    evidence: list[Evidence] = Field(
        default_factory=list
    )

    structured_elements: list[StructuredElement] = Field(
        default_factory=list
    )

    topics: list[dict[str, Any]] = Field(
        default_factory=list
    )

    summary: Optional[str] = None

    extra: dict[str, Any] = Field(
        default_factory=dict
    )


# ============================================================
# Processing Stage
# ============================================================

class ProcessingStage(BaseModel):
    """
    Records execution of an individual pipeline stage.
    """

    name: str

    status: str

    message: Optional[str] = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


# ============================================================
# Universal Processing Information
# ============================================================

class NormalizedProcessing(BaseModel):
    """
    Processing lifecycle information.
    """

    status: str

    stages: list[ProcessingStage] = Field(
        default_factory=list
    )

    cache_hit: bool = False

    warnings: list[str] = Field(
        default_factory=list
    )

    errors: list[ProcessingError] = Field(
        default_factory=list
    )


# ============================================================
# Universal Artifact Collection
# ============================================================

class NormalizedArtifacts(BaseModel):
    """
    Derived files generated during processing.
    """

    items: list[ProcessingArtifact] = Field(
        default_factory=list
    )


# ============================================================
# Universal Normalized Document
# ============================================================

class NormalizedMediaDocument(BaseModel):
    """
    Universal output contract.

    Every media processor ultimately produces this structure,
    regardless of whether the original input was:

        video
        audio
        image
        PDF
    """

    document_id: str

    schema_version: str = "1.0"

    media_type: MediaType

    source: NormalizedSource

    metadata: NormalizedMetadata

    content: NormalizedContent = Field(
        default_factory=NormalizedContent
    )

    artifacts: NormalizedArtifacts = Field(
        default_factory=NormalizedArtifacts
    )

    provenance: list[Provenance | Evidence] = Field(
        default_factory=list
    )

    processing: NormalizedProcessing

    # Modality-specific information that does not
    # fit the common contract.
    extra: dict[str, Any] = Field(
        default_factory=dict
    )