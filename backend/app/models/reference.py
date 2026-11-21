"""Reference data: currencies, exchanges and the unified sector taxonomy."""

from sqlalchemy import CHAR, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True, comment="ISO 4217 code")
    name: Mapped[str] = mapped_column(String(100))


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(primary_key=True)
    mic: Mapped[str] = mapped_column(String(10), unique=True, comment="ISO 10383 market code")
    name: Mapped[str] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(CHAR(2), comment="ISO 3166-1 alpha-2")
    timezone: Mapped[str] = mapped_column(String(64), comment="IANA timezone, e.g. Asia/Jerusalem")
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"))
    yahoo_suffix: Mapped[str | None] = mapped_column(
        String(10), comment="Ticker suffix on Yahoo Finance, e.g. '.TA'"
    )

    currency: Mapped[Currency] = relationship()


class Sector(Base):
    """Top level of the internal sector taxonomy (GICS is proprietary, so we keep our own)."""

    __tablename__ = "sectors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    industries: Mapped[list["Industry"]] = relationship(back_populates="sector")


class Industry(Base):
    __tablename__ = "industries"
    __table_args__ = (UniqueConstraint("sector_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sectors.id"))
    name: Mapped[str] = mapped_column(String(150))

    sector: Mapped[Sector] = relationship(back_populates="industries")
