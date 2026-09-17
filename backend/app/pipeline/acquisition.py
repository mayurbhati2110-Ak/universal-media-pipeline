import hashlib
import ipaddress
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.core.config import settings
from app.models.media import InputSource


class AcquisitionError(Exception):
    """Raised when media acquisition fails."""


@dataclass
class AcquisitionResult:
    """
    Result returned after successfully acquiring media.
    """

    source_type: InputSource
    source: str

    file_path: Path

    filename: Optional[str] = None
    declared_mime_type: Optional[str] = None

    size_bytes: int = 0
    content_hash: Optional[str] = None


class MediaAcquirer:
    """
    Handles acquisition of media from uploads and direct URLs.

    Responsibilities:
    - Stream uploaded files to temporary storage.
    - Stream URL downloads to temporary storage.
    - Enforce maximum file/download size.
    - Calculate SHA-256 while writing.
    - Validate URL schemes.
    - Perform basic SSRF protection.
    - Handle redirects explicitly.
    - Treat Content-Type as a hint only.
    - Never load the complete media file into RAM.
    """

    CHUNK_SIZE = 1024 * 1024  # 1 MB

    def __init__(self) -> None:
        """
        Ensure temporary storage exists.
        """

        settings.TEMP_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    # =========================================================
    # Upload acquisition
    # =========================================================

    def acquire_upload(
        self,
        file: BinaryIO,
        filename: Optional[str] = None,
        declared_mime_type: Optional[str] = None,
    ) -> AcquisitionResult:
        """
        Acquire an uploaded media file.

        The uploaded stream is copied to temporary storage
        in chunks while calculating its SHA-256 hash.
        """

        if file is None:
            raise AcquisitionError(
                "No upload file was provided."
            )

        safe_filename = self._safe_filename(
            filename or "uploaded_media"
        )

        destination = self._create_temp_path(
            safe_filename
        )

        try:
            size_bytes, content_hash = self._stream_to_disk(
                source=file,
                destination=destination,
                max_size=settings.max_file_size_bytes,
            )

        except Exception:
            self._remove_file(destination)
            raise

        return AcquisitionResult(
            source_type=InputSource.UPLOAD,
            source=safe_filename,
            file_path=destination,
            filename=safe_filename,
            declared_mime_type=declared_mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
        )

    # =========================================================
    # URL acquisition
    # =========================================================

    def acquire_url(
        self,
        url: str,
    ) -> AcquisitionResult:
        """
        Acquire media from a directly accessible URL.

        Redirects are handled manually so that every redirect
        destination can be validated before following it.
        """

        self._validate_url(url)

        current_url = url
        redirect_count = 0

        timeout = httpx.Timeout(
            settings.DOWNLOAD_TIMEOUT_SECONDS
        )

        client = httpx.Client(
            follow_redirects=False,
            timeout=timeout,
        )

        try:
            while True:

                # Validate every redirect destination.
                self._validate_url(current_url)

                try:
                    with client.stream(
                        "GET",
                        current_url,
                        headers={
                            "User-Agent": (
                                "UniversalMediaPipeline/1.0"
                            )
                        },
                    ) as response:

                        status_code = response.status_code

                        # -------------------------------------------------
                        # Redirect handling
                        # -------------------------------------------------

                        if 300 <= status_code < 400:

                            location = response.headers.get(
                                "location"
                            )

                            if not location:
                                raise AcquisitionError(
                                    "Server returned a redirect "
                                    "without a Location header."
                                )

                            redirect_count += 1

                            if (
                                redirect_count
                                > settings.MAX_REDIRECTS
                            ):
                                raise AcquisitionError(
                                    "Maximum redirect limit exceeded."
                                )

                            current_url = urljoin(
                                current_url,
                                location,
                            )

                            continue

                        # -------------------------------------------------
                        # HTTP errors
                        # -------------------------------------------------

                        if status_code >= 400:
                            raise AcquisitionError(
                                f"Media URL returned HTTP "
                                f"{status_code}."
                            )

                        # -------------------------------------------------
                        # Content-Length pre-check
                        # -------------------------------------------------

                        content_length = response.headers.get(
                            "content-length"
                        )

                        if content_length:

                            try:
                                expected_size = int(
                                    content_length
                                )

                            except ValueError:
                                expected_size = None

                            if (
                                expected_size is not None
                                and expected_size
                                > settings.max_download_size_bytes
                            ):
                                raise AcquisitionError(
                                    "Remote file exceeds the "
                                    "maximum allowed download size."
                                )

                        # -------------------------------------------------
                        # Determine temporary filename
                        # -------------------------------------------------

                        remote_filename = (
                            self._filename_from_url(
                                current_url
                            )
                        )

                        destination = self._create_temp_path(
                            remote_filename
                        )

                        # -------------------------------------------------
                        # Stream download
                        # -------------------------------------------------

                        hasher = hashlib.sha256()
                        total_size = 0

                        try:
                            with destination.open(
                                "wb"
                            ) as output:

                                for chunk in response.iter_bytes(
                                    chunk_size=self.CHUNK_SIZE
                                ):

                                    if not chunk:
                                        continue

                                    total_size += len(chunk)

                                    # Enforce limit even when
                                    # Content-Length is missing
                                    # or incorrect.
                                    if (
                                        total_size
                                        > settings.max_download_size_bytes
                                    ):
                                        raise AcquisitionError(
                                            "Remote file exceeds "
                                            "the maximum allowed "
                                            "download size."
                                        )

                                    output.write(chunk)
                                    hasher.update(chunk)

                        except AcquisitionError:
                            self._remove_file(
                                destination
                            )
                            raise

                        except (
                            OSError,
                            httpx.HTTPError,
                        ) as exc:

                            self._remove_file(
                                destination
                            )

                            raise AcquisitionError(
                                f"Failed while downloading media: "
                                f"{exc}"
                            ) from exc

                        # -------------------------------------------------
                        # Empty response
                        # -------------------------------------------------

                        if total_size == 0:

                            self._remove_file(
                                destination
                            )

                            raise AcquisitionError(
                                "Remote resource returned an "
                                "empty file."
                            )

                        # -------------------------------------------------
                        # Successful acquisition
                        # -------------------------------------------------

                        return AcquisitionResult(
                            source_type=InputSource.URL,
                            source=url,
                            file_path=destination,
                            filename=remote_filename,
                            declared_mime_type=(
                                response.headers.get(
                                    "content-type"
                                )
                            ),
                            size_bytes=total_size,
                            content_hash=hasher.hexdigest(),
                        )

                except httpx.HTTPError as exc:

                    raise AcquisitionError(
                        f"Unable to access URL: {exc}"
                    ) from exc

        finally:
            client.close()

    # =========================================================
    # Streaming helper
    # =========================================================

    def _stream_to_disk(
        self,
        source: BinaryIO,
        destination: Path,
        max_size: int,
    ) -> tuple[int, str]:
        """
        Stream a file-like object to disk.

        Returns:
            (total_size, sha256_hash)
        """

        hasher = hashlib.sha256()
        total_size = 0

        try:
            with destination.open(
                "wb"
            ) as output:

                while True:

                    chunk = source.read(
                        self.CHUNK_SIZE
                    )

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > max_size:
                        raise AcquisitionError(
                            "Uploaded file exceeds the "
                            "maximum allowed file size."
                        )

                    output.write(chunk)
                    hasher.update(chunk)

        except AcquisitionError:
            raise

        except (
            OSError,
            ValueError,
        ) as exc:

            raise AcquisitionError(
                f"Failed to store uploaded file: {exc}"
            ) from exc

        if total_size == 0:
            raise AcquisitionError(
                "Uploaded file is empty."
            )

        return (
            total_size,
            hasher.hexdigest(),
        )

    # =========================================================
    # URL validation
    # =========================================================

    def _validate_url(
        self,
        url: str,
    ) -> None:
        """
        Validate URL scheme and hostname.
        """

        try:
            parsed = urlparse(url)

        except ValueError as exc:

            raise AcquisitionError(
                f"Invalid URL: {exc}"
            ) from exc

        # -----------------------------------------------------
        # Scheme validation
        # -----------------------------------------------------

        if parsed.scheme.lower() not in (
            settings.ALLOWED_URL_SCHEMES
        ):
            raise AcquisitionError(
                f"URL scheme '{parsed.scheme}' is not allowed."
            )

        # -----------------------------------------------------
        # Host validation
        # -----------------------------------------------------

        if not parsed.hostname:
            raise AcquisitionError(
                "URL must contain a valid hostname."
            )

        self._validate_host(
            parsed.hostname
        )

    # =========================================================
    # Basic SSRF protection
    # =========================================================

    @staticmethod
    def _validate_host(
        hostname: str,
    ) -> None:
        """
        Resolve the hostname and reject restricted addresses.

        Blocks:
        - Private addresses
        - Loopback addresses
        - Link-local addresses
        - Multicast addresses
        - Reserved addresses
        - Unspecified addresses
        """

        try:
            addresses = socket.getaddrinfo(
                hostname,
                None,
            )

        except socket.gaierror as exc:

            raise AcquisitionError(
                f"Unable to resolve URL host '{hostname}'."
            ) from exc

        for address in addresses:

            ip_value = address[4][0]

            try:
                ip = ipaddress.ip_address(
                    ip_value
                )

            except ValueError:
                continue

            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise AcquisitionError(
                    "URL resolves to a restricted "
                    "or non-public network address."
                )

    # =========================================================
    # Filename helpers
    # =========================================================

    @staticmethod
    def _safe_filename(
        filename: str,
    ) -> str:
        """
        Remove directory components from an uploaded filename.
        """

        filename = Path(
            filename
        ).name

        if not filename:
            return "media"

        return filename

    @staticmethod
    def _filename_from_url(
        url: str,
    ) -> str:
        """
        Extract a filename from the URL path.

        Falls back to 'downloaded_media' when the URL
        does not contain a filename.
        """

        parsed = urlparse(url)

        name = Path(
            parsed.path
        ).name

        if not name:
            return "downloaded_media"

        return name

    # =========================================================
    # Storage helpers
    # =========================================================

    @staticmethod
    def _create_temp_path(
        filename: str,
    ) -> Path:
        """
        Create a unique temporary storage path.

        Only the original extension is preserved.
        """

        extension = Path(
            filename
        ).suffix.lower()

        unique_name = (
            f"{uuid.uuid4().hex}"
            f"{extension}"
        )

        return (
            settings.TEMP_DIR
            / unique_name
        )

    @staticmethod
    def _remove_file(
        path: Path,
    ) -> None:
        """
        Safely remove a temporary file.
        """

        try:

            if path.exists():
                path.unlink()

        except OSError:
            pass