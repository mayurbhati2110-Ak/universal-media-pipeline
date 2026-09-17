from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, HttpUrl

from app.pipeline.orchestrator import (
    MediaPipeline,
    MediaPipelineError,
)

from app.services.jobs import job_store


router = APIRouter(
    prefix="/api/media",
    tags=["Media"],
)

pipeline = MediaPipeline()


class MediaURLRequest(BaseModel):
    url: HttpUrl


# ============================================================
# Upload
# ============================================================

@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
):
    """
    Upload a media file and process it through
    the universal media pipeline.
    """

    job = job_store.create()

    job_store.update(
        job.job_id,
        status="processing",
    )

    try:

        result = pipeline.process_upload(
            file=file.file,
            filename=(
                file.filename
                or "uploaded_file"
            ),
            declared_mime_type=file.content_type,
        )

        # Determine final status.
        if result.normalized is not None:

            if (
                result.normalized.processing.status
                == "partial"
            ):
                status = "partial"

            elif result.normalized.processing.cache_hit:
                status = "cached"

            else:
                status = "completed"

        else:
            status = "failed"

        job_store.update(
            job.job_id,
            status=status,
            result=result,
        )

        return {
            "job_id": job.job_id,
            "status": status,
            "result": result,
        }

    except MediaPipelineError as exc:

        job_store.update(
            job.job_id,
            status="failed",
            error=str(exc),
        )

        raise HTTPException(
            status_code=400,
            detail={
                "job_id": job.job_id,
                "error": str(exc),
            },
        )

    except Exception as exc:

        job_store.update(
            job.job_id,
            status="failed",
            error=str(exc),
        )

        raise HTTPException(
            status_code=500,
            detail={
                "job_id": job.job_id,
                "error": (
                    "Unexpected processing error: "
                    f"{exc}"
                ),
            },
        )


# ============================================================
# Direct URL
# ============================================================

@router.post("/url")
def process_media_url(
    request: MediaURLRequest,
):
    """
    Acquire and process media from an accessible
    direct URL.
    """

    job = job_store.create()

    job_store.update(
        job.job_id,
        status="processing",
    )

    try:

        result = pipeline.process_url(
            str(request.url)
        )

        if result.normalized is not None:

            if (
                result.normalized.processing.status
                == "partial"
            ):
                status = "partial"

            elif result.normalized.processing.cache_hit:
                status = "cached"

            else:
                status = "completed"

        else:
            status = "failed"

        job_store.update(
            job.job_id,
            status=status,
            result=result,
        )

        return {
            "job_id": job.job_id,
            "status": status,
            "result": result,
        }

    except MediaPipelineError as exc:

        job_store.update(
            job.job_id,
            status="failed",
            error=str(exc),
        )

        raise HTTPException(
            status_code=400,
            detail={
                "job_id": job.job_id,
                "error": str(exc),
            },
        )

    except Exception as exc:

        job_store.update(
            job.job_id,
            status="failed",
            error=str(exc),
        )

        raise HTTPException(
            status_code=500,
            detail={
                "job_id": job.job_id,
                "error": (
                    "Unexpected processing error: "
                    f"{exc}"
                ),
            },
        )


# ============================================================
# Job status
# ============================================================

@router.get("/jobs/{job_id}")
def get_job_status(
    job_id: str,
):
    """
    Return the current status and metadata of a job.
    """

    job = job_store.get(
        job_id
    )

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    return {
        "job_id": job.job_id,
        "status": job.status,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "error": job.error,
    }


# ============================================================
# Job result
# ============================================================

@router.get("/jobs/{job_id}/result")
def get_job_result(
    job_id: str,
):
    """
    Return the normalized result of a completed job.
    """

    job = job_store.get(
        job_id
    )

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    if job.result is None:

        return {
            "job_id": job.job_id,
            "status": job.status,
            "result": None,
            "error": job.error,
        }

    return {
        "job_id": job.job_id,
        "status": job.status,
        "result": job.result,
    }


# ============================================================
# Job artifacts
# ============================================================

@router.get("/jobs/{job_id}/artifacts")
def get_job_artifacts(
    job_id: str,
):
    """
    Return artifact metadata for a processed job.

    Supports both:
    - freshly processed results
    - SHA-256 cache-hit results
    """

    job = job_store.get(
        job_id
    )

    if job is None:

        raise HTTPException(
            status_code=404,
            detail="Job not found.",
        )

    if job.result is None:

        return {
            "job_id": job.job_id,
            "status": job.status,
            "artifacts": [],
        }

    # ---------------------------------------------------------
    # Freshly processed result
    # ---------------------------------------------------------

    processing = job.result.processing

    if processing is not None:

        artifacts = [
            (
                artifact.model_dump()
                if hasattr(
                    artifact,
                    "model_dump",
                )
                else artifact
            )
            for artifact in processing.artifacts
        ]

    # ---------------------------------------------------------
    # Cached result
    #
    # On a cache hit, the outer MediaInputResult has
    # processing=None. The artifact information is instead
    # stored inside normalized.artifacts.
    # ---------------------------------------------------------

    elif job.result.normalized is not None:

        normalized_artifacts = (
            job.result.normalized.artifacts
        )

        if hasattr(
            normalized_artifacts,
            "items",
        ):

            artifacts = [
                (
                    artifact.model_dump()
                    if hasattr(
                        artifact,
                        "model_dump",
                    )
                    else artifact
                )
                for artifact in (
                    normalized_artifacts.items
                )
            ]

        else:
            artifacts = []

    else:

        artifacts = []

    return {
        "job_id": job.job_id,
        "status": job.status,
        "artifacts": artifacts,
    }