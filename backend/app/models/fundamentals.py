"""Standardized company fundamentals, stored point-in-time."""

import datetime as dt

from sqlalchemy import Double, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialFact(Base):
    """One value of a standard metric (see ``app.fundamentals.metrics``) for one period.

    A new row is stored only when a value first appears or changes, with the date it became
    known (SEC filing date, or the fetch date for sources without one). The latest value for
    a period is the row with the greatest ``known_since``; restatements stay in history.
    Facts are attached to the company's primary listing.
    """

    __tablename__ = "financial_facts"
    __table_args__ = (
        UniqueConstraint(
            "security_id", "source", "metric", "period_type", "period_end", "known_since"
        ),
        Index("ix_financial_facts_lookup", "security_id", "period_type", "metric", "period_end"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(16))
    metric: Mapped[str] = mapped_column(String(40))
    period_type: Mapped[str] = mapped_column(String(2), comment="FY or Q")
    period_start: Mapped[dt.date | None]
    period_end: Mapped[dt.date]
    fiscal_year: Mapped[int | None]
    fiscal_period: Mapped[str | None] = mapped_column(String(4))
    value: Mapped[float] = mapped_column(Double)
    unit: Mapped[str] = mapped_column(String(16), comment="Currency, 'shares' or 'CCY/shares'")
    known_since: Mapped[dt.date] = mapped_column(comment="Filing date, or first fetch date")
    form: Mapped[str | None] = mapped_column(String(16))
