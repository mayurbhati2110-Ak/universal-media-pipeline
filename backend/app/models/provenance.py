from typing import Optional

from pydantic import BaseModel


class Provenance(BaseModel):
    source_type: str
    source_artifact: Optional[str] = None

    # Document/page provenance
    page: Optional[int] = None

    # Time-based media provenance
    timestamp_start: Optional[float] = None
    timestamp_end: Optional[float] = None
    frame_number: Optional[int] = None

    # Image/video region provenance
    bbox: Optional[list[int]] = None

    # How the evidence was extracted
    extraction_method: Optional[str] = None


class Evidence(BaseModel):
    evidence_id: str
    content_type: str = "text"
    text: str
    provenance: Provenance
    confidence: Optional[float] = None