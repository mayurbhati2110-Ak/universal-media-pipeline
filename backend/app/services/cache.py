import json
from pathlib import Path
from typing import Optional

from app.schemas.normalized import NormalizedMediaDocument


class MediaCache:
    """
    Simple content-hash based cache for processed media.

    The SHA-256 content hash is authoritative, so the same
    media content can be reused even when filenames or URLs differ.
    """

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    def _cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.json"

    def get(
        self,
        content_hash: Optional[str],
    ) -> Optional[NormalizedMediaDocument]:

        if not content_hash:
            return None

        path = self._cache_path(content_hash)

        if not path.exists():
            return None

        try:
            data = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            return NormalizedMediaDocument.model_validate(
                data
            )

        except Exception:
            # Corrupt/old cache entries should never
            # break normal processing.
            return None

    def set(
        self,
        content_hash: Optional[str],
        document: NormalizedMediaDocument,
    ) -> None:

        if not content_hash:
            return

        path = self._cache_path(content_hash)

        path.write_text(
            document.model_dump_json(
                indent=2
            ),
            encoding="utf-8",
        )