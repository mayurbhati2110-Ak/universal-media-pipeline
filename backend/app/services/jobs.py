from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


@dataclass
class Job:
    job_id: str
    status: str = "queued"
    created_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )
    result: Optional[Any] = None
    error: Optional[str] = None


class JobStore:
    """
    Lightweight in-memory job store.

    This is intentionally simple for the MVP.
    Redis/Celery/database-backed jobs can be added later
    without changing the normalized media contract.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def create(self) -> Job:
        job = Job(
            job_id=f"job-{uuid4().hex[:16]}"
        )

        self._jobs[job.job_id] = job

        return job

    def get(
        self,
        job_id: str,
    ) -> Optional[Job]:

        return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        status: Optional[str] = None,
        result: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> Optional[Job]:

        job = self._jobs.get(job_id)

        if job is None:
            return None

        if status is not None:
            job.status = status

        if result is not None:
            job.result = result

        if error is not None:
            job.error = error

        job.updated_at = datetime.now(
            timezone.utc
        ).isoformat()

        return job


# Shared in-memory store for the application.
job_store = JobStore()