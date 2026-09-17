import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

import mimetypes

from app.models.media import MediaType


@dataclass
class DetectionResult:
    media_type: MediaType
    mime_type: Optional[str]
    detected_format: Optional[str]
    confidence: str


class MediaDetector:
    """
    Detects the actual media type from file content.

    The filename extension and user-provided MIME type are treated
    only as supporting information and are never trusted as the
    primary source of truth.
    """

    def detect(
        self,
        file: BinaryIO,
        filename: Optional[str] = None,
        declared_mime_type: Optional[str] = None,
    ) -> DetectionResult:

        # Read a small portion of the file for signature detection.
        current_position = file.tell()

        header = file.read(8192)

        # Restore original file position.
        file.seek(current_position)

        if not header:
            return DetectionResult(
                media_type=MediaType.UNKNOWN,
                mime_type=None,
                detected_format=None,
                confidence="none",
            )

        # ---------------------------------------------------------
        # PDF
        # ---------------------------------------------------------
        if header.startswith(b"%PDF-"):
            return DetectionResult(
                media_type=MediaType.PDF,
                mime_type="application/pdf",
                detected_format="pdf",
                confidence="high",
            )

        # ---------------------------------------------------------
        # JPEG
        # ---------------------------------------------------------
        if header.startswith(b"\xff\xd8\xff"):
            return DetectionResult(
                media_type=MediaType.IMAGE,
                mime_type="image/jpeg",
                detected_format="jpeg",
                confidence="high",
            )

        # ---------------------------------------------------------
        # PNG
        # ---------------------------------------------------------
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return DetectionResult(
                media_type=MediaType.IMAGE,
                mime_type="image/png",
                detected_format="png",
                confidence="high",
            )

        # ---------------------------------------------------------
        # GIF
        # ---------------------------------------------------------
        if header.startswith((b"GIF87a", b"GIF89a")):
            return DetectionResult(
                media_type=MediaType.IMAGE,
                mime_type="image/gif",
                detected_format="gif",
                confidence="high",
            )

        # ---------------------------------------------------------
        # WEBP
        # RIFF....WEBP
        # ---------------------------------------------------------
        if (
            len(header) >= 12
            and header[0:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        ):
            return DetectionResult(
                media_type=MediaType.IMAGE,
                mime_type="image/webp",
                detected_format="webp",
                confidence="high",
            )

        # ---------------------------------------------------------
        # WAV
        # RIFF....WAVE
        # ---------------------------------------------------------
        if (
            len(header) >= 12
            and header[0:4] == b"RIFF"
            and header[8:12] == b"WAVE"
        ):
            return DetectionResult(
                media_type=MediaType.AUDIO,
                mime_type="audio/wav",
                detected_format="wav",
                confidence="high",
            )

        # ---------------------------------------------------------
        # FLAC
        # ---------------------------------------------------------
        if header.startswith(b"fLaC"):
            return DetectionResult(
                media_type=MediaType.AUDIO,
                mime_type="audio/flac",
                detected_format="flac",
                confidence="high",
            )

        # ---------------------------------------------------------
        # OGG
        # ---------------------------------------------------------
        if header.startswith(b"OggS"):
            return DetectionResult(
                media_type=MediaType.AUDIO,
                mime_type="audio/ogg",
                detected_format="ogg",
                confidence="high",
            )

        # ---------------------------------------------------------
        # MP3
        # ---------------------------------------------------------
        if header.startswith(b"ID3") or self._looks_like_mp3(header):
            return DetectionResult(
                media_type=MediaType.AUDIO,
                mime_type="audio/mpeg",
                detected_format="mp3",
                confidence="high",
            )

        # ---------------------------------------------------------
        # MP4 / MOV / QuickTime
        # ---------------------------------------------------------
        if self._is_iso_base_media(header):
            detected_format = self._detect_iso_base_format(header)

            if detected_format == "mp4":
                return DetectionResult(
                    media_type=MediaType.VIDEO,
                    mime_type="video/mp4",
                    detected_format="mp4",
                    confidence="high",
                )

            if detected_format == "mov":
                return DetectionResult(
                    media_type=MediaType.VIDEO,
                    mime_type="video/quicktime",
                    detected_format="mov",
                    confidence="high",
                )

            return DetectionResult(
                media_type=MediaType.VIDEO,
                mime_type="video/mp4",
                detected_format="iso-base-media",
                confidence="medium",
            )

        # ---------------------------------------------------------
        # AVI
        # RIFF....AVI
        # ---------------------------------------------------------
        if (
            len(header) >= 12
            and header[0:4] == b"RIFF"
            and header[8:12] == b"AVI "
        ):
            return DetectionResult(
                media_type=MediaType.VIDEO,
                mime_type="video/x-msvideo",
                detected_format="avi",
                confidence="high",
            )

        # ---------------------------------------------------------
        # WebM / Matroska
        # EBML signature
        # ---------------------------------------------------------
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            # WebM and Matroska share the EBML container signature.
            # Detailed distinction can be performed later with FFprobe.
            return DetectionResult(
                media_type=MediaType.VIDEO,
                mime_type="video/webm",
                detected_format="webm/matroska",
                confidence="medium",
            )

        # ---------------------------------------------------------
        # Content could not be identified
        # ---------------------------------------------------------
        return self._fallback_detection(
            filename=filename,
            declared_mime_type=declared_mime_type,
        )

    @staticmethod
    def _looks_like_mp3(header: bytes) -> bool:
        """
        Detect common MPEG audio frame signatures.

        This is intentionally conservative because not every file
        beginning with FF bytes is necessarily MP3.
        """

        if len(header) < 2:
            return False

        first = header[0]
        second = header[1]

        # MPEG audio frame sync:
        # 11111111 followed by 111xxxxx
        return first == 0xFF and (second & 0xE0) == 0xE0

    @staticmethod
    def _is_iso_base_media(header: bytes) -> bool:
        """
        Detect ISO Base Media containers such as MP4 and MOV.

        The 'ftyp' box normally starts at byte offset 4.
        """

        return len(header) >= 12 and header[4:8] == b"ftyp"

    @staticmethod
    def _detect_iso_base_format(header: bytes) -> Optional[str]:
        """
        Inspect the major brand of an ISO Base Media file.
        """

        if len(header) < 12:
            return None

        major_brand = header[8:12].decode(
            "ascii",
            errors="ignore",
        ).lower()

        mp4_brands = {
            "isom",
            "iso2",
            "iso3",
            "iso4",
            "iso5",
            "iso6",
            "mp41",
            "mp42",
            "avc1",
            "mp71",
            "mmp4",
        }

        mov_brands = {
            "qt  ",
        }

        if major_brand in mp4_brands:
            return "mp4"

        if major_brand in mov_brands:
            return "mov"

        # Some valid MP4 files use brands we don't explicitly list.
        if major_brand.startswith("mp4"):
            return "mp4"

        return "iso-base-media"

    def _fallback_detection(
        self,
        filename: Optional[str],
        declared_mime_type: Optional[str],
    ) -> DetectionResult:
        """
        Filename and declared MIME type may be used only as fallback
        hints when content signatures cannot identify the file.

        The confidence is deliberately low.
        """

        # First consider a declared MIME type.
        if declared_mime_type:
            media_type = self._media_type_from_mime(declared_mime_type)

            if media_type != MediaType.UNKNOWN:
                return DetectionResult(
                    media_type=media_type,
                    mime_type=declared_mime_type,
                    detected_format=None,
                    confidence="low",
                )

        # Then consider the filename extension.
        if filename:
            guessed_mime, _ = mimetypes.guess_type(filename)

            if guessed_mime:
                media_type = self._media_type_from_mime(guessed_mime)

                if media_type != MediaType.UNKNOWN:
                    return DetectionResult(
                        media_type=media_type,
                        mime_type=guessed_mime,
                        detected_format=Path(filename).suffix.lower().lstrip("."),
                        confidence="low",
                    )

        return DetectionResult(
            media_type=MediaType.UNKNOWN,
            mime_type=None,
            detected_format=None,
            confidence="none",
        )

    @staticmethod
    def _media_type_from_mime(mime_type: str) -> MediaType:
        mime_type = mime_type.lower().strip()

        if mime_type == "application/pdf":
            return MediaType.PDF

        if mime_type.startswith("video/"):
            return MediaType.VIDEO

        if mime_type.startswith("audio/"):
            return MediaType.AUDIO

        if mime_type.startswith("image/"):
            return MediaType.IMAGE

        return MediaType.UNKNOWN