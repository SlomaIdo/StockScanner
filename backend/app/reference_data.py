"""Static reference data loaded by ``python -m app.seed``.

Exchanges cover the first target markets (US, Israel, Europe) plus the next wave
(Japan, Korea, Taiwan, Hong Kong).

Note: some exchanges quote prices in a currency sub-unit on Yahoo (London in pence,
GBp; Tel Aviv in agorot, ILA). The listing currency here is the main unit; the data
pipeline converts sub-unit quotes on ingest.
"""

from typing import TypedDict


class ExchangeSeed(TypedDict):
    mic: str
    name: str
    country_code: str
    timezone: str
    currency_code: str
    yahoo_suffix: str | None


CURRENCIES: dict[str, str] = {
    "USD": "US Dollar",
    "ILS": "Israeli New Shekel",
    "EUR": "Euro",
    "GBP": "Pound Sterling",
    "CHF": "Swiss Franc",
    "SEK": "Swedish Krona",
    "DKK": "Danish Krone",
    "NOK": "Norwegian Krone",
    "PLN": "Polish Zloty",
    "JPY": "Japanese Yen",
    "KRW": "South Korean Won",
    "TWD": "New Taiwan Dollar",
    "HKD": "Hong Kong Dollar",
}

EXCHANGES: list[ExchangeSeed] = [
    # United States
    {
        "mic": "XNYS",
        "name": "New York Stock Exchange",
        "country_code": "US",
        "timezone": "America/New_York",
        "currency_code": "USD",
        "yahoo_suffix": None,
    },
    {
        "mic": "XNAS",
        "name": "Nasdaq",
        "country_code": "US",
        "timezone": "America/New_York",
        "currency_code": "USD",
        "yahoo_suffix": None,
    },
    {
        "mic": "XASE",
        "name": "NYSE American",
        "country_code": "US",
        "timezone": "America/New_York",
        "currency_code": "USD",
        "yahoo_suffix": None,
    },
    # Israel
    {
        "mic": "XTAE",
        "name": "Tel Aviv Stock Exchange",
        "country_code": "IL",
        "timezone": "Asia/Jerusalem",
        "currency_code": "ILS",
        "yahoo_suffix": ".TA",
    },
    # Europe
    {
        "mic": "XLON",
        "name": "London Stock Exchange",
        "country_code": "GB",
        "timezone": "Europe/London",
        "currency_code": "GBP",
        "yahoo_suffix": ".L",
    },
    {
        "mic": "XETR",
        "name": "Deutsche Börse Xetra",
        "country_code": "DE",
        "timezone": "Europe/Berlin",
        "currency_code": "EUR",
        "yahoo_suffix": ".DE",
    },
    {
        "mic": "XPAR",
        "name": "Euronext Paris",
        "country_code": "FR",
        "timezone": "Europe/Paris",
        "currency_code": "EUR",
        "yahoo_suffix": ".PA",
    },
    {
        "mic": "XAMS",
        "name": "Euronext Amsterdam",
        "country_code": "NL",
        "timezone": "Europe/Amsterdam",
        "currency_code": "EUR",
        "yahoo_suffix": ".AS",
    },
    {
        "mic": "XBRU",
        "name": "Euronext Brussels",
        "country_code": "BE",
        "timezone": "Europe/Brussels",
        "currency_code": "EUR",
        "yahoo_suffix": ".BR",
    },
    {
        "mic": "XLIS",
        "name": "Euronext Lisbon",
        "country_code": "PT",
        "timezone": "Europe/Lisbon",
        "currency_code": "EUR",
        "yahoo_suffix": ".LS",
    },
    {
        "mic": "XDUB",
        "name": "Euronext Dublin",
        "country_code": "IE",
        "timezone": "Europe/Dublin",
        "currency_code": "EUR",
        "yahoo_suffix": ".IR",
    },
    {
        "mic": "XMIL",
        "name": "Borsa Italiana",
        "country_code": "IT",
        "timezone": "Europe/Rome",
        "currency_code": "EUR",
        "yahoo_suffix": ".MI",
    },
    {
        "mic": "XMAD",
        "name": "Bolsa de Madrid",
        "country_code": "ES",
        "timezone": "Europe/Madrid",
        "currency_code": "EUR",
        "yahoo_suffix": ".MC",
    },
    {
        "mic": "XSWX",
        "name": "SIX Swiss Exchange",
        "country_code": "CH",
        "timezone": "Europe/Zurich",
        "currency_code": "CHF",
        "yahoo_suffix": ".SW",
    },
    {
        "mic": "XSTO",
        "name": "Nasdaq Stockholm",
        "country_code": "SE",
        "timezone": "Europe/Stockholm",
        "currency_code": "SEK",
        "yahoo_suffix": ".ST",
    },
    {
        "mic": "XCSE",
        "name": "Nasdaq Copenhagen",
        "country_code": "DK",
        "timezone": "Europe/Copenhagen",
        "currency_code": "DKK",
        "yahoo_suffix": ".CO",
    },
    {
        "mic": "XHEL",
        "name": "Nasdaq Helsinki",
        "country_code": "FI",
        "timezone": "Europe/Helsinki",
        "currency_code": "EUR",
        "yahoo_suffix": ".HE",
    },
    {
        "mic": "XOSL",
        "name": "Oslo Børs",
        "country_code": "NO",
        "timezone": "Europe/Oslo",
        "currency_code": "NOK",
        "yahoo_suffix": ".OL",
    },
    {
        "mic": "XWBO",
        "name": "Wiener Börse",
        "country_code": "AT",
        "timezone": "Europe/Vienna",
        "currency_code": "EUR",
        "yahoo_suffix": ".VI",
    },
    {
        "mic": "XWAR",
        "name": "Warsaw Stock Exchange",
        "country_code": "PL",
        "timezone": "Europe/Warsaw",
        "currency_code": "PLN",
        "yahoo_suffix": ".WA",
    },
    # Asia (next wave)
    {
        "mic": "XTKS",
        "name": "Tokyo Stock Exchange",
        "country_code": "JP",
        "timezone": "Asia/Tokyo",
        "currency_code": "JPY",
        "yahoo_suffix": ".T",
    },
    {
        "mic": "XKRX",
        "name": "Korea Exchange",
        "country_code": "KR",
        "timezone": "Asia/Seoul",
        "currency_code": "KRW",
        "yahoo_suffix": ".KS",
    },
    {
        "mic": "XTAI",
        "name": "Taiwan Stock Exchange",
        "country_code": "TW",
        "timezone": "Asia/Taipei",
        "currency_code": "TWD",
        "yahoo_suffix": ".TW",
    },
    {
        "mic": "XHKG",
        "name": "Hong Kong Exchanges",
        "country_code": "HK",
        "timezone": "Asia/Hong_Kong",
        "currency_code": "HKD",
        "yahoo_suffix": ".HK",
    },
]

# Internal top-level sector taxonomy. Aligned with Yahoo Finance's sector names so
# global data maps directly; SEC SIC codes are mapped onto these during ingest.
SECTORS: list[str] = [
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
]
