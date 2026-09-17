from typing import Iterable

from app.models.media import MediaType
from app.processors.base import BaseMediaProcessor


class ProcessorRegistry:
    """
    Maintains the available media processors and selects
    the correct processor for a detected media type.
    """

    def __init__(
        self,
        processors: Iterable[BaseMediaProcessor] | None = None,
    ) -> None:

        self._processors: list[
            BaseMediaProcessor
        ] = list(processors or [])

    def register(
        self,
        processor: BaseMediaProcessor,
    ) -> None:
        """
        Register a media processor.
        """

        if not isinstance(
            processor,
            BaseMediaProcessor,
        ):
            raise TypeError(
                "Processor must inherit from "
                "BaseMediaProcessor."
            )

        # Prevent duplicate processor registration
        # for the same media type.
        existing = self.get(
            processor.media_type
        )

        if existing is not None:
            raise ValueError(
                f"A processor for media type "
                f"'{processor.media_type.value}' "
                f"is already registered."
            )

        self._processors.append(
            processor
        )

    def get(
        self,
        media_type: MediaType,
    ) -> BaseMediaProcessor | None:
        """
        Return the processor responsible for the
        supplied media type.
        """

        for processor in self._processors:

            if processor.supports(
                media_type
            ):
                return processor

        return None

    def require(
        self,
        media_type: MediaType,
    ) -> BaseMediaProcessor:
        """
        Return a processor or raise a clear error if
        the media type is unsupported.
        """

        processor = self.get(
            media_type
        )

        if processor is None:
            raise LookupError(
                f"No processor registered for "
                f"media type '{media_type.value}'."
            )

        return processor

    def all(
        self,
    ) -> list[BaseMediaProcessor]:
        """
        Return all registered processors.
        """

        return list(
            self._processors
        )

    def supported_types(
        self,
    ) -> list[MediaType]:
        """
        Return all media types currently supported
        by registered processors.
        """

        return [
            processor.media_type
            for processor in self._processors
        ]