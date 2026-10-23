"""Database-backed job queue consumed by the worker (`python -m app.worker`)."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import QueueJob, utcnow


class Retry(Exception):
    """Raise from a handler to run the job again later without counting a failed attempt."""

    def __init__(self, after_seconds: float):
        super().__init__(f"retry after {after_seconds}s")
        self.after_seconds = after_seconds


def enqueue(db: Session, org_id: int, kind: str, payload: dict | None = None,
            run_after: datetime | None = None, max_attempts: int = 5) -> QueueJob:
    job = QueueJob(org_id=org_id, kind=kind, payload=payload or {}, run_after=run_after or utcnow(),
                   max_attempts=max_attempts)
    db.add(job)
    db.flush()
    return job


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(3600, 30 * 2 ** max(0, attempts - 1)))
