from pathlib import Path

from PIL import Image
import pytesseract
from pytesseract import Output

from app.models.provenance import Evidence, Provenance


class OCRExtractionError(Exception):
    """Raised when OCR extraction fails."""


class OCRExtractor:
    """Deterministic OCR extraction using Tesseract."""

    def __init__(self, tesseract_cmd: str | None = None):
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            raise OCRExtractionError(
                "Tesseract OCR is not available."
            ) from exc

    def extract(
        self,
        file_path: str | Path,
        source_type: str = "image",
        source_artifact: str | None = None,
        page: int | None = None,
    ) -> list[Evidence]:

        path = Path(file_path)

        if not path.exists():
            raise OCRExtractionError(
                f"Image file does not exist: {path.name}"
            )

        artifact_name = source_artifact or path.name

        try:
            with Image.open(path) as image:
                data = pytesseract.image_to_data(
                    image,
                    output_type=Output.DICT,
                )

        except Exception as exc:
            raise OCRExtractionError(
                f"OCR extraction failed: {exc}"
            ) from exc

        evidence: list[Evidence] = []

        text_values = data.get("text", [])
        confidences = data.get("conf", [])
        left_values = data.get("left", [])
        top_values = data.get("top", [])
        width_values = data.get("width", [])
        height_values = data.get("height", [])

        for index, raw_text in enumerate(text_values):

            text = str(raw_text).strip()

            if not text:
                continue

            confidence = self._parse_confidence(
                confidences[index]
                if index < len(confidences)
                else None
            )

            left = int(left_values[index])
            top = int(top_values[index])
            width = int(width_values[index])
            height = int(height_values[index])

            bbox = [
                left,
                top,
                left + width,
                top + height,
            ]

            evidence.append(
                Evidence(
                    evidence_id=f"ocr-{len(evidence) + 1}",
                    content_type="text",
                    text=text,
                    confidence=confidence,
                    provenance=Provenance(
                        source_type=source_type,
                        source_artifact=artifact_name,
                        page=page,
                        bbox=bbox,
                        extraction_method="tesseract_ocr",
                    ),
                )
            )

        return evidence

    @staticmethod
    def _parse_confidence(value) -> float | None:

        try:
            confidence = float(value)

            if confidence < 0:
                return None

            return round(confidence / 100.0, 4)

        except (TypeError, ValueError):
            return None