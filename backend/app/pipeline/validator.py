from pathlib import Path
from typing import BinaryIO, Optional

from app.core.config import settings
from app.models.media import (
    MediaType,
    ValidationResult,
    ValidationStatus,
)
from app.pipeline.detector import DetectionResult


class MediaValidator:
    """
    Validates an acquired media file before expensive processing begins.

    Validation checks:
    - File exists / can be read
    - File is not empty
    - File size is within configured limits
    - Detected media type is supported
    - Detected content is consistent enough to continue
    """

    def validate(
        self,
        file: BinaryIO,
        detection: DetectionResult,
        file_path: Optional[Path] = None,
    ) -> ValidationResult:

        errors: list[str] = []
        warnings: list[str] = []

        # ---------------------------------------------------------
        # 1. Determine file size
        # ---------------------------------------------------------

        try:
            current_position = file.tell()

            file.seek(0, 2)
            size_bytes = file.tell()

            file.seek(current_position)

        except (OSError, ValueError) as exc:
            return ValidationResult(
                status=ValidationStatus.INVALID,
                is_readable=False,
                is_supported=False,
                integrity_valid=False,
                size_valid=False,
                errors=[
                    f"Unable to determine file size: {exc}"
                ],
                warnings=[],
            )

        # ---------------------------------------------------------
        # 2. Check readability
        # ---------------------------------------------------------

        is_readable = True

        try:
            current_position = file.tell()

            file.seek(0)

            test_bytes = file.read(1)

            file.seek(current_position)

            if size_bytes > 0 and not test_bytes:
                is_readable = False
                errors.append(
                    "File exists but could not be read."
                )

        except (OSError, ValueError) as exc:
            is_readable = False

            errors.append(
                f"File is not readable: {exc}"
            )

        # ---------------------------------------------------------
        # 3. Check empty file
        # ---------------------------------------------------------

        if size_bytes == 0:
            errors.append(
                "File is empty."
            )

        # ---------------------------------------------------------
        # 4. Check maximum file size
        # ---------------------------------------------------------

        size_valid = size_bytes <= settings.max_file_size_bytes

        if not size_valid:
            errors.append(
                f"File size ({self._format_size(size_bytes)}) "
                f"exceeds the maximum allowed size "
                f"({settings.MAX_FILE_SIZE_MB} MB)."
            )

        # ---------------------------------------------------------
        # 5. Check detected media type
        # ---------------------------------------------------------

        is_supported = detection.media_type != MediaType.UNKNOWN

        if not is_supported:
            errors.append(
                "Unable to identify a supported media type."
            )

        # ---------------------------------------------------------
        # 6. Check MIME type against supported types
        # ---------------------------------------------------------

        if detection.mime_type:

            mime_supported = (
                detection.mime_type.lower()
                in settings.SUPPORTED_MIME_TYPES
            )

            if not mime_supported:
                is_supported = False

                errors.append(
                    f"Detected MIME type "
                    f"'{detection.mime_type}' "
                    f"is not supported."
                )

        # ---------------------------------------------------------
        # 7. Detection confidence warning
        # ---------------------------------------------------------

        if detection.confidence == "low":

            warnings.append(
                "Media type was determined using fallback "
                "information rather than a strong content signature."
            )

        elif detection.confidence == "medium":

            warnings.append(
                "Media type was detected with medium confidence "
                "and may require deeper container inspection."
            )

        # ---------------------------------------------------------
        # 8. Integrity
        # ---------------------------------------------------------

        integrity_valid = self._basic_integrity_check(
            file=file,
            size_bytes=size_bytes,
            detection=detection,
        )

        if not integrity_valid:
            errors.append(
                "Basic file integrity check failed."
            )

        # ---------------------------------------------------------
        # 9. Optional path validation
        # ---------------------------------------------------------

        if file_path is not None:

            if not file_path.exists():

                errors.append(
                    "Referenced file path does not exist."
                )

                is_readable = False

            elif not file_path.is_file():

                errors.append(
                    "Referenced path is not a regular file."
                )

                is_readable = False

        # ---------------------------------------------------------
        # 10. Determine final validation status
        # ---------------------------------------------------------

        if errors:

            status = ValidationStatus.INVALID

        elif warnings:

            status = ValidationStatus.PARTIAL

        else:

            status = ValidationStatus.VALID

        return ValidationResult(
            status=status,
            is_readable=is_readable,
            is_supported=is_supported,
            integrity_valid=integrity_valid,
            size_valid=size_valid,
            errors=errors,
            warnings=warnings,
        )

    @staticmethod
    def _basic_integrity_check(
        file: BinaryIO,
        size_bytes: int,
        detection: DetectionResult,
    ) -> bool:
        """
        Perform basic integrity checks.

        This is intentionally lightweight.

        Full container/codec integrity validation will later be
        performed by modality-specific tools such as FFprobe,
        image parsers, and PDF parsers.
        """

        if size_bytes <= 0:
            return False

        try:
            current_position = file.tell()

            file.seek(0)

            header = file.read(8192)

            file.seek(current_position)

        except (OSError, ValueError):
            return False

        if not header:
            return False

        # A media type was detected from actual content.
        # This means at least the expected file signature exists.
        if detection.confidence in {"high", "medium"}:
            return True

        # For fallback detection, we cannot confidently establish
        # container integrity yet.
        return False

    @staticmethod
    def _format_size(size_bytes: int) -> str:

        if size_bytes < 1024:
            return f"{size_bytes} B"

        if size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.2f} KB"

        if size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"