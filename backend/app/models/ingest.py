"""Bookkeeping for data pipeline runs, used for monitoring."""

import datetime as dt
import enum

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class IngestStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(64), index=True)
    scope: Mapped[str | None] = mapped_column(String(200), comment="e.g. exchange MICs")
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[IngestStatus] = mapped_column(
        Enum(IngestStatus, name="ingest_status", values_callable=lambda e: [m.value for m in e]),
        default=IngestStatus.RUNNING,
    )
    items_ok: Mapped[int] = mapped_column(default=0)
    items_failed: Mapped[int] = mapped_column(default=0)
    message: Mapped[str | None] = mapped_column(Text)
