from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.normalized import NormalizedMediaDocument


class ReasoningRequest(BaseModel):
    """
    Request containing the complete response produced
    by the deterministic media processing pipeline.
    """

    source_type: str | None = None
    source: str | None = None
    metadata: dict = Field(default_factory=dict)
    validation: dict = Field(default_factory=dict)
    acquired: bool = False
    detected: bool = False
    processing: dict = Field(default_factory=dict)
    pipeline_metadata: dict = Field(default_factory=dict)

    normalized: NormalizedMediaDocument


class ReasoningResponse(BaseModel):
    """
    AI-generated reasoning result based only on the
    deterministic pipeline output.
    """

    document_id: str

    topics: list[dict[str, str]] = Field(
        default_factory=list
    )

    summary: str