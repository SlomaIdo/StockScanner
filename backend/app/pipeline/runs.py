"""Record each pipeline run in ``ingest_runs`` for monitoring."""

import datetime as dt
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import IngestRun, IngestStatus

log = logging.getLogger(__name__)


@dataclass
class RunTracker:
    run: IngestRun
    ok: int = 0
    failed: int = 0
    notes: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        log.info(message)
        self.notes.append(message)


@contextmanager
def track_run(session: Session, job: str, scope: str | None = None) -> Iterator[RunTracker]:
    run = IngestRun(job=job, scope=scope, status=IngestStatus.RUNNING)
    session.add(run)
    session.commit()
    tracker = RunTracker(run=run)
    log.info("Starting %s (%s)", job, scope or "all")
    try:
        yield tracker
    except Exception as exc:
        session.rollback()
        run.status = IngestStatus.FAILED
        tracker.notes.append(f"error: {exc}")
        raise
    else:
        if tracker.failed == 0:
            run.status = IngestStatus.SUCCESS
        elif tracker.ok > 0:
            run.status = IngestStatus.PARTIAL
        else:
            run.status = IngestStatus.FAILED
    finally:
        run.items_ok = tracker.ok
        run.items_failed = tracker.failed
        run.message = "\n".join(tracker.notes)[-4000:] or None
        run.finished_at = dt.datetime.now(dt.UTC)
        session.add(run)
        session.commit()
        log.info("Finished %s: %s (ok=%d failed=%d)", job, run.status, tracker.ok, tracker.failed)
