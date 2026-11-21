"""Provider-agnostic types and interfaces.

Pipelines depend only on these, so a paid provider can replace or complement the
free ones without touching pipeline code.
"""

import datetime as dt
from dataclasses import dataclass, field
from typing import Protocol

# Currencies some providers quote in hundredths of the main unit.
SUBUNIT_CURRENCIES: dict[str, tuple[str, int]] = {
    "ILA": ("ILS", 100),  # Israeli agorot
    "GBp": ("GBP", 100),  # British pence
    "GBX": ("GBP", 100),
    "ZAc": ("ZAR", 100),  # South African cents
}


def normalize_currency(code: str) -> tuple[str, int]:
    """Map a quoted currency to (main currency, divisor). ``ILA`` -> (``ILS``, 100)."""
    return SUBUNIT_CURRENCIES.get(code, (code.upper(), 1))


@dataclass(frozen=True)
class Listing:
    """A security as discovered by a provider's universe/screener endpoint.

    Prices are in the main currency unit (already divided by ``price_divisor``).
    """

    provider_symbol: str
    symbol: str
    exchange_mic: str
    name: str
    currency: str
    price_divisor: int
    sector: str | None
    price: float | None = None
    market_cap: float | None = None
    shares_outstanding: float | None = None
    avg_volume_3m: float | None = None
    trailing_pe: float | None = None
    price_to_book: float | None = None
    dividend_yield: float | None = None
    first_trade_date: dt.date | None = None


@dataclass(frozen=True)
class Bar:
    """Daily bar in the provider's quoted units (not yet divided by any price divisor)."""

    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: int | None


@dataclass(frozen=True)
class Split:
    ex_date: dt.date
    ratio: float  # new shares per old share, e.g. 4.0 for a 4-for-1 split


@dataclass(frozen=True)
class Dividend:
    ex_date: dt.date
    amount: float  # per share, in the provider's quoted units


@dataclass
class PriceHistory:
    bars: list[Bar] = field(default_factory=list)
    splits: list[Split] = field(default_factory=list)
    dividends: list[Dividend] = field(default_factory=list)


class ProviderError(Exception):
    """A provider request failed (network, rate limit, unexpected payload)."""


class UniverseProvider(Protocol):
    name: str

    def supports_exchange(self, exchange_mic: str) -> bool: ...

    def list_equities(
        self, exchange_mic: str, sectors: list[str], min_market_cap: float
    ) -> list[Listing]:
        """Equities listed on the exchange with market cap (listing currency) above a floor."""
        ...


class PriceProvider(Protocol):
    name: str

    def daily_history(
        self, provider_symbols: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, PriceHistory]:
        """Daily bars, splits and dividends from ``start`` to ``end`` (inclusive, or today).

        Symbols with no data are omitted from the result.
        """
        ...

    def fx_to_usd(
        self, currencies: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, list[tuple[dt.date, float]]]:
        """Daily rates as units of each currency per 1 USD."""
        ...


@dataclass(frozen=True)
class Fact:
    """One standardized fundamentals value (see ``app.fundamentals.metrics``)."""

    metric: str
    period_type: str  # "FY" or "Q"
    period_end: dt.date
    value: float
    unit: str  # currency code, "shares", or "<CCY>/shares"
    known_since: dt.date  # filing date, or the date we first saw it if the source has none
    period_start: dt.date | None = None
    fiscal_year: int | None = None
    fiscal_period: str | None = None  # FY, Q1..Q4
    form: str | None = None  # e.g. 10-K, 10-Q, 20-F


@dataclass(frozen=True)
class Profile:
    """Company profile details from a provider."""

    country: str | None = None  # country name as the provider spells it
    sector: str | None = None
    industry: str | None = None
    reporting_currency: str | None = None


class FundamentalsProvider(Protocol):
    name: str

    def fundamentals(self, external_symbol: str) -> tuple[Profile | None, list[Fact]]:
        """Profile (if the source has one) and standardized facts for one company."""
        ...
