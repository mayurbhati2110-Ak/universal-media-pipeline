from abc import ABC, abstractmethod
from pathlib import Path

from app.models.media import MediaType
from app.models.processing import ProcessingResult


class BaseMediaProcessor(ABC):
    """
    Common interface for all media processors.

    Every processor receives an already acquired and validated
    media file and returns a standardized ProcessingResult.
    """

    media_type: MediaType

    @abstractmethod
    def process(
        self,
        file_path: Path,
    ) -> ProcessingResult:
        """
        Process the supplied media file.

        Args:
            file_path: Path to the acquired/normalized media file.

        Returns:
            ProcessingResult containing artifacts, extracted
            data, warnings, and structured errors.
        """
        raise NotImplementedError

    def supports(
        self,
        media_type: MediaType,
    ) -> bool:
        """
        Check whether this processor handles the supplied
        media type.
        """

        return media_type == self.media_type