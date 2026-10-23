"""Background worker: runs queued jobs (sending, PDFs, syncs, notifications) and periodic schedules.

Usage: uv run python -m app.worker            (run forever)
       uv run python -m app.worker --check    (list registered handlers and exit)
Handlers register with @handler("kind"). Tests call `process_due_jobs` directly.
"""

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Org, QueueJob, utcnow
from app.queue import Retry, backoff, enqueue

log = logging.getLogger("app.worker")
HANDLERS: dict[str, Callable[[Session, QueueJob], None]] = {}


def handler(kind: str):
    def wrap(fn):
        HANDLERS[kind] = fn
        return fn
    return wrap


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def load_handlers() -> None:
    # Importing registers the handlers.
    import app.integrations.jobs  # noqa: F401
    import app.notices.sending  # noqa: F401
    import app.notify  # noqa: F401
    import app.reports.scheduled  # noqa: F401
    import app.retention  # noqa: F401
    import app.workflow.escalation  # noqa: F401


def process_due_jobs(db: Session, limit: int = 100, now: datetime | None = None) -> int:
    """Run jobs whose run_after has passed. Commits after each job. Returns jobs processed."""
    load_handlers()
    now = now or utcnow()
    jobs = [j for j in db.scalars(select(QueueJob).where(QueueJob.status == "queued").order_by(QueueJob.id))
            if _aware(j.run_after) <= now][:limit]
    done = 0
    for job in jobs:
        fn = HANDLERS.get(job.kind)
        if fn is None:
            job.status, job.last_error = "failed", f"no handler for {job.kind}"
            db.commit()
            continue
        job.status = "running"
        db.flush()
        try:
            fn(db, job)
            job.status, job.finished_at = "done", utcnow()
        except Retry as r:
            job.status, job.run_after = "queued", utcnow() + timedelta(seconds=r.after_seconds)
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job
            db.rollback()
            job = db.get(QueueJob, job.id)
            job.attempts += 1
            job.last_error = f"{type(exc).__name__}: {str(exc)[:300]}"
            job.status = "failed" if job.attempts >= job.max_attempts else "queued"
            job.run_after = utcnow() + backoff(job.attempts)
            log.warning("job %s (%s) failed attempt %s", job.id, job.kind, job.attempts)
        db.commit()
        done += 1
    return done


def drain(db: Session, max_rounds: int = 20) -> None:
    """Run jobs until none are due now (tests and synchronous helpers)."""
    for _ in range(max_rounds):
        if process_due_jobs(db) == 0:
            return


SCHEDULES = [  # (job kind, interval)
    ("escalate_approvals", timedelta(hours=1)),
    ("retention_sweep", timedelta(days=1)),
    ("weekly_report", timedelta(days=7)),
]


def run_schedules(db: Session) -> None:
    now = utcnow()
    for org_id in db.scalars(select(Org.id)):
        for kind, every in SCHEDULES:
            last = db.scalar(select(QueueJob.created_at).where(QueueJob.org_id == org_id, QueueJob.kind == kind)
                             .order_by(QueueJob.id.desc()).limit(1))
            if last is None or _aware(last) <= now - every:
                enqueue(db, org_id, kind, {})
    db.commit()


def main(check: bool = False) -> None:
    from app.db import SessionLocal

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    load_handlers()
    if not HANDLERS:
        raise SystemExit("no job handlers registered")
    log.info("worker started with handlers: %s", ", ".join(sorted(HANDLERS)))
    if check:
        return
    last_schedule = 0.0
    while True:
        with SessionLocal() as db:
            if time.monotonic() - last_schedule > 60:
                run_schedules(db)
                last_schedule = time.monotonic()
            n = process_due_jobs(db)
        time.sleep(0.2 if n else 1.0)


if __name__ == "__main__":
    import sys

    # Under `python -m` this file is `__main__`, while handler modules import `app.worker`. Run main from
    # `app.worker` so both use the same HANDLERS registry.
    from app.worker import main as run

    run(check="--check" in sys.argv)
