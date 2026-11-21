"""In-memory provider used by pipeline tests (no network)."""

import datetime as dt
from dataclasses import dataclass, field

from app.providers.base import Listing, PriceHistory


@dataclass
class FakeProvider:
    name: str = "fake"
    listings: dict[str, list[Listing]] = field(default_factory=dict)
    histories: dict[str, PriceHistory] = field(default_factory=dict)
    fx: dict[str, list[tuple[dt.date, float]]] = field(default_factory=dict)
    history_calls: list[tuple[tuple[str, ...], dt.date]] = field(default_factory=list)

    def supports_exchange(self, exchange_mic: str) -> bool:
        return True

    def list_equities(
        self, exchange_mic: str, sectors: list[str], min_market_cap: float
    ) -> list[Listing]:
        return [
            item
            for item in self.listings.get(exchange_mic, [])
            if (item.market_cap or 0) > min_market_cap
        ]

    def daily_history(
        self, provider_symbols: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, PriceHistory]:
        self.history_calls.append((tuple(provider_symbols), start))
        out = {}
        for symbol in provider_symbols:
            history = self.histories.get(symbol)
            if history is None:
                continue
            out[symbol] = PriceHistory(
                bars=[b for b in history.bars if b.date >= start],
                splits=[s for s in history.splits if s.ex_date >= start],
                dividends=[d for d in history.dividends if d.ex_date >= start],
            )
        return out

    def fx_to_usd(
        self, currencies: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, list[tuple[dt.date, float]]]:
        return {c: [r for r in self.fx[c] if r[0] >= start] for c in currencies if c in self.fx}


def listing(
    symbol: str,
    mic: str,
    name: str,
    *,
    currency: str = "USD",
    divisor: int = 1,
    market_cap: float = 1e9,
    avg_volume: float = 1e6,
    price: float = 10.0,
    sector: str | None = "Technology",
) -> Listing:
    return Listing(
        provider_symbol=symbol,
        symbol=symbol.split(".")[0],
        exchange_mic=mic,
        name=name,
        currency=currency,
        price_divisor=divisor,
        sector=sector,
        price=price,
        market_cap=market_cap,
        avg_volume_3m=avg_volume,
    )
