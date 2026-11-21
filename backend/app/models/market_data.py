"""Time series: daily price bars, corporate actions and FX rates.

``daily_bars`` and ``fx_rates`` become TimescaleDB hypertables when the extension
is available (see the initial migration).
"""

import datetime as dt
import enum
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, Double, Enum, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyBar(Base):
    __tablename__ = "daily_bars"

    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), primary_key=True
    )
    # Separate index on date for cross-sectional queries (all securities on a day).
    date: Mapped[dt.date] = mapped_column(primary_key=True, index=True)
    open: Mapped[float | None] = mapped_column(Double)
    high: Mapped[float | None] = mapped_column(Double)
    low: Mapped[float | None] = mapped_column(Double)
    close: Mapped[float] = mapped_column(Double, comment="Raw close in listing currency")
    adj_close: Mapped[float | None] = mapped_column(
        Double, comment="Close adjusted for splits and dividends"
    )
    volume: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(32))


class CorporateActionType(enum.StrEnum):
    SPLIT = "split"
    DIVIDEND = "dividend"


class CorporateAction(Base):
    __tablename__ = "corporate_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), index=True
    )
    ex_date: Mapped[dt.date]
    action_type: Mapped[CorporateActionType] = mapped_column(
        Enum(
            CorporateActionType,
            name="corporate_action_type",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    value: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), comment="Split ratio (new/old) or dividend amount per share"
    )
    currency_code: Mapped[str | None] = mapped_column(ForeignKey("currencies.code"))
    source: Mapped[str] = mapped_column(String(32))


class FxRate(Base):
    """Daily FX rate: 1 unit of ``base`` = ``rate`` units of ``quote``."""

    __tablename__ = "fx_rates"

    base: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), primary_key=True)
    quote: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), primary_key=True)
    date: Mapped[dt.date] = mapped_column(primary_key=True)
    rate: Mapped[float] = mapped_column(Double)
    source: Mapped[str] = mapped_column(String(32))
