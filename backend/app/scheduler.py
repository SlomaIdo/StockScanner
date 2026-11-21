"""Nightly scheduler: runs each market group's pipeline after its exchanges close.

Usage: ``python -m app.scheduler`` (runs in the foreground; Docker runs it as a service).
"""

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.cli import run_nightly
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.pipeline.universe import GROUPS

log = logging.getLogger(__name__)


def _job(group: str) -> None:
    try:
        run_nightly([group])
    except Exception:
        # Keep the scheduler alive; the failure is recorded in ingest_runs.
        log.exception("Nightly job for %s failed", group)


def main() -> None:
    configure_logging(get_settings().log_level)
    scheduler = BlockingScheduler()
    for group in GROUPS.values():
        if not group.enabled:
            continue
        hour, minute = group.schedule_time.split(":")
        scheduler.add_job(
            _job,
            CronTrigger(
                day_of_week="mon-fri", hour=hour, minute=minute, timezone=group.schedule_timezone
            ),
            args=[group.name],
            id=f"nightly-{group.name}",
            misfire_grace_time=3600,
            coalesce=True,
        )
        log.info("Scheduled %s at %s %s", group.name, group.schedule_time, group.schedule_timezone)
    scheduler.start()


if __name__ == "__main__":
    main()
