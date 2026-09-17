from pathlib import Path
import json
import subprocess

from app.models.media import MediaType
from app.models.processing import (
    ArtifactType,
    ProcessingArtifact,
    ProcessingError,
    ProcessingResult,
    ProcessingStatus,
)
from app.processors.base import BaseMediaProcessor
from app.extractors.ocr import (
    OCRExtractionError,
    OCRExtractor,
)
from app.extractors.transcription import (
    TranscriptionError,
    TranscriptionExtractor,
)


class VideoProcessor(BaseMediaProcessor):
    """
    Processes video files using FFprobe and FFmpeg.

    Responsibilities:
    - Verify the video can be inspected.
    - Extract video metadata.
    - Normalize the video.
    - Extract normalized audio.
    - Transcribe extracted audio using Whisper.
    - Sample representative video frames.
    - Run OCR on sampled frames.
    - Preserve timestamp/frame/bounding-box provenance.
    - Return standardized processing output.
    """

    media_type = MediaType.VIDEO

    WHISPER_MODEL = "base"

    # Extract approximately one frame every 2 seconds.
    FRAME_INTERVAL_SECONDS = 2.0

    def process(
        self,
        file_path: Path,
    ) -> ProcessingResult:

        if not file_path.exists():
            return self._failure(
                file_path=file_path,
                code="FILE_NOT_FOUND",
                message="Video file does not exist.",
            )

        if not file_path.is_file():
            return self._failure(
                file_path=file_path,
                code="NOT_A_FILE",
                message="Video path is not a regular file.",
            )

        # -----------------------------------------------------
        # Probe original video
        # -----------------------------------------------------

        try:
            probe_data = self._probe(file_path)

        except RuntimeError as exc:
            return self._failure(
                file_path=file_path,
                code="VIDEO_PROBE_ERROR",
                message=str(exc),
            )

        format_data = probe_data.get("format", {})
        streams = probe_data.get("streams", [])

        video_stream = self._find_stream(
            streams,
            "video",
        )

        if video_stream is None:
            return self._failure(
                file_path=file_path,
                code="NO_VIDEO_STREAM",
                message=(
                    "No video stream was found "
                    "in the supplied file."
                ),
            )

        audio_stream = self._find_stream(
            streams,
            "audio",
        )

        duration = self._to_float(
            video_stream.get("duration")
            or format_data.get("duration")
        )

        width = self._to_int(
            video_stream.get("width")
        )

        height = self._to_int(
            video_stream.get("height")
        )

        frame_rate = self._parse_frame_rate(
            video_stream.get("r_frame_rate")
        )

        video_codec = video_stream.get(
            "codec_name"
        )

        video_codec_long_name = (
            video_stream.get(
                "codec_long_name"
            )
        )

        audio_present = audio_stream is not None

        audio_codec = None
        audio_codec_long_name = None
        audio_channels = None
        audio_sample_rate = None

        if audio_stream is not None:

            audio_codec = audio_stream.get(
                "codec_name"
            )

            audio_codec_long_name = (
                audio_stream.get(
                    "codec_long_name"
                )
            )

            audio_channels = self._to_int(
                audio_stream.get("channels")
            )

            audio_sample_rate = self._to_int(
                audio_stream.get("sample_rate")
            )

        container_format = format_data.get(
            "format_name"
        )

        try:
            size_bytes = file_path.stat().st_size

        except OSError:
            size_bytes = 0

        # -----------------------------------------------------
        # Original video artifact
        # -----------------------------------------------------

        artifacts = [
            ProcessingArtifact(
                artifact_id=file_path.stem,
                artifact_type=ArtifactType.VIDEO,
                file_path=str(file_path),
                mime_type="video/*",
                size_bytes=size_bytes,
                metadata={
                    "duration_seconds": duration,
                    "width": width,
                    "height": height,
                    "frame_rate": frame_rate,
                    "video_codec": video_codec,
                    "video_codec_long_name": (
                        video_codec_long_name
                    ),
                    "audio_present": audio_present,
                    "audio_codec": audio_codec,
                    "audio_codec_long_name": (
                        audio_codec_long_name
                    ),
                    "audio_channels": audio_channels,
                    "audio_sample_rate": audio_sample_rate,
                    "container_format": container_format,
                    "normalized": False,
                },
            )
        ]

        # -----------------------------------------------------
        # Normalize video
        # -----------------------------------------------------

        try:
            normalized_path = self._normalize_video(
                file_path
            )

        except RuntimeError as exc:
            return ProcessingResult(
                status=ProcessingStatus.PARTIAL,
                media_type=MediaType.VIDEO,
                artifacts=artifacts,
                extracted_data={
                    "duration_seconds": duration,
                    "width": width,
                    "height": height,
                    "frame_rate": frame_rate,
                    "video_codec": video_codec,
                    "audio_present": audio_present,
                    "audio_codec": audio_codec,
                    "audio_channels": audio_channels,
                    "audio_sample_rate": audio_sample_rate,
                    "container_format": container_format,
                    "normalized": False,
                    "transcribed": False,
                    "frames_extracted": 0,
                    "frame_ocr_available": False,
                },
                warnings=[
                    f"Video normalization failed: {exc}"
                ],
                metadata={
                    "filename": file_path.name,
                },
            )

        # -----------------------------------------------------
        # Normalized video artifact
        # -----------------------------------------------------

        normalized_size = 0

        try:
            normalized_size = (
                normalized_path.stat().st_size
            )
        except OSError:
            pass

        normalized_artifact = ProcessingArtifact(
            artifact_id=(
                f"{file_path.stem}-normalized"
            ),
            artifact_type=ArtifactType.NORMALIZED,
            file_path=str(normalized_path),
            mime_type="video/mp4",
            size_bytes=normalized_size,
            metadata={
                "source_video": file_path.name,
                "format": "mp4",
                "video_codec": "h264",
                "audio_codec": "aac",
                "normalized": True,
                "normalization_method": "ffmpeg",
            },
        )

        artifacts.append(
            normalized_artifact
        )

        # -----------------------------------------------------
        # Extract audio
        # -----------------------------------------------------

        extracted_audio_path = None

        if audio_present:

            try:
                extracted_audio_path = (
                    self._extract_audio(
                        normalized_path
                    )
                )

            except RuntimeError as exc:

                return ProcessingResult(
                    status=ProcessingStatus.PARTIAL,
                    media_type=MediaType.VIDEO,
                    artifacts=artifacts,
                    extracted_data={
                        "duration_seconds": duration,
                        "width": width,
                        "height": height,
                        "frame_rate": frame_rate,
                        "video_codec": video_codec,
                        "audio_present": True,
                        "audio_codec": audio_codec,
                        "audio_channels": audio_channels,
                        "audio_sample_rate": (
                            audio_sample_rate
                        ),
                        "container_format": (
                            container_format
                        ),
                        "normalized": True,
                        "audio_extracted": False,
                        "transcribed": False,
                        "frames_extracted": 0,
                        "frame_ocr_available": False,
                    },
                    warnings=[
                        f"Audio extraction failed: {exc}"
                    ],
                    metadata={
                        "filename": file_path.name,
                    },
                )

            audio_size = 0

            try:
                audio_size = (
                    extracted_audio_path.stat().st_size
                )
            except OSError:
                pass

            audio_artifact = ProcessingArtifact(
                artifact_id=(
                    f"{file_path.stem}-audio"
                ),
                artifact_type=ArtifactType.AUDIO,
                file_path=str(
                    extracted_audio_path
                ),
                mime_type="audio/wav",
                size_bytes=audio_size,
                metadata={
                    "source_video": (
                        normalized_path.name
                    ),
                    "format": "wav",
                    "sample_rate": 16000,
                    "channels": 1,
                    "codec": "pcm_s16le",
                    "normalized": True,
                    "extraction_method": "ffmpeg",
                },
            )

            artifacts.append(
                audio_artifact
            )

        # -----------------------------------------------------
        # Transcription
        # -----------------------------------------------------

        transcript = []
        transcribed = False
        transcription_warning = None

        if extracted_audio_path is not None:

            try:
                transcription_extractor = (
                    TranscriptionExtractor(
                        model_name=self.WHISPER_MODEL
                    )
                )

                transcript_evidence = (
                    transcription_extractor.extract(
                        extracted_audio_path,
                        source_type="video",
                        source_artifact=(
                            extracted_audio_path.name
                        ),
                    )
                )

                transcript = [
                    item.model_dump()
                    for item in transcript_evidence
                ]

                transcribed = True

            except TranscriptionError as exc:

                transcription_warning = (
                    f"Video transcription failed: {exc}"
                )

            except Exception as exc:

                transcription_warning = (
                    f"Unexpected transcription error: {exc}"
                )

        # -----------------------------------------------------
        # Sample video frames
        # -----------------------------------------------------

        sampled_frames = []
        frame_extraction_warning = None

        try:
            sampled_frames = (
                self._extract_sampled_frames(
                    normalized_path,
                    duration=duration,
                    frame_rate=frame_rate,
                )
            )

        except RuntimeError as exc:

            frame_extraction_warning = (
                f"Video frame extraction failed: {exc}"
            )

        # -----------------------------------------------------
        # Frame artifacts + OCR
        # -----------------------------------------------------

        frame_ocr_evidence = []
        frame_ocr_warning = None

        if sampled_frames:

            try:
                ocr_extractor = OCRExtractor()

                for frame_info in sampled_frames:

                    frame_path = Path(
                        frame_info["file_path"]
                    )

                    frame_number = frame_info[
                        "frame_number"
                    ]

                    timestamp = frame_info[
                        "timestamp_seconds"
                    ]

                    # -----------------------------------------
                    # OCR
                    # -----------------------------------------

                    evidence = ocr_extractor.extract(
                        frame_path,
                        source_type="video",
                        source_artifact=file_path.name,
                    )

                    # Add video-specific provenance.
                    for item in evidence:

                        item.provenance.source_type = (
                            "video"
                        )

                        item.provenance.source_artifact = (
                            file_path.name
                        )

                        item.provenance.frame_number = (
                            frame_number
                        )

                        item.provenance.timestamp_start = (
                            timestamp
                        )

                        item.provenance.timestamp_end = (
                            timestamp
                        )

                    frame_ocr_evidence.extend(
                        evidence
                    )

                    # -----------------------------------------
                    # Frame artifact
                    # -----------------------------------------

                    frame_size = 0

                    try:
                        frame_size = (
                            frame_path.stat().st_size
                        )
                    except OSError:
                        pass

                    artifacts.append(
                        ProcessingArtifact(
                            artifact_id=(
                                f"{file_path.stem}-frame-"
                                f"{frame_number}"
                            ),
                            artifact_type=(
                                ArtifactType.FRAME
                            ),
                            file_path=str(
                                frame_path
                            ),
                            mime_type="image/jpeg",
                            size_bytes=frame_size,
                            metadata={
                                "source_video": (
                                    file_path.name
                                ),
                                "frame_number": (
                                    frame_number
                                ),
                                "timestamp_seconds": (
                                    timestamp
                                ),
                                "extraction_method": (
                                    "ffmpeg"
                                ),
                                "ocr_evidence_count": (
                                    len(evidence)
                                ),
                            },
                        )
                    )

            except OCRExtractionError as exc:

                frame_ocr_warning = (
                    f"Video frame OCR failed: {exc}"
                )

            except Exception as exc:

                frame_ocr_warning = (
                    f"Unexpected video frame OCR "
                    f"error: {exc}"
                )

        # -----------------------------------------------------
        # Warnings
        # -----------------------------------------------------

        warnings = []

        if transcription_warning:
            warnings.append(
                transcription_warning
            )

        if not audio_present:
            warnings.append(
                "No audio stream was found; "
                "transcription was skipped."
            )

        if frame_extraction_warning:
            warnings.append(
                frame_extraction_warning
            )

        if frame_ocr_warning:
            warnings.append(
                frame_ocr_warning
            )

        # -----------------------------------------------------
        # Final status
        # -----------------------------------------------------

        if (
            audio_present
            and not transcribed
        ):
            status = ProcessingStatus.PARTIAL

        elif frame_extraction_warning:
            status = ProcessingStatus.PARTIAL

        else:
            status = ProcessingStatus.SUCCESS

        # -----------------------------------------------------
        # Final result
        # -----------------------------------------------------

        return ProcessingResult(
            status=status,
            media_type=MediaType.VIDEO,
            artifacts=artifacts,
            extracted_data={
                "duration_seconds": duration,
                "width": width,
                "height": height,
                "frame_rate": frame_rate,
                "video_codec": video_codec,
                "audio_present": audio_present,
                "audio_codec": audio_codec,
                "audio_channels": audio_channels,
                "audio_sample_rate": audio_sample_rate,
                "container_format": container_format,
                "normalized": True,
                "normalized_format": "mp4",
                "normalized_video_codec": "h264",
                "normalized_audio_codec": "aac",
                "audio_extracted": (
                    extracted_audio_path is not None
                ),
                "extracted_audio_format": (
                    "wav"
                    if extracted_audio_path
                    else None
                ),
                "transcribed": transcribed,
                "transcript": transcript,
                "frames_extracted": len(
                    sampled_frames
                ),
                "frame_ocr_available": (
                    len(frame_ocr_evidence) > 0
                ),
                "frame_ocr_evidence": [
                    item.model_dump()
                    for item in frame_ocr_evidence
                ],
            },
            warnings=warnings,
            metadata={
                "filename": file_path.name,
                "transcription_model": (
                    self.WHISPER_MODEL
                    if extracted_audio_path
                    else None
                ),
                "transcript_segments": len(
                    transcript
                ),
                "frame_interval_seconds": (
                    self.FRAME_INTERVAL_SECONDS
                ),
                "frames_extracted": len(
                    sampled_frames
                ),
                "frame_ocr_evidence_count": len(
                    frame_ocr_evidence
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
                "the video file."
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
    # Video normalization
    # =========================================================

    @staticmethod
    def _normalize_video(
        file_path: Path,
    ) -> Path:

        output_dir = (
            file_path.parent
            / "normalized_video"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            output_dir
            / f"{file_path.stem}_normalized.mp4"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(file_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg was not found. "
                "Ensure FFmpeg is available in PATH."
            ) from exc

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Video normalization timed out."
            ) from exc

        if result.returncode != 0:

            error_message = (
                result.stderr.strip()
                or "Unknown FFmpeg error."
            )

            raise RuntimeError(
                f"Video normalization failed: "
                f"{error_message}"
            )

        if not output_path.exists():
            raise RuntimeError(
                "FFmpeg completed but the "
                "normalized video was not created."
            )

        return output_path

    # =========================================================
    # Audio extraction
    # =========================================================

    @staticmethod
    def _extract_audio(
        normalized_video: Path,
    ) -> Path:

        output_dir = (
            normalized_video.parent
            / "extracted_audio"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        output_path = (
            output_dir
            / f"{normalized_video.stem}_audio.wav"
        )

        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(normalized_video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg was not found. "
                "Ensure FFmpeg is available in PATH."
            ) from exc

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Audio extraction timed out."
            ) from exc

        if result.returncode != 0:

            error_message = (
                result.stderr.strip()
                or "Unknown FFmpeg error."
            )

            raise RuntimeError(
                f"Audio extraction failed: "
                f"{error_message}"
            )

        if not output_path.exists():
            raise RuntimeError(
                "FFmpeg completed but the "
                "extracted audio was not created."
            )

        return output_path

    # =========================================================
    # Sample video frames
    # =========================================================

    @staticmethod
    def _extract_sampled_frames(
        normalized_video: Path,
        duration: float | None,
        frame_rate: float | None,
    ) -> list[dict]:

        if duration is None or duration <= 0:
            return []

        output_dir = (
            normalized_video.parent
            / "sampled_frames"
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # -----------------------------------------------------
        # Remove previously generated frames
        # -----------------------------------------------------

        for old_frame in output_dir.glob(
            "frame_*.jpg"
        ):
            try:
                old_frame.unlink()
            except OSError:
                pass

        # -----------------------------------------------------
        # Build exact timestamps.
        #
        # Example for a 6.84 second video:
        #
        # 0.0
        # 2.0
        # 4.0
        # 6.0
        # -----------------------------------------------------

        timestamps = []

        current_timestamp = 0.0

        while current_timestamp < duration:

            timestamps.append(
                round(
                    current_timestamp,
                    3,
                )
            )

            current_timestamp += (
                VideoProcessor.FRAME_INTERVAL_SECONDS
            )

        # -----------------------------------------------------
        # Extract each requested timestamp individually
        # -----------------------------------------------------

        results = []

        for index, timestamp in enumerate(
            timestamps
        ):

            output_path = (
                output_dir
                / f"frame_{index + 1:05d}.jpg"
            )

            command = [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(normalized_video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(output_path),
            ]

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )

            except FileNotFoundError as exc:
                raise RuntimeError(
                    "FFmpeg was not found while "
                    "extracting video frames."
                ) from exc

            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "Video frame extraction timed out."
                ) from exc

            if result.returncode != 0:

                error_message = (
                    result.stderr.strip()
                    or "Unknown FFmpeg error."
                )

                raise RuntimeError(
                    f"Frame extraction failed at "
                    f"{timestamp}s: "
                    f"{error_message}"
                )

            if not output_path.exists():

                raise RuntimeError(
                    f"FFmpeg completed but frame "
                    f"at {timestamp}s was not created."
                )

            # -------------------------------------------------
            # Calculate source frame number using the actual
            # video frame rate.
            # -------------------------------------------------

            if frame_rate and frame_rate > 0:

                frame_number = round(
                    timestamp * frame_rate
                )

            else:

                frame_number = index

            results.append(
                {
                    "file_path": str(
                        output_path
                    ),
                    "frame_number": frame_number,
                    "timestamp_seconds": timestamp,
                }
            )

        return results

    # =========================================================
    # Stream helpers
    # =========================================================

    @staticmethod
    def _find_stream(
        streams: list[dict],
        stream_type: str,
    ) -> dict | None:

        for stream in streams:

            if stream.get(
                "codec_type"
            ) == stream_type:

                return stream

        return None

    @staticmethod
    def _parse_frame_rate(
        value,
    ) -> float | None:

        if not value:
            return None

        try:
            if "/" in str(value):

                numerator, denominator = (
                    str(value).split(
                        "/",
                        1,
                    )
                )

                numerator = float(
                    numerator
                )

                denominator = float(
                    denominator
                )

                if denominator == 0:
                    return None

                return round(
                    numerator / denominator,
                    3,
                )

            return float(value)

        except (
            TypeError,
            ValueError,
            ZeroDivisionError,
        ):
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
    # Failure helper
    # =========================================================

    @staticmethod
    def _failure(
        file_path: Path,
        code: str,
        message: str,
    ) -> ProcessingResult:

        error = ProcessingError(
            stage="video_processing",
            code=code,
            message=message,
            recoverable=False,
        )

        return ProcessingResult(
            status=ProcessingStatus.FAILED,
            media_type=MediaType.VIDEO,
            errors=[error],
            metadata={
                "filename": file_path.name,
            },
        )


