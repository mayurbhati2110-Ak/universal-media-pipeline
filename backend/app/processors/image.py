from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.extractors.ocr import OCRExtractionError, OCRExtractor
from app.models.media import MediaType
from app.models.processing import (
    ArtifactType,
    ProcessingArtifact,
    ProcessingError,
    ProcessingResult,
    ProcessingStatus,
)
from app.processors.base import BaseMediaProcessor
from app.schemas.normalized import ImageStructuredElement


class ImageProcessor(BaseMediaProcessor):
    """
    Processes image and screenshot inputs.

    Responsibilities:
    - Verify image readability.
    - Inspect image metadata.
    - Extract dimensions.
    - Identify image format and mode.
    - Run deterministic OCR when available.
    - Filter very low-confidence OCR noise from structured elements.
    - Preserve all raw OCR evidence for auditability.
    - Preserve OCR confidence and bounding-box provenance.
    - Return standardized processing output.
    """

    media_type = MediaType.IMAGE

    # Minimum OCR confidence required for structured elements.
    # Raw OCR evidence is still preserved below this threshold.
    OCR_ELEMENT_CONFIDENCE_THRESHOLD = 0.20

    def __init__(self, ocr_extractor: OCRExtractor | None = None):
        self.ocr_extractor = ocr_extractor

    def process(
        self,
        file_path: Path,
    ) -> ProcessingResult:

        # ---------------------------------------------------------
        # 1. Validate file path
        # ---------------------------------------------------------

        if not file_path.exists():
            return self._failure(
                file_path=file_path,
                code="FILE_NOT_FOUND",
                message="Image file does not exist.",
            )

        if not file_path.is_file():
            return self._failure(
                file_path=file_path,
                code="NOT_A_FILE",
                message="Image path is not a regular file.",
            )

        # ---------------------------------------------------------
        # 2. Read and validate image
        # ---------------------------------------------------------

        try:
            with Image.open(file_path) as image:

                # Force Pillow to verify that the image
                # can actually be decoded.
                image.verify()

            # Re-open after verify().
            with Image.open(file_path) as image:

                width, height = image.size
                image_format = image.format
                mode = image.mode

                frame_count = getattr(
                    image,
                    "n_frames",
                    1,
                )

        except UnidentifiedImageError:

            return self._failure(
                file_path=file_path,
                code="INVALID_IMAGE",
                message=(
                    "The file could not be identified "
                    "as a valid image."
                ),
            )

        except (
            OSError,
            ValueError,
        ) as exc:

            return self._failure(
                file_path=file_path,
                code="IMAGE_READ_ERROR",
                message=f"Unable to read image: {exc}",
            )

        # ---------------------------------------------------------
        # 3. Create image artifact
        # ---------------------------------------------------------

        try:
            size_bytes = file_path.stat().st_size

        except OSError:
            size_bytes = 0

        artifact = ProcessingArtifact(
            artifact_id=file_path.stem,
            artifact_type=ArtifactType.IMAGE,
            file_path=str(file_path),
            mime_type=self._mime_type(image_format),
            size_bytes=size_bytes,
            metadata={
                "width": width,
                "height": height,
                "format": image_format,
                "mode": mode,
                "frame_count": frame_count,
            },
        )

        # ---------------------------------------------------------
        # 4. Base normalized output
        # ---------------------------------------------------------

        extracted_data = {
            "width": width,
            "height": height,
            "format": image_format,
            "mode": mode,
            "frame_count": frame_count,
            "elements": [],
            "evidence": [],
        }

        metadata = {
            "filename": file_path.name,
            "ocr_available": False,
            "ocr_items": 0,
            "ocr_structured_items": 0,
            "ocr_filtered_items": 0,
        }

        warnings: list[str] = []
        status = ProcessingStatus.SUCCESS

        # ---------------------------------------------------------
        # 5. Deterministic OCR
        # ---------------------------------------------------------

        try:
            ocr_extractor = self.ocr_extractor

            if ocr_extractor is None:
                ocr_extractor = OCRExtractor(
                    tesseract_cmd=settings.TESSERACT_CMD
                )

            # Extract all OCR evidence.
            #
            # IMPORTANT:
            # We do not delete low-confidence OCR here.
            # Every OCR result remains available as evidence
            # with its original provenance and confidence.
            evidence = ocr_extractor.extract(file_path)

            elements = []
            filtered_count = 0

            for item in evidence:

                # Filter obvious OCR garbage from the cleaner
                # structured representation.
                #
                # The raw item remains inside `evidence`.
                if (
                    item.confidence is not None
                    and item.confidence
                    < self.OCR_ELEMENT_CONFIDENCE_THRESHOLD
                ):
                    filtered_count += 1
                    continue

                elements.append(
                    ImageStructuredElement(
                        type="text",
                        text=item.text,
                        bbox=item.provenance.bbox,
                        confidence=item.confidence,
                    )
                )

            # Clean structured OCR output.
            extracted_data["elements"] = [
                element.model_dump()
                for element in elements
            ]

            # Complete raw OCR evidence, including
            # low-confidence items.
            extracted_data["evidence"] = [
                item.model_dump()
                for item in evidence
            ]

            metadata["ocr_available"] = True
            metadata["ocr_items"] = len(evidence)
            metadata["ocr_structured_items"] = len(elements)
            metadata["ocr_filtered_items"] = filtered_count

        except OCRExtractionError as exc:

            # OCR failure should not make an otherwise valid
            # image unusable.
            status = ProcessingStatus.PARTIAL

            warnings.append(
                f"OCR extraction unavailable: {exc}"
            )

        # ---------------------------------------------------------
        # 6. Return standardized processing result
        # ---------------------------------------------------------

        return ProcessingResult(
            status=status,
            media_type=MediaType.IMAGE,
            artifacts=[artifact],
            extracted_data=extracted_data,
            warnings=warnings,
            metadata=metadata,
        )

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    @staticmethod
    def _mime_type(
        image_format: str | None,
    ) -> str | None:

        if not image_format:
            return None

        mapping = {
            "JPEG": "image/jpeg",
            "PNG": "image/png",
            "WEBP": "image/webp",
            "GIF": "image/gif",
            "BMP": "image/bmp",
            "TIFF": "image/tiff",
        }

        return mapping.get(
            image_format.upper()
        )

    @staticmethod
    def _failure(
        file_path: Path,
        code: str,
        message: str,
    ) -> ProcessingResult:

        error = ProcessingError(
            stage="image_processing",
            code=code,
            message=message,
            recoverable=False,
        )

        return ProcessingResult(
            status=ProcessingStatus.FAILED,
            media_type=MediaType.IMAGE,
            errors=[error],
            metadata={
                "filename": file_path.name,
            },
        )