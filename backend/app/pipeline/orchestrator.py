from pathlib import Path
from typing import BinaryIO, Optional

from app.models.media import MediaInputResult, MediaMetadata
from app.models.processing import ProcessingResult
from app.models.provenance import Evidence
from app.schemas.normalized import ProcessingStage

from app.pipeline.acquisition import (
    AcquisitionError,
    AcquisitionResult,
    MediaAcquirer,
)
from app.pipeline.detector import MediaDetector
from app.pipeline.normalizer import NormalizedOutputBuilder
from app.pipeline.validator import MediaValidator

from app.processors.audio import AudioProcessor
from app.processors.base import BaseMediaProcessor
from app.processors.image import ImageProcessor
from app.processors.pdf import PDFProcessor
from app.processors.registry import ProcessorRegistry
from app.processors.video import VideoProcessor

from app.reasoning.topics import (
    topic_extractor,
    TopicExtractionError,
)
from app.reasoning.summarizer import (
    summarizer,
    SummarizationError,
)

from app.services.cache import MediaCache
from app.services.artifacts import artifact_manager


class MediaPipelineError(Exception):
    """Raised when a pipeline stage fails."""


class MediaPipeline:
    """
    Coordinates the universal media processing pipeline.

    Current workflow:

        Input
          ↓
        Acquire
          ↓
        Detect
          ↓
        Validate
          ↓
        Cache Check
          ↓
        Select Processor
          ↓
        Process
          ↓
        Artifact Management
          ↓
        AI Reasoning (optional)
          ↓
        Normalize
          ↓
        Cache Result
          ↓
        Return
    """

    def __init__(
        self,
        acquirer: Optional[MediaAcquirer] = None,
        detector: Optional[MediaDetector] = None,
        validator: Optional[MediaValidator] = None,
        registry: Optional[ProcessorRegistry] = None,
    ) -> None:

        self.acquirer = (
            acquirer
            or MediaAcquirer()
        )

        self.detector = (
            detector
            or MediaDetector()
        )

        self.validator = (
            validator
            or MediaValidator()
        )

        self.registry = (
            registry
            or self._create_default_registry()
        )

        # -----------------------------------------------------
        # Content-based cache
        # -----------------------------------------------------

        self.cache = MediaCache(
            Path("storage/cache")
        )

    # ---------------------------------------------------------
    # Default processor registry
    # ---------------------------------------------------------

    @staticmethod
    def _create_default_registry() -> ProcessorRegistry:

        registry = ProcessorRegistry()

        registry.register(
            ImageProcessor()
        )

        registry.register(
            PDFProcessor()
        )

        registry.register(
            AudioProcessor()
        )

        registry.register(
            VideoProcessor()
        )

        return registry

    # ---------------------------------------------------------
    # Upload pipeline
    # ---------------------------------------------------------

    def process_upload(
        self,
        file: BinaryIO,
        filename: Optional[str] = None,
        declared_mime_type: Optional[str] = None,
    ) -> MediaInputResult:

        try:

            acquisition = (
                self.acquirer.acquire_upload(
                    file=file,
                    filename=filename,
                    declared_mime_type=declared_mime_type,
                )
            )

        except AcquisitionError as exc:

            raise MediaPipelineError(
                f"Acquisition failed: {exc}"
            ) from exc

        return self._process_acquired_media(
            acquisition
        )

    # ---------------------------------------------------------
    # URL pipeline
    # ---------------------------------------------------------

    def process_url(
        self,
        url: str,
    ) -> MediaInputResult:

        try:

            acquisition = (
                self.acquirer.acquire_url(
                    url=url
                )
            )

        except AcquisitionError as exc:

            raise MediaPipelineError(
                f"Acquisition failed: {exc}"
            ) from exc

        return self._process_acquired_media(
            acquisition
        )

    # ---------------------------------------------------------
    # Detect → Validate → Cache → Process
    # → Artifacts → Reason → Normalize
    # ---------------------------------------------------------

    def _process_acquired_media(
        self,
        acquisition: AcquisitionResult,
    ) -> MediaInputResult:

        # -----------------------------------------------------
        # Detect + Validate
        # -----------------------------------------------------

        try:

            with acquisition.file_path.open(
                "rb"
            ) as media_file:

                detection = (
                    self.detector.detect(
                        file=media_file,
                        filename=acquisition.filename,
                        declared_mime_type=(
                            acquisition.declared_mime_type
                        ),
                    )
                )

                validation = (
                    self.validator.validate(
                        file=media_file,
                        detection=detection,
                        file_path=(
                            acquisition.file_path
                        ),
                    )
                )

        except OSError as exc:

            raise MediaPipelineError(
                f"Unable to inspect acquired media: {exc}"
            ) from exc

        # -----------------------------------------------------
        # Build universal metadata
        # -----------------------------------------------------

        metadata = MediaMetadata(
            filename=(
                acquisition.file_path.name
            ),
            original_filename=(
                acquisition.filename
            ),
            media_type=detection.media_type,
            mime_type=detection.mime_type,
            detected_format=(
                detection.detected_format
            ),
            size_bytes=(
                acquisition.size_bytes
            ),
            content_hash=(
                acquisition.content_hash
            ),
        )

        # -----------------------------------------------------
        # Stop before processor if media is unreadable
        # -----------------------------------------------------

        if not validation.is_readable:

            return MediaInputResult(
                source_type=acquisition.source_type,
                source=acquisition.source,
                metadata=metadata,
                validation=validation,
                acquired=True,
                detected=True,
                processing=None,
                normalized=None,
            )

        # -----------------------------------------------------
        # Stop before processor if media type unsupported
        # -----------------------------------------------------

        if not validation.is_supported:

            return MediaInputResult(
                source_type=acquisition.source_type,
                source=acquisition.source,
                metadata=metadata,
                validation=validation,
                acquired=True,
                detected=True,
                processing=None,
                normalized=None,
            )

        # -----------------------------------------------------
        # Cache lookup
        # -----------------------------------------------------

        cached_document = self.cache.get(
            acquisition.content_hash
        )

        if cached_document is not None:

            cached_document = (
                cached_document.model_copy(
                    deep=True
                )
            )

            cached_document.processing.cache_hit = True

            cached_document.processing.stages.append(
                ProcessingStage(
                    name="cache",
                    status="cached",
                    message=(
                        "Previously processed content "
                        "was reused from the SHA-256 cache."
                    ),
                    metadata={
                        "content_hash": (
                            acquisition.content_hash
                        )
                    },
                )
            )

            return MediaInputResult(
                source_type=acquisition.source_type,
                source=acquisition.source,
                metadata=metadata,
                validation=validation,
                acquired=True,
                detected=True,
                processing=None,
                pipeline_metadata={
                    "cache_hit": True,
                    "cache_key": (
                        acquisition.content_hash
                    ),
                },
                normalized=cached_document,
            )

        # -----------------------------------------------------
        # Select processor
        # -----------------------------------------------------

        processor = self.registry.get(
            detection.media_type
        )

        if processor is None:

            validation.errors.append(
                "No processor is registered for "
                f"media type "
                f"'{detection.media_type.value}'."
            )

            return MediaInputResult(
                source_type=acquisition.source_type,
                source=acquisition.source,
                metadata=metadata,
                validation=validation,
                acquired=True,
                detected=True,
                processing=None,
                normalized=None,
            )

        # -----------------------------------------------------
        # Process media
        # -----------------------------------------------------

        try:

            processing_result = (
                processor.process(
                    acquisition.file_path
                )
            )

        except Exception as exc:

            raise MediaPipelineError(
                "Media processing failed: "
                f"{exc}"
            ) from exc

        # -----------------------------------------------------
        # Artifact management
        #
        # Processor-generated artifacts are copied into:
        #
        # storage/artifacts/<document_id>/
        #
        # The acquired source file itself is not copied again.
        # -----------------------------------------------------

        document_id = (
            f"media-{acquisition.content_hash[:16]}"
            if acquisition.content_hash
            else f"media-{acquisition.file_path.stem}"
        )

        managed_artifact_paths = []

        for artifact in processing_result.artifacts:

            if not artifact.file_path:
                continue

            artifact_path = Path(
                artifact.file_path
            )

            # Skip missing artifacts gracefully.
            if not artifact_path.exists():
                processing_result.warnings.append(
                    "Artifact file was reported by the "
                    f"processor but was not found: "
                    f"{artifact_path}"
                )
                continue

            try:

                managed_artifact = (
                    artifact_manager.store(
                        document_id=document_id,
                        source_path=artifact_path,
                        artifact_type=artifact.artifact_type,
                        filename=artifact_path.name,
                        mime_type=artifact.mime_type,
                        metadata=artifact.metadata,
                    )
                )

                managed_artifact_paths.append(
                    managed_artifact
                )

            except Exception as exc:

                processing_result.warnings.append(
                    "Artifact management failed for "
                    f"'{artifact_path.name}': {exc}"
                )

        # Replace processor paths with managed artifact paths
        # only when at least one artifact was successfully stored.
        if managed_artifact_paths:

            processing_result.artifacts = (
                managed_artifact_paths
            )

        # -----------------------------------------------------
        # Propagate processor metadata
        # -----------------------------------------------------

        metadata.filename = (
            acquisition.file_path.name
        )

        if processing_result.artifacts:

            processor_metadata = (
                processing_result
                .artifacts[0]
                .metadata
            )

            if "page_count" in processor_metadata:

                metadata.page_count = (
                    processor_metadata.get(
                        "page_count"
                    )
                )

            if "width" in processor_metadata:

                metadata.width = (
                    processor_metadata.get(
                        "width"
                    )
                )

            if "height" in processor_metadata:

                metadata.height = (
                    processor_metadata.get(
                        "height"
                    )
                )

            if "duration_seconds" in processor_metadata:

                metadata.duration_seconds = (
                    processor_metadata.get(
                        "duration_seconds"
                    )
                )

        # -----------------------------------------------------
        # Build pipeline result
        # -----------------------------------------------------

        result = MediaInputResult(
            source_type=acquisition.source_type,
            source=acquisition.source,
            metadata=metadata,
            validation=validation,
            acquired=True,
            detected=True,
            processing=processing_result,
            normalized=None,
        )

        # -----------------------------------------------------
        # Optional AI reasoning
        # -----------------------------------------------------

        extracted_data = (
            processing_result.extracted_data
            or {}
        )

        evidence = extracted_data.get(
            "evidence",
            []
        )

        if isinstance(evidence, list) and evidence:

            evidence_for_reasoning = [
                item.model_dump()
                if hasattr(item, "model_dump")
                else item
                for item in evidence
                if isinstance(
                    item,
                    (dict, Evidence)
                )
            ]

            # -------------------------------------------------
            # Topic extraction
            # -------------------------------------------------

            try:

                topic_response = (
                    topic_extractor.extract(
                        evidence_for_reasoning
                    )
                )

                extracted_data["topics"] = [
                    topic.model_dump()
                    for topic in topic_response.topics
                ]

            except TopicExtractionError as exc:

                processing_result.warnings.append(
                    f"Topic reasoning unavailable: {exc}"
                )

            # -------------------------------------------------
            # Summary generation
            # -------------------------------------------------

            try:

                summary_response = (
                    summarizer.summarize(
                        evidence_for_reasoning
                    )
                )

                extracted_data["summary"] = (
                    summary_response.summary
                )

            except SummarizationError as exc:

                processing_result.warnings.append(
                    f"Summary reasoning unavailable: {exc}"
                )

        processing_result.extracted_data = (
            extracted_data
        )

        # -----------------------------------------------------
        # Normalize output
        # -----------------------------------------------------

        try:

            result.normalized = (
                NormalizedOutputBuilder.build(
                    result
                )
            )

        except Exception as exc:

            raise MediaPipelineError(
                "Output normalization failed: "
                f"{exc}"
            ) from exc

        # -----------------------------------------------------
        # Store normalized result in cache
        # -----------------------------------------------------

        if result.normalized is not None:

            try:

                self.cache.set(
                    acquisition.content_hash,
                    result.normalized,
                )

            except Exception:
                pass

        # -----------------------------------------------------
        # Return complete universal result
        # -----------------------------------------------------

        return result

    # ---------------------------------------------------------
    # Direct processor access
    # ---------------------------------------------------------

    def get_processor(
        self,
        media_type,
    ) -> BaseMediaProcessor:

        try:

            return self.registry.require(
                media_type
            )

        except LookupError as exc:

            raise MediaPipelineError(
                str(exc)
            ) from exc

    # ---------------------------------------------------------
    # Processing helper
    # ---------------------------------------------------------

    @staticmethod
    def process_with_processor(
        processor: BaseMediaProcessor,
        file_path: Path,
    ) -> ProcessingResult:

        return processor.process(
            file_path
        )

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    @staticmethod
    def cleanup(
        result: MediaInputResult,
    ) -> None:

        if not result.metadata.filename:
            return

        path = (
            Path("storage/temp")
            / result.metadata.filename
        )

        try:

            if path.exists():
                path.unlink()

        except OSError:
            pass