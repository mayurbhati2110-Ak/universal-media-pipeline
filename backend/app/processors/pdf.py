from pathlib import Path

import fitz

from app.core.config import settings
from app.extractors.ocr import OCRExtractionError, OCRExtractor
from app.models.media import MediaType
from app.models.processing import (
    ArtifactType,
    ProcessingError,
    ProcessingResult,
    ProcessingStatus,
    ProcessingArtifact,
)
from app.models.provenance import Evidence, Provenance
from app.processors.base import BaseMediaProcessor


class PDFProcessor(BaseMediaProcessor):
    """
    Processes PDF documents.

    Responsibilities:
    - Verify the PDF can be opened.
    - Count pages.
    - Extract document metadata.
    - Extract native PDF text.
    - Detect scanned/image-only pages.
    - Render scanned pages.
    - Run OCR on scanned pages.
    - Extract embedded images.
    - Preserve page-level provenance.
    - Preserve image-level provenance.
    - Return standardized processing output.
    """

    media_type = MediaType.PDF

    def __init__(
        self,
        ocr_extractor: OCRExtractor | None = None,
    ):
        self.ocr_extractor = ocr_extractor

    def process(
        self,
        file_path: Path,
    ) -> ProcessingResult:

        # ---------------------------------------------------------
        # 1. Validate file
        # ---------------------------------------------------------

        if not file_path.exists():
            return self._failure(
                file_path=file_path,
                code="FILE_NOT_FOUND",
                message="PDF file does not exist.",
            )

        if not file_path.is_file():
            return self._failure(
                file_path=file_path,
                code="NOT_A_FILE",
                message="PDF path is not a regular file.",
            )

        document = None

        try:
            # -----------------------------------------------------
            # 2. Open PDF
            # -----------------------------------------------------

            document = fitz.open(str(file_path))

            if document.is_closed:
                return self._failure(
                    file_path=file_path,
                    code="PDF_NOT_READABLE",
                    message="PDF could not be opened.",
                )

            page_count = document.page_count

            if page_count == 0:
                return self._failure(
                    file_path=file_path,
                    code="EMPTY_PDF",
                    message="PDF contains no pages.",
                )

            document_metadata = document.metadata or {}

            text_pages = 0
            scanned_pages = 0
            image_pages = 0

            evidence: list[Evidence] = []
            image_artifacts: list[ProcessingArtifact] = []
            page_summaries: list[dict] = []

            # -----------------------------------------------------
            # 3. Inspect every page
            # -----------------------------------------------------

            for page_number, page in enumerate(
                document,
                start=1,
            ):

                native_text = page.get_text(
                    "text"
                ).strip()

                images = page.get_images(
                    full=True
                )

                if images:
                    image_pages += 1

                # Track page-level information.
                page_summary = {
                    "page": page_number,
                    "has_native_text": bool(native_text),
                    "scanned": False,
                    "embedded_image_count": len(images),
                }

                # -------------------------------------------------
                # 4. Extract embedded images
                # -------------------------------------------------

                for image_index, image_info in enumerate(
                    images,
                    start=1,
                ):

                    try:
                        xref = image_info[0]

                        extracted_image = (
                            document.extract_image(
                                xref
                            )
                        )

                        image_bytes = (
                            extracted_image.get(
                                "image"
                            )
                        )

                        extension = (
                            extracted_image.get(
                                "ext"
                            )
                            or "bin"
                        )

                        width = extracted_image.get(
                            "width"
                        )

                        height = extracted_image.get(
                            "height"
                        )

                        colorspace = (
                            extracted_image.get(
                                "cs-name"
                            )
                        )

                        if not image_bytes:
                            continue

                        image_filename = (
                            f"{file_path.stem}"
                            f"_page_{page_number}"
                            f"_image_{image_index}"
                            f".{extension}"
                        )

                        image_dir = (
                            file_path.parent
                            / "pdf_images"
                        )

                        image_dir.mkdir(
                            exist_ok=True
                        )

                        image_path = (
                            image_dir
                            / image_filename
                        )

                        image_path.write_bytes(
                            image_bytes
                        )

                        image_size = len(
                            image_bytes
                        )

                        image_artifacts.append(
                            ProcessingArtifact(
                                artifact_id=(
                                    f"{file_path.stem}"
                                    f"-p{page_number}"
                                    f"-img{image_index}"
                                ),
                                artifact_type=(
                                    ArtifactType.IMAGE
                                ),
                                file_path=str(
                                    image_path
                                ),
                                mime_type=(
                                    self._image_mime_type(
                                        extension
                                    )
                                ),
                                size_bytes=image_size,
                                metadata={
                                    "page": page_number,
                                    "image_index": (
                                        image_index
                                    ),
                                    "xref": xref,
                                    "width": width,
                                    "height": height,
                                    "extension": extension,
                                    "colorspace": (
                                        colorspace
                                    ),
                                    "source_pdf": (
                                        file_path.name
                                    ),
                                    "extraction_method": (
                                        "pymupdf_embedded_image"
                                    ),
                                },
                            )
                        )

                    except (
                        RuntimeError,
                        OSError,
                        ValueError,
                    ):
                        # One bad embedded image should not
                        # fail the complete PDF.
                        continue

                # -------------------------------------------------
                # Native text page
                # -------------------------------------------------

                if native_text:

                    text_pages += 1

                    evidence.append(
                        Evidence(
                            evidence_id=(
                                f"pdf-page-{page_number}"
                            ),
                            content_type="text",
                            text=native_text,
                            provenance=Provenance(
                                source_type="pdf",
                                source_artifact=(
                                    file_path.name
                                ),
                                page=page_number,
                                extraction_method=(
                                    "pymupdf_text"
                                ),
                            ),
                        )
                    )

                    page_summaries.append(
                        page_summary
                    )

                    continue

                # -------------------------------------------------
                # Scanned/image-only page
                # -------------------------------------------------

                scanned_pages += 1

                page_summary["scanned"] = True

                try:
                    # Render PDF page to an image.
                    pixmap = page.get_pixmap(
                        matrix=fitz.Matrix(
                            2,
                            2,
                        ),
                        alpha=False,
                    )

                    page_image = pixmap.tobytes(
                        "png"
                    )

                    # Save temporary rendered page.
                    temp_dir = (
                        file_path.parent
                        / ".pdf_ocr_temp"
                    )

                    temp_dir.mkdir(
                        exist_ok=True
                    )

                    rendered_path = (
                        temp_dir
                        / (
                            f"{file_path.stem}"
                            f"_page_{page_number}.png"
                        )
                    )

                    rendered_path.write_bytes(
                        page_image
                    )

                    # ---------------------------------------------
                    # Run OCR
                    # ---------------------------------------------

                    ocr_extractor = (
                        self.ocr_extractor
                    )

                    if ocr_extractor is None:
                        ocr_extractor = OCRExtractor(
                            tesseract_cmd=(
                                settings.TESSERACT_CMD
                            )
                        )

                    page_evidence = (
                        ocr_extractor.extract(
                            rendered_path,
                            source_type="pdf",
                            source_artifact=(
                                file_path.name
                            ),
                            page=page_number,
                        )
                    )

                    evidence.extend(
                        page_evidence
                    )

                    # ---------------------------------------------
                    # Cleanup rendered image
                    # ---------------------------------------------

                    try:
                        rendered_path.unlink()
                    except OSError:
                        pass

                except (
                    OCRExtractionError,
                    OSError,
                    RuntimeError,
                ):
                    # OCR failure should not destroy the
                    # rest of the PDF result.
                    pass

                page_summaries.append(
                    page_summary
                )

        except (
            fitz.FileDataError,
            RuntimeError,
            OSError,
        ) as exc:

            return self._failure(
                file_path=file_path,
                code="PDF_READ_ERROR",
                message=f"Unable to read PDF: {exc}",
            )

        finally:
            if document is not None:
                document.close()

        # ---------------------------------------------------------
        # 5. File information
        # ---------------------------------------------------------

        try:
            size_bytes = file_path.stat().st_size

        except OSError:
            size_bytes = 0

        # ---------------------------------------------------------
        # 6. Original PDF artifact
        # ---------------------------------------------------------

        pdf_artifact = ProcessingArtifact(
            artifact_id=file_path.stem,
            artifact_type=ArtifactType.PDF,
            file_path=str(file_path),
            mime_type="application/pdf",
            size_bytes=size_bytes,
            metadata={
                "page_count": page_count,
                "text_pages": text_pages,
                "scanned_pages": scanned_pages,
                "image_pages": image_pages,
                "embedded_image_count": (
                    len(image_artifacts)
                ),
                "title": document_metadata.get(
                    "title"
                ),
                "author": document_metadata.get(
                    "author"
                ),
                "subject": document_metadata.get(
                    "subject"
                ),
            },
        )

        # ---------------------------------------------------------
        # 7. Warnings
        # ---------------------------------------------------------

        warnings: list[str] = []

        if scanned_pages > 0:
            warnings.append(
                f"{scanned_pages} page(s) were processed "
                "using OCR because no native text was found."
            )

        if (
            text_pages == 0
            and scanned_pages == 0
        ):
            warnings.append(
                "No extractable text was found in the PDF."
            )

        # ---------------------------------------------------------
        # 8. Final result
        # ---------------------------------------------------------

        return ProcessingResult(
            status=ProcessingStatus.SUCCESS,
            media_type=MediaType.PDF,
            artifacts=[
                pdf_artifact,
                *image_artifacts,
            ],
            extracted_data={
                "page_count": page_count,
                "text_pages": text_pages,
                "scanned_pages": scanned_pages,
                "image_pages": image_pages,
                "embedded_image_count": (
                    len(image_artifacts)
                ),
                "page_summaries": page_summaries,
                "evidence": [
                    item.model_dump()
                    for item in evidence
                ],
            },
            warnings=warnings,
            errors=[],
            metadata={
                "filename": file_path.name,
                "document_metadata": (
                    document_metadata
                ),
            },
        )

    # -------------------------------------------------------------
    # Image MIME type helper
    # -------------------------------------------------------------

    @staticmethod
    def _image_mime_type(
        extension: str | None,
    ) -> str | None:

        if not extension:
            return None

        mapping = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "jpx": "image/jp2",
            "jp2": "image/jp2",
            "webp": "image/webp",
            "bmp": "image/bmp",
            "gif": "image/gif",
            "tif": "image/tiff",
            "tiff": "image/tiff",
        }

        return mapping.get(
            extension.lower()
        )

    # -------------------------------------------------------------
    # Failure helper
    # -------------------------------------------------------------

    @staticmethod
    def _failure(
        file_path: Path,
        code: str,
        message: str,
    ) -> ProcessingResult:

        error = ProcessingError(
            stage="pdf_processing",
            code=code,
            message=message,
            recoverable=False,
        )

        return ProcessingResult(
            status=ProcessingStatus.FAILED,
            media_type=MediaType.PDF,
            errors=[error],
            metadata={
                "filename": file_path.name,
            },
        )