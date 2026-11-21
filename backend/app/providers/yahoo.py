"""Yahoo Finance adapter (via ``yfinance``). Free, unofficial and rate-limited: personal use."""

import datetime as dt
import logging
import math
import time
from typing import Any

import pandas as pd
import yfinance as yf

from app.fundamentals.metrics import METRICS, OUTFLOW_METRICS, UnitKind
from app.providers.base import (
    Bar,
    Dividend,
    Fact,
    Listing,
    PriceHistory,
    Profile,
    ProviderError,
    Split,
    normalize_currency,
)

log = logging.getLogger(__name__)

# Our exchange MIC -> Yahoo screener exchange codes.
EXCHANGE_CODES: dict[str, list[str]] = {
    "XNAS": ["NMS", "NGM", "NCM"],
    "XNYS": ["NYQ"],
    "XASE": ["ASE"],
    "XTAE": ["TLV"],
    "XLON": ["LSE"],
    "XETR": ["GER"],
    "XPAR": ["PAR"],
    "XAMS": ["AMS"],
    "XBRU": ["BRU"],
    "XLIS": ["LIS"],
    "XDUB": ["ISE"],
    "XMIL": ["MIL"],
    "XMAD": ["MCE"],
    "XSWX": ["EBS"],
    "XSTO": ["STO"],
    "XCSE": ["CPH"],
    "XHEL": ["HEL"],
    "XOSL": ["OSL"],
    "XWBO": ["VIE"],
    "XWAR": ["WSE"],
    "XTKS": ["JPX"],
    "XKRX": ["KSC"],
    "XTAI": ["TAI"],
    "XHKG": ["HKG"],
}

# Ticker suffix Yahoo appends per exchange (US listings have none).
SUFFIXES: dict[str, str] = {
    "XTAE": ".TA",
    "XLON": ".L",
    "XETR": ".DE",
    "XPAR": ".PA",
    "XAMS": ".AS",
    "XBRU": ".BR",
    "XLIS": ".LS",
    "XDUB": ".IR",
    "XMIL": ".MI",
    "XMAD": ".MC",
    "XSWX": ".SW",
    "XSTO": ".ST",
    "XCSE": ".CO",
    "XHEL": ".HE",
    "XOSL": ".OL",
    "XWBO": ".VI",
    "XWAR": ".WA",
    "XTKS": ".T",
    "XKRX": ".KS",
    "XTAI": ".TW",
    "XHKG": ".HK",
}

SCREEN_PAGE_SIZE = 250

# Standard metric -> Yahoo statement row labels, in priority order.
STATEMENT_ROWS: dict[str, list[str]] = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "cost_of_revenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "gross_profit": ["Gross Profit"],
    "rd_expense": ["Research And Development"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "interest_expense": ["Interest Expense"],
    "income_tax": ["Tax Provision"],
    "net_income": ["Net Income Common Stockholders", "Net Income"],
    "eps_basic": ["Basic EPS"],
    "eps_diluted": ["Diluted EPS"],
    "shares_diluted": ["Diluted Average Shares"],
    "total_assets": ["Total Assets"],
    "current_assets": ["Current Assets"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "total_liabilities": ["Total Liabilities Net Minority Interest"],
    "current_liabilities": ["Current Liabilities"],
    "long_term_debt": ["Long Term Debt"],
    "total_debt": ["Total Debt"],
    "total_equity": ["Stockholders Equity", "Common Stock Equity"],
    "shares_outstanding": ["Ordinary Shares Number", "Share Issued"],
    "operating_cash_flow": ["Operating Cash Flow"],
    "capex": ["Capital Expenditure"],
    "free_cash_flow": ["Free Cash Flow"],
    "dividends_paid": ["Cash Dividends Paid", "Common Stock Dividend Paid"],
    "buybacks": ["Repurchase Of Capital Stock", "Common Stock Payments"],
}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def native_symbol(provider_symbol: str, suffix: str | None) -> str:
    """``BRK-B`` -> ``BRK.B``; ``TEVA.TA`` -> ``TEVA`` (given suffix ``.TA``)."""
    symbol = provider_symbol
    if suffix and symbol.endswith(suffix):
        symbol = symbol[: -len(suffix)]
    return symbol.replace("-", ".")


def parse_screen_quote(
    quote: dict[str, Any], exchange_mic: str, suffix: str | None, sector: str | None
) -> Listing | None:
    """Turn a Yahoo screener quote into a Listing. Returns None for unusable rows."""
    symbol = quote.get("symbol")
    raw_currency = quote.get("currency")
    if not symbol or not raw_currency or quote.get("quoteType") != "EQUITY":
        return None
    currency, divisor = normalize_currency(raw_currency)
    price = _num(quote.get("regularMarketPrice"))
    first_trade_ms = quote.get("firstTradeDateMilliseconds")
    return Listing(
        provider_symbol=symbol,
        symbol=native_symbol(symbol, suffix),
        exchange_mic=exchange_mic,
        name=quote.get("longName") or quote.get("shortName") or symbol,
        currency=currency,
        price_divisor=divisor,
        sector=sector,
        price=price / divisor if price is not None else None,
        # Yahoo reports market cap in the main currency unit even for sub-unit quotes.
        market_cap=_num(quote.get("marketCap")),
        shares_outstanding=_num(quote.get("sharesOutstanding")),
        avg_volume_3m=_num(quote.get("averageDailyVolume3Month")),
        trailing_pe=_num(quote.get("trailingPE")),
        price_to_book=_num(quote.get("priceToBook")),
        dividend_yield=_num(quote.get("trailingAnnualDividendYield")),
        first_trade_date=(
            dt.datetime.fromtimestamp(first_trade_ms / 1000, tz=dt.UTC).date()
            if isinstance(first_trade_ms, int | float)
            else None
        ),
    )


def parse_history_frame(frame: pd.DataFrame) -> PriceHistory:
    """Parse one ticker's ``yf.download`` frame (Open/High/Low/Close/Adj Close/Volume/...)."""
    history = PriceHistory()
    if frame.empty or "Close" not in frame:
        return history
    for ts, row in frame.iterrows():
        day = pd.Timestamp(ts).date()  # type: ignore[arg-type]
        close = _num(row.get("Close"))
        if close is not None and close > 0:
            volume = _num(row.get("Volume"))
            history.bars.append(
                Bar(
                    date=day,
                    open=_num(row.get("Open")),
                    high=_num(row.get("High")),
                    low=_num(row.get("Low")),
                    close=close,
                    adj_close=_num(row.get("Adj Close")),
                    volume=int(volume) if volume is not None else None,
                )
            )
        split = _num(row.get("Stock Splits"))
        if split:
            history.splits.append(Split(ex_date=day, ratio=split))
        dividend = _num(row.get("Dividends"))
        if dividend:
            history.dividends.append(Dividend(ex_date=day, amount=dividend))
    return history


def parse_statement_frames(
    frames: list[tuple[str, pd.DataFrame]], currency: str, known_since: dt.date
) -> list[Fact]:
    """Map Yahoo statement frames (rows = line items, columns = period ends) to facts.

    ``frames`` holds (period type, frame) pairs, e.g. ("FY", ticker.income_stmt). Yahoo has no
    filing dates, so ``known_since`` is the date we fetched the data.
    """
    facts: list[Fact] = []
    for period_type, frame in frames:
        if frame is None or frame.empty:
            continue
        for metric, labels in STATEMENT_ROWS.items():
            label = next((lbl for lbl in labels if lbl in frame.index), None)
            if label is None:
                continue
            kind = METRICS[metric].unit
            unit = {
                UnitKind.MONEY: currency,
                UnitKind.PER_SHARE: f"{currency}/shares",
                UnitKind.SHARES: "shares",
            }[kind]
            for column, raw in frame.loc[label].items():
                value = _num(raw)
                if value is None:
                    continue
                if metric in OUTFLOW_METRICS:
                    value = abs(value)
                facts.append(
                    Fact(
                        metric=metric,
                        period_type=period_type,
                        period_end=pd.Timestamp(column).date(),  # type: ignore[arg-type]
                        value=value,
                        unit=unit,
                        known_since=known_since,
                    )
                )
    return facts


def _ticker_frame(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    sub = frame.xs(ticker, axis=1, level=0)
    assert isinstance(sub, pd.DataFrame)
    return sub.dropna(how="all")


class YahooProvider:
    name = "yahoo"

    def __init__(self, request_pause: float = 0.3, chunk_size: int = 50) -> None:
        self.request_pause = request_pause
        self.chunk_size = chunk_size

    # -- universe -------------------------------------------------------------

    def supports_exchange(self, exchange_mic: str) -> bool:
        return exchange_mic in EXCHANGE_CODES

    def list_equities(
        self,
        exchange_mic: str,
        sectors: list[str],
        min_market_cap: float,
    ) -> list[Listing]:
        suffix = SUFFIXES.get(exchange_mic)
        listings: dict[str, Listing] = {}
        for code in EXCHANGE_CODES[exchange_mic]:
            for sector in sectors:
                query = yf.EquityQuery(
                    "and",
                    [
                        yf.EquityQuery("eq", ["exchange", code]),
                        yf.EquityQuery("eq", ["sector", sector]),
                        yf.EquityQuery("gt", ["intradaymarketcap", min_market_cap]),
                    ],
                )
                for quote in self._screen_all(query):
                    listing = parse_screen_quote(quote, exchange_mic, suffix, sector)
                    if listing is not None:
                        listings.setdefault(listing.provider_symbol, listing)
        return list(listings.values())

    def _screen_all(self, query: Any) -> list[dict[str, Any]]:
        quotes: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                result = yf.screen(
                    query,
                    offset=offset,
                    size=SCREEN_PAGE_SIZE,
                    sortField="intradaymarketcap",
                    sortAsc=False,
                )
            except Exception as exc:
                raise ProviderError(f"Yahoo screener failed: {exc}") from exc
            time.sleep(self.request_pause)
            page = result.get("quotes", [])
            quotes.extend(page)
            offset += len(page)
            if not page or offset >= int(result.get("total", 0)):
                return quotes

    # -- prices ---------------------------------------------------------------

    def daily_history(
        self, provider_symbols: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, PriceHistory]:
        out: dict[str, PriceHistory] = {}
        # yfinance's ``end`` is exclusive.
        end_exclusive = (end or dt.date.today()) + dt.timedelta(days=1)
        for i in range(0, len(provider_symbols), self.chunk_size):
            chunk = provider_symbols[i : i + self.chunk_size]
            frame = self._download(chunk, start, end_exclusive)
            for symbol in chunk:
                if symbol not in frame.columns.get_level_values(0):
                    continue
                history = parse_history_frame(_ticker_frame(frame, symbol))
                if history.bars:
                    out[symbol] = history
            time.sleep(self.request_pause)
        return out

    def fx_to_usd(
        self, currencies: list[str], start: dt.date, end: dt.date | None = None
    ) -> dict[str, list[tuple[dt.date, float]]]:
        wanted = {c: f"USD{c}=X" for c in currencies if c != "USD"}
        end_exclusive = (end or dt.date.today()) + dt.timedelta(days=1)
        frame = self._download(list(wanted.values()), start, end_exclusive)
        out: dict[str, list[tuple[dt.date, float]]] = {}
        for currency, ticker in wanted.items():
            if ticker not in frame.columns.get_level_values(0):
                continue
            history = parse_history_frame(_ticker_frame(frame, ticker))
            out[currency] = [(b.date, b.close) for b in history.bars]
        return out

    # -- fundamentals -----------------------------------------------------------

    def fundamentals(self, external_symbol: str) -> tuple[Profile | None, list[Fact]]:
        """Profile plus ~4 years of annual and ~6 quarters of quarterly statements."""
        profile = self.profile(external_symbol)
        if profile is None or not profile.reporting_currency:
            return profile, []
        ticker = yf.Ticker(external_symbol)
        try:
            frames = [
                ("FY", ticker.income_stmt),
                ("FY", ticker.balance_sheet),
                ("FY", ticker.cashflow),
                ("Q", ticker.quarterly_income_stmt),
                ("Q", ticker.quarterly_balance_sheet),
                ("Q", ticker.quarterly_cashflow),
            ]
        except Exception as exc:
            raise ProviderError(f"Yahoo statements failed for {external_symbol}: {exc}") from exc
        time.sleep(self.request_pause)
        currency, _ = normalize_currency(profile.reporting_currency)
        return profile, parse_statement_frames(frames, currency, dt.date.today())

    def profile(self, external_symbol: str) -> Profile | None:
        try:
            info = yf.Ticker(external_symbol).info
        except Exception as exc:
            raise ProviderError(f"Yahoo profile failed for {external_symbol}: {exc}") from exc
        time.sleep(self.request_pause)
        if not info or not isinstance(info, dict) or len(info) < 3:
            return None
        return Profile(
            country=info.get("country"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            reporting_currency=info.get("financialCurrency"),
        )

    def _download(self, tickers: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        try:
            frame = yf.download(
                tickers,
                start=start.isoformat(),
                end=end.isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=True,
                group_by="ticker",
                threads=True,
                progress=False,
            )
        except Exception as exc:
            raise ProviderError(f"Yahoo download failed: {exc}") from exc
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return pd.DataFrame(columns=pd.MultiIndex.from_tuples([], names=["Ticker", "Price"]))
        return frame
