from typing import Any
from uuid import uuid4

from app.models.media import MediaInputResult
from app.models.processing import ProcessingResult
from app.models.provenance import Evidence

from app.schemas.normalized import (
    NormalizedArtifacts,
    NormalizedContent,
    NormalizedMediaDocument,
    NormalizedMetadata,
    NormalizedProcessing,
    NormalizedSource,
    ProcessingStage,
    StructuredElement,
)


class NormalizedOutputBuilder:
    """
    Converts the current pipeline result into the universal
    NormalizedMediaDocument contract.

    This layer intentionally sits outside the individual
    processors so modality-specific processors do not need
    to know about the final API contract.
    """

    SCHEMA_VERSION = "1.0"

    @classmethod
    def build(
        cls,
        input_result: MediaInputResult,
    ) -> NormalizedMediaDocument:

        processing = input_result.processing

        if processing is None:
            raise ValueError(
                "Cannot create normalized output without "
                "a processing result."
            )

        extracted = processing.extracted_data or {}

        # ----------------------------------------------------
        # Document ID
        # ----------------------------------------------------

        document_id = cls._create_document_id(
            input_result
        )

        # ----------------------------------------------------
        # Source
        # ----------------------------------------------------

        source = NormalizedSource(
            source_type=input_result.source_type,
            filename=(
                input_result.metadata.original_filename
                or input_result.metadata.filename
            ),
            url=(
                input_result.source
                if input_result.source_type.value == "url"
                else None
            ),
            content_hash=input_result.metadata.content_hash,
            acquisition={
                "acquired": input_result.acquired,
                "detected": input_result.detected,
            },
        )

        # ----------------------------------------------------
        # Metadata
        # ----------------------------------------------------

        metadata = NormalizedMetadata(
            filename=input_result.metadata.filename,
            mime_type=input_result.metadata.mime_type,
            detected_format=input_result.metadata.detected_format,
            size_bytes=input_result.metadata.size_bytes,
            duration_seconds=input_result.metadata.duration_seconds,
            page_count=input_result.metadata.page_count,
            width=input_result.metadata.width,
            height=input_result.metadata.height,
            content_hash=input_result.metadata.content_hash,
            extra=dict(processing.metadata or {}),
        )

        # ----------------------------------------------------
        # Evidence
        # ----------------------------------------------------

        evidence = cls._extract_evidence(
            extracted
        )

        # ----------------------------------------------------
        # Structured elements
        # ----------------------------------------------------

        structured_elements = (
            cls._extract_structured_elements(
                extracted
            )
        )

        # ----------------------------------------------------
        # Content
        # ----------------------------------------------------

        content = NormalizedContent(
            segments=evidence,
            evidence=evidence,
            structured_elements=structured_elements,
            topics=cls._extract_topics(
                extracted
            ),
            summary=cls._extract_summary(
                extracted
            ),
            extra={
                "raw_extracted_data": extracted,
            },
        )

        # ----------------------------------------------------
        # Processing stages
        # ----------------------------------------------------

        stages = cls._build_stages(
            processing
        )

        normalized_processing = NormalizedProcessing(
            status=processing.status.value,
            stages=stages,
            cache_hit=False,
            warnings=list(processing.warnings),
            errors=list(processing.errors),
        )

        # ----------------------------------------------------
        # Provenance
        # ----------------------------------------------------

        provenance = cls._extract_provenance(
            extracted,
            evidence,
        )

        # ----------------------------------------------------
        # Final universal document
        # ----------------------------------------------------

        return NormalizedMediaDocument(
            document_id=document_id,
            schema_version=cls.SCHEMA_VERSION,
            media_type=input_result.metadata.media_type,
            source=source,
            metadata=metadata,
            content=content,
            artifacts=NormalizedArtifacts(
                items=processing.artifacts
            ),
            provenance=provenance,
            processing=normalized_processing,
            extra={
                "validation": (
                    input_result.validation.model_dump()
                ),
                "pipeline_metadata": (
                    input_result.pipeline_metadata
                ),
            },
        )

    # ========================================================
    # Helpers
    # ========================================================

    @staticmethod
    def _create_document_id(
        input_result: MediaInputResult,
    ) -> str:

        content_hash = (
            input_result.metadata.content_hash
        )

        if content_hash:
            return f"media-{content_hash[:16]}"

        return f"media-{uuid4().hex}"

    # --------------------------------------------------------

    @staticmethod
    def _extract_evidence(
        extracted_data: dict[str, Any],
    ) -> list[Evidence]:

        raw_evidence = extracted_data.get(
            "evidence",
            []
        )

        result: list[Evidence] = []

        # ----------------------------------------------------
        # Explicit evidence
        # ----------------------------------------------------

        if isinstance(raw_evidence, list):

            for item in raw_evidence:

                if isinstance(item, Evidence):
                    result.append(item)
                    continue

                if not isinstance(item, dict):
                    continue

                try:
                    result.append(
                        Evidence.model_validate(item)
                    )
                except Exception:
                    # Invalid processor evidence should not
                    # crash normalization.
                    continue

        # ----------------------------------------------------
        # Audio / video transcript fallback
        # ----------------------------------------------------

        if not result:

            transcript = extracted_data.get(
                "transcript",
                []
            )

            if isinstance(transcript, list):

                for index, item in enumerate(
                    transcript
                ):

                    if not isinstance(item, dict):
                        continue

                    try:

                        provenance_data = item.get(
                            "provenance",
                            {}
                        )

                        evidence_item = Evidence(
                            evidence_id=(
                                item.get(
                                    "evidence_id"
                                )
                                or f"transcript-{index + 1}"
                            ),
                            content_type="text",
                            text=(
                                item.get("text")
                                or item.get("content")
                                or ""
                            ),
                            provenance=provenance_data,
                            confidence=item.get(
                                "confidence"
                            ),
                        )

                        result.append(
                            evidence_item
                        )

                    except Exception:
                        continue

        return result

    # --------------------------------------------------------

    @staticmethod
    def _extract_structured_elements(
        extracted_data: dict[str, Any],
    ) -> list[StructuredElement]:

        raw_elements = extracted_data.get(
            "elements",
            []
        )

        result: list[StructuredElement] = []

        if not isinstance(raw_elements, list):
            return result

        for index, item in enumerate(
            raw_elements
        ):

            if not isinstance(item, dict):
                continue

            try:

                result.append(
                    StructuredElement(
                        element_id=(
                            item.get("element_id")
                            or f"element-{index + 1}"
                        ),
                        type=item.get(
                            "type",
                            "text",
                        ),
                        text=item.get(
                            "text"
                        ),
                        value=item.get(
                            "value"
                        ),
                        bbox=item.get(
                            "bbox"
                        ),
                        confidence=item.get(
                            "confidence"
                        ),
                        provenance=item.get(
                            "provenance"
                        ),
                        metadata={
                            key: value
                            for key, value in item.items()
                            if key not in {
                                "element_id",
                                "type",
                                "text",
                                "value",
                                "bbox",
                                "confidence",
                                "provenance",
                            }
                        },
                    )
                )

            except Exception:
                # One malformed element should not
                # invalidate the entire normalized output.
                continue

        return result

    # --------------------------------------------------------

    @staticmethod
    def _extract_topics(
        extracted_data: dict[str, Any],
    ) -> list[dict[str, Any]]:

        topics = extracted_data.get(
            "topics",
            []
        )

        if not isinstance(topics, list):
            return []

        return [
            item
            for item in topics
            if isinstance(item, dict)
        ]

    # --------------------------------------------------------

    @staticmethod
    def _extract_summary(
        extracted_data: dict[str, Any],
    ) -> str | None:

        summary = extracted_data.get(
            "summary"
        )

        if isinstance(summary, str):
            return summary

        return None

    # --------------------------------------------------------

    @staticmethod
    def _extract_provenance(
        extracted_data: dict[str, Any],
        evidence: list[Evidence],
    ) -> list[Any]:

        """
        Collect explicit provenance from processor output.

        Evidence provenance is included automatically because
        evidence itself represents source-grounded information.
        """

        result: list[Any] = []

        raw_provenance = extracted_data.get(
            "provenance",
            []
        )

        if isinstance(raw_provenance, list):
            result.extend(raw_provenance)

        # ----------------------------------------------------
        # Evidence-derived provenance
        # ----------------------------------------------------

        for item in evidence:

            provenance = getattr(
                item,
                "provenance",
                None,
            )

            if provenance:

                if isinstance(provenance, list):
                    result.extend(provenance)
                else:
                    result.append(provenance)

        return result

    # --------------------------------------------------------

    @staticmethod
    def _build_stages(
        processing: ProcessingResult,
    ) -> list[ProcessingStage]:

        return [
            ProcessingStage(
                name="processing",
                status=processing.status.value,
                message=(
                    "Modality-specific processor "
                    "completed."
                ),
                metadata={
                    "media_type": processing.media_type,
                    "artifact_count": len(
                        processing.artifacts
                    ),
                    "warning_count": len(
                        processing.warnings
                    ),
                    "error_count": len(
                        processing.errors
                    ),
                },
            )
        ]