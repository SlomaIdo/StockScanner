"""Securities and their identifiers across data providers."""

import datetime as dt
import enum

from sqlalchemy import CHAR, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.reference import Exchange, Industry, Sector


class SecurityType(enum.StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    FUND = "fund"
    INDEX = "index"


class Security(Base):
    """A single listing: one instrument on one exchange.

    The same company listed on two exchanges is two securities that share an ISIN
    (or a FIGI share-class id), which lets us link dual listings.
    """

    __tablename__ = "securities"
    __table_args__ = (UniqueConstraint("exchange_id", "symbol"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id"))
    symbol: Mapped[str] = mapped_column(String(32), comment="Ticker as used on the exchange")
    name: Mapped[str] = mapped_column(String(300))
    security_type: Mapped[SecurityType] = mapped_column(
        Enum(SecurityType, name="security_type", values_callable=lambda e: [m.value for m in e])
    )
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))
    country_code: Mapped[str | None] = mapped_column(CHAR(2), comment="Country of domicile")
    isin: Mapped[str | None] = mapped_column(CHAR(12), index=True)
    figi: Mapped[str | None] = mapped_column(CHAR(12), unique=True)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), index=True)
    industry_id: Mapped[int | None] = mapped_column(ForeignKey("industries.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
    listed_on: Mapped[dt.date | None]
    delisted_on: Mapped[dt.date | None]
    last_seen_on: Mapped[dt.date | None] = mapped_column(
        comment="Last date the security appeared in a universe refresh"
    )
    primary_security_id: Mapped[int | None] = mapped_column(
        ForeignKey("securities.id", ondelete="SET NULL"),
        index=True,
        comment="For dual listings: the company's most liquid listing. NULL = this is primary",
    )

    exchange: Mapped[Exchange] = relationship()
    primary_listing: Mapped["Security | None"] = relationship(remote_side=[id])
    sector: Mapped[Sector | None] = relationship()
    industry: Mapped[Industry | None] = relationship()
    identifiers: Mapped[list["SecurityIdentifier"]] = relationship(
        back_populates="security", cascade="all, delete-orphan"
    )


class SecurityIdentifier(Base):
    """How a data provider refers to a security, e.g. provider='yahoo', symbol='TEVA.TA'."""

    __tablename__ = "security_identifiers"
    __table_args__ = (
        UniqueConstraint("provider", "external_symbol"),
        UniqueConstraint("security_id", "provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    external_symbol: Mapped[str] = mapped_column(String(64))
    price_divisor: Mapped[int] = mapped_column(
        default=1,
        server_default="1",
        comment="Provider quotes in a currency sub-unit (e.g. agorot, pence): divide by this",
    )

    security: Mapped[Security] = relationship(back_populates="identifiers")
