from pathlib import Path
import subprocess
import json

from app.core.config import settings
from app.extractors.transcription import (
    TranscriptionError,
    TranscriptionExtractor,
)
from app.models.media import MediaType
from app.models.processing import (
    ArtifactType,
    ProcessingArtifact,
    ProcessingError,
    ProcessingResult,
    ProcessingStatus,
)
from app.processors.base import BaseMediaProcessor


class AudioProcessor(BaseMediaProcessor):
    """
    Processes audio files using FFprobe, FFmpeg, and Whisper.

    Responsibilities:
    - Verify the audio file can be inspected.
    - Extract duration.
    - Extract sample rate.
    - Extract channel count.
    - Extract codec information.
    - Normalize audio into a standard WAV representation.
    - Transcribe normalized audio.
    - Preserve timestamped transcription evidence.
    - Return standardized processing output.
    """

    media_type = MediaType.AUDIO

    NORMALIZED_SAMPLE_RATE = 16000
    NORMALIZED_CHANNELS = 1
    NORMALIZED_CODEC = "pcm_s16le"

    WHISPER_MODEL = "base"

    def __init__(
        self,
        transcription_extractor: TranscriptionExtractor | None = None,
    ):
        self.transcription_extractor = (
            transcription_extractor
        )

    def process(
        self,
        file_path: Path,
    ) -> ProcessingResult:

        if not file_path.exists():
            return self._failure(
                file_path=file_path,
                code="FILE_NOT_FOUND",
                message="Audio file does not exist.",
            )

        if not file_path.is_file():
            return self._failure(
                file_path=file_path,
                code="NOT_A_FILE",
                message="Audio path is not a regular file.",
            )

        # =========================================================
        # 1. Probe original audio
        # =========================================================

        try:
            probe_data = self._probe(file_path)

        except RuntimeError as exc:
            return self._failure(
                file_path=file_path,
                code="AUDIO_PROBE_ERROR",
                message=str(exc),
            )

        format_data = probe_data.get(
            "format",
            {},
        )

        audio_stream = self._find_audio_stream(
            probe_data
        )

        if audio_stream is None:
            return self._failure(
                file_path=file_path,
                code="NO_AUDIO_STREAM",
                message=(
                    "No audio stream was found "
                    "in the supplied file."
                ),
            )

        duration = self._to_float(
            audio_stream.get("duration")
            or format_data.get("duration")
        )

        sample_rate = self._to_int(
            audio_stream.get("sample_rate")
        )

        channels = self._to_int(
            audio_stream.get("channels")
        )

        codec = audio_stream.get(
            "codec_name"
        )

        codec_long_name = audio_stream.get(
            "codec_long_name"
        )

        container_format = format_data.get(
            "format_name"
        )

        try:
            size_bytes = file_path.stat().st_size

        except OSError:
            size_bytes = 0

        # =========================================================
        # 2. Original artifact
        # =========================================================

        original_artifact = ProcessingArtifact(
            artifact_id=file_path.stem,
            artifact_type=ArtifactType.AUDIO,
            file_path=str(file_path),
            mime_type=self._mime_type(file_path),
            size_bytes=size_bytes,
            metadata={
                "duration_seconds": duration,
                "sample_rate": sample_rate,
                "channels": channels,
                "codec": codec,
                "codec_long_name": codec_long_name,
                "container_format": container_format,
                "normalized": False,
            },
        )

        # =========================================================
        # 3. Normalize audio
        # =========================================================

        try:
            normalized_path = self._normalize(
                file_path
            )

        except RuntimeError as exc:
            return ProcessingResult(
                status=ProcessingStatus.PARTIAL,
                media_type=MediaType.AUDIO,
                artifacts=[original_artifact],
                extracted_data={
                    "duration_seconds": duration,
                    "sample_rate": sample_rate,
                    "channels": channels,
                    "codec": codec,
                    "codec_long_name": codec_long_name,
                    "container_format": container_format,
                    "normalized": False,
                    "transcribed": False,
                },
                warnings=[
                    f"Audio normalization failed: {exc}"
                ],
                metadata={
                    "filename": file_path.name,
                },
            )

        try:
            normalized_size = (
                normalized_path.stat().st_size
            )

        except OSError:
            normalized_size = 0

        normalized_artifact = ProcessingArtifact(
            artifact_id=(
                f"{file_path.stem}-normalized"
            ),
            artifact_type=ArtifactType.NORMALIZED,
            file_path=str(normalized_path),
            mime_type="audio/wav",
            size_bytes=normalized_size,
            metadata={
                "source_audio": file_path.name,
                "sample_rate": (
                    self.NORMALIZED_SAMPLE_RATE
                ),
                "channels": (
                    self.NORMALIZED_CHANNELS
                ),
                "codec": self.NORMALIZED_CODEC,
                "format": "wav",
                "normalized": True,
                "normalization_method": "ffmpeg",
            },
        )

        # =========================================================
        # 4. Transcription
        # =========================================================

        extracted_data = {
            "duration_seconds": duration,
            "sample_rate": sample_rate,
            "channels": channels,
            "codec": codec,
            "codec_long_name": codec_long_name,
            "container_format": container_format,
            "normalized": True,
            "normalized_sample_rate": (
                self.NORMALIZED_SAMPLE_RATE
            ),
            "normalized_channels": (
                self.NORMALIZED_CHANNELS
            ),
            "normalized_codec": (
                self.NORMALIZED_CODEC
            ),
            "normalized_format": "wav",
            "transcribed": False,
            "transcript": [],
        }

        warnings: list[str] = []

        try:
            transcription_extractor = (
                self.transcription_extractor
            )

            if transcription_extractor is None:
                transcription_extractor = (
                    TranscriptionExtractor(
                        model_name=self.WHISPER_MODEL
                    )
                )

            evidence = (
                transcription_extractor.extract(
                    normalized_path,
                    source_type="audio",
                    source_artifact=(
                        normalized_path.name
                    ),
                )
            )

            extracted_data["transcript"] = [
                item.model_dump()
                for item in evidence
            ]

            extracted_data["transcribed"] = True

        except TranscriptionError as exc:
            warnings.append(
                f"Audio transcription failed: {exc}"
            )

        # =========================================================
        # 5. Final result
        # =========================================================

        status = (
            ProcessingStatus.SUCCESS
            if extracted_data["transcribed"]
            else ProcessingStatus.PARTIAL
        )

        return ProcessingResult(
            status=status,
            media_type=MediaType.AUDIO,
            artifacts=[
                original_artifact,
                normalized_artifact,
            ],
            extracted_data=extracted_data,
            warnings=warnings,
            errors=[],
            metadata={
                "filename": file_path.name,
                "transcription_model": (
                    self.WHISPER_MODEL
                ),
                "transcript_segments": len(
                    extracted_data["transcript"]
                ),
            },
        )

    # =========================================================
    # FFprobe
    # =========================================================

    @staticmethod
    def _probe(
        file_path: Path,
    ) -> dict:

        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(file_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFprobe was not found. "
                "Install FFmpeg and ensure ffprobe "
                "is available in PATH."
            ) from exc

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "FFprobe timed out while inspecting "
                "the audio file."
            ) from exc

        if result.returncode != 0:
            error_message = (
                result.stderr.strip()
                or "Unknown FFprobe error."
            )

            raise RuntimeError(
                f"FFprobe failed: {error_message}"
            )

        try:
            return json.loads(
                result.stdout
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "FFprobe returned invalid JSON."
            ) from exc

    # =========================================================
    # FFmpeg normalization
    # =========================================================

    @staticmethod
    def _normalize(
        file_path: Path,
    ) -> Path:

        normalized_dir = (
            file_path.parent
            / "normalized_audio"
        )

        normalized_dir.mkdir(
            exist_ok=True
        )

        normalized_path = (
            normalized_dir
            / f"{file_path.stem}_normalized.wav"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(normalized_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg was not found. "
                "Install FFmpeg and ensure ffmpeg "
                "is available in PATH."
            ) from exc

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "FFmpeg timed out while normalizing "
                "the audio file."
            ) from exc

        if result.returncode != 0:
            error_message = (
                result.stderr.strip()
                or "Unknown FFmpeg error."
            )

            raise RuntimeError(
                "FFmpeg normalization failed: "
                f"{error_message}"
            )

        if not normalized_path.exists():
            raise RuntimeError(
                "FFmpeg completed but the normalized "
                "audio file was not created."
            )

        return normalized_path

    # =========================================================
    # Stream helpers
    # =========================================================

    @staticmethod
    def _find_audio_stream(
        probe_data: dict,
    ) -> dict | None:

        streams = probe_data.get(
            "streams",
            [],
        )

        for stream in streams:

            if stream.get(
                "codec_type"
            ) == "audio":

                return stream

        return None

    @staticmethod
    def _to_float(
        value,
    ) -> float | None:

        if value is None:
            return None

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _to_int(
        value,
    ) -> int | None:

        if value is None:
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    # =========================================================
    # MIME helper
    # =========================================================

    @staticmethod
    def _mime_type(
        file_path: Path,
    ) -> str:

        mapping = {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
            ".opus": "audio/opus",
            ".wma": "audio/x-ms-wma",
        }

        return mapping.get(
            file_path.suffix.lower(),
            "audio/*",
        )

    # =========================================================
    # Failure helper
    # =========================================================

    @staticmethod
    def _failure(
        file_path: Path,
        code: str,
        message: str,
    ) -> ProcessingResult:

        error = ProcessingError(
            stage="audio_processing",
            code=code,
            message=message,
            recoverable=False,
        )

        return ProcessingResult(
            status=ProcessingStatus.FAILED,
            media_type=MediaType.AUDIO,
            errors=[error],
            metadata={
                "filename": file_path.name,
            },
        )