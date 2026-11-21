import datetime as dt

import numpy as np
import pandas as pd

from app.providers.base import normalize_currency
from app.providers.yahoo import native_symbol, parse_history_frame, parse_screen_quote


def test_normalize_currency_subunits() -> None:
    assert normalize_currency("ILA") == ("ILS", 100)
    assert normalize_currency("GBp") == ("GBP", 100)
    assert normalize_currency("usd") == ("USD", 1)


def test_native_symbol() -> None:
    assert native_symbol("TEVA.TA", ".TA") == "TEVA"
    assert native_symbol("BRK-B", None) == "BRK.B"
    assert native_symbol("BT-A.L", ".L") == "BT.A"


def test_parse_screen_quote_converts_subunit_price() -> None:
    quote = {
        "symbol": "TEVA.TA",
        "quoteType": "EQUITY",
        "currency": "ILA",
        "longName": "Teva Pharmaceutical Industries Limited",
        "regularMarketPrice": 13210.0,
        "marketCap": 154_137_804_800,
        "averageDailyVolume3Month": 900_000,
        "trailingPE": 25.5,
        "firstTradeDateMilliseconds": 1029135000000,
    }
    listing = parse_screen_quote(quote, "XTAE", ".TA", "Healthcare")
    assert listing is not None
    assert listing.symbol == "TEVA"
    assert listing.currency == "ILS"
    assert listing.price_divisor == 100
    assert listing.price == 132.10
    assert listing.market_cap == 154_137_804_800  # already in shekels
    assert listing.first_trade_date == dt.date(2002, 8, 12)


def test_parse_screen_quote_skips_non_equity() -> None:
    assert (
        parse_screen_quote(
            {"symbol": "X", "currency": "USD", "quoteType": "ETF"}, "XNYS", None, None
        )
        is None
    )
    assert parse_screen_quote({"symbol": "X", "quoteType": "EQUITY"}, "XNYS", None, None) is None


def test_parse_history_frame() -> None:
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0, np.nan],
            "High": [10.5, 11.5, np.nan],
            "Low": [9.5, 10.5, np.nan],
            "Close": [10.2, 11.2, np.nan],
            "Adj Close": [10.0, 11.0, np.nan],
            "Volume": [1000.0, 2000.0, np.nan],
            "Dividends": [0.0, 0.25, 0.0],
            "Stock Splits": [0.0, 2.0, 0.0],
        },
        index=pd.to_datetime(["2026-11-18", "2026-11-19", "2026-11-20"]),
    )
    history = parse_history_frame(frame)
    assert [b.date for b in history.bars] == [dt.date(2026, 11, 18), dt.date(2026, 11, 19)]
    assert history.bars[1].volume == 2000
    assert history.splits[0].ratio == 2.0
    assert history.dividends[0].amount == 0.25
