from pathlib import Path

import whisper

from app.models.provenance import Evidence, Provenance


class TranscriptionError(Exception):
    """Raised when speech transcription fails."""


class TranscriptionExtractor:
    """
    Deterministic speech-to-text extraction using Whisper.

    Produces timestamped transcript evidence while preserving
    provenance back to the source audio artifact.
    """

    def __init__(
        self,
        model_name: str = "base",
    ):
        try:
            self.model = whisper.load_model(
                model_name
            )
        except Exception as exc:
            raise TranscriptionError(
                f"Unable to load Whisper model '{model_name}': {exc}"
            ) from exc

    def extract(
        self,
        file_path: str | Path,
        source_type: str = "audio",
        source_artifact: str | None = None,
    ) -> list[Evidence]:

        path = Path(file_path)

        if not path.exists():
            raise TranscriptionError(
                f"Audio file does not exist: {path.name}"
            )

        if not path.is_file():
            raise TranscriptionError(
                f"Audio path is not a regular file: {path.name}"
            )

        artifact_name = source_artifact or path.name

        try:
            result = self.model.transcribe(
                str(path),
                fp16=False,
                verbose=False,
            )

        except Exception as exc:
            raise TranscriptionError(
                f"Transcription failed: {exc}"
            ) from exc

        segments = result.get(
            "segments",
            [],
        )

        evidence: list[Evidence] = []

        for segment in segments:

            text = str(
                segment.get("text", "")
            ).strip()

            if not text:
                continue

            start = self._to_float(
                segment.get("start")
            )

            end = self._to_float(
                segment.get("end")
            )

            evidence.append(
                Evidence(
                    evidence_id=(
                        f"transcript-{len(evidence) + 1}"
                    ),
                    content_type="transcript",
                    text=text,
                    provenance=Provenance(
                        source_type=source_type,
                        source_artifact=artifact_name,
                        timestamp_start=start,
                        timestamp_end=end,
                        extraction_method="whisper",
                    ),
                )
            )

        return evidence

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