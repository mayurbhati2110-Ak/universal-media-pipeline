from pathlib import Path
from typing import Optional
import hashlib
import shutil
import uuid

from app.models.processing import ProcessingArtifact, ArtifactType


class ArtifactManager:
    """
    Centralized storage and metadata management for pipeline artifacts.

    Artifacts are stored under:
        storage/artifacts/<document_id>/

    The manager keeps artifact handling separate from
    modality-specific processors.
    """

    def __init__(self, storage_dir: Path = Path("storage/artifacts")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _document_dir(self, document_id: str) -> Path:
        path = self.storage_dir / document_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()

        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest()

    def store(
        self,
        document_id: str,
        source_path: Path,
        artifact_type: ArtifactType,
        filename: Optional[str] = None,
        mime_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ProcessingArtifact:
        """
        Copy an artifact into centralized pipeline storage
        and return its normalized metadata.
        """

        if not source_path.exists():
            raise FileNotFoundError(
                f"Artifact source does not exist: {source_path}"
            )

        if not source_path.is_file():
            raise ValueError(
                f"Artifact source is not a file: {source_path}"
            )

        document_dir = self._document_dir(document_id)

        artifact_id = f"artifact-{uuid.uuid4().hex}"

        output_name = filename or source_path.name
        destination = document_dir / output_name

        # Avoid accidental overwrite.
        if destination.exists():
            destination = (
                document_dir
                / f"{artifact_id}_{output_name}"
            )

        shutil.copy2(source_path, destination)

        size_bytes = destination.stat().st_size
        content_hash = self._sha256(destination)

        return ProcessingArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            file_path=str(destination),
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            metadata=metadata or {},
        )

    def list_artifacts(
        self,
        document_id: str,
    ) -> list[Path]:
        """
        Return all stored artifact files for a document.
        """

        document_dir = self.storage_dir / document_id

        if not document_dir.exists():
            return []

        return [
            path
            for path in document_dir.iterdir()
            if path.is_file()
        ]

    def get_artifact(
        self,
        document_id: str,
        artifact_id: str,
    ) -> Optional[Path]:
        """
        Find an artifact by its artifact ID.

        Artifact IDs are embedded into generated filenames when
        duplicate filenames require collision handling.
        """

        document_dir = self.storage_dir / document_id

        if not document_dir.exists():
            return None

        for path in document_dir.iterdir():
            if path.is_file() and artifact_id in path.name:
                return path

        return None


# Shared manager used by the pipeline.
artifact_manager = ArtifactManager()