# StockScanner data report

Generated 2026-11-21 19:40 UTC from the live database. Regenerate any time with `stockscanner report`.

## At a glance

|  |  |
| --- | --- |
| Active stocks | 5,037 |
|   of which dual listings | 111 |
|   of which in grace period | 30 (not picked in the latest refresh; kept active for 14 days so a flaky day doesn't drop them) |
| Inactive (delisted / dropped) | 293 |
| Exchanges with data | 20 |
| Daily price bars | 11,078,313 |
| Price history | 2016-11-23 → 2026-11-20 |
| Latest trading day loaded | 2026-11-20 |
| Splits / dividends recorded | 1,054 / 88,694 |
| Quote snapshots (market cap, P/E, …) | 5,330 over 1 day(s), latest 2026-11-21 |
| FX currencies vs USD | 12, latest 2026-11-21 |
| Data source | Yahoo Finance (free, delayed, personal use) |

## Freshness: when was it updated

| Job | Last run status | Scope | Started (UTC) | OK / failed | Last success (UTC) |
| --- | --- | --- | --- | --- | --- |
| backfill | success | all | 2026-11-21 19:03 | 1 / 0 | 2026-11-21 19:03 |
| fundamentals:sec | partial | 2561 companies | 2026-11-21 19:17 | 2419 / 142 | 2026-11-21 19:39 |
| fundamentals:yahoo | running | 1967 companies | 2026-11-21 19:13 | 0 / 0 | 2026-11-21 19:12 |
| fx | success | ILS,EUR,GBP,CHF,SEK,DKK,NOK,PLN,JPY,KRW, | 2026-11-21 18:21 | 12 / 0 | 2026-11-21 18:21 |
| profiles | success | 5 companies | 2026-11-21 19:12 | 5 / 0 | 2026-11-21 19:12 |
| universe | success | EU | 2026-11-21 19:02 | 16 / 0 | 2026-11-21 19:03 |

Nightly schedule (weekdays, run by the `scheduler` service):

| Group | Exchanges | Runs at (local time) | Universe rule | Enabled |
| --- | --- | --- | --- | --- |
| US | XNYS, XNAS, XASE | 18:30 America/New_York | top 3,000, market cap > $100.0M | yes |
| IL | XTAE | 18:30 Asia/Jerusalem | all, market cap > $1.0M | yes |
| EU | XLON, XETR, XPAR, XAMS, XBRU, XLIS, XDUB, XMIL, XMAD, XSWX, XSTO, XCSE, XHEL, XOSL, XWBO, XWAR | 19:00 Europe/Berlin | top 1,500, market cap > $100.0M | yes |
| ASIA | XTKS, XKRX, XTAI, XHKG | 18:30 Asia/Tokyo | top 1,500, market cap > $500.0M | no |

## Coverage by exchange

| Group | Exchange | MIC | Country | Ccy | Stocks | With prices | Bars | History from | Last bar | Avg years |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| US | New York Stock Exchange | XNYS | US | USD | 1,673 | 1,673 | 3,654,417 | 2016-11-23 | 2026-11-20 | 8.7 |
| US | Nasdaq | XNAS | US | USD | 1,315 | 1,315 | 2,633,842 | 2016-11-23 | 2026-11-20 | 8.0 |
| IL | Tel Aviv Stock Exchange | XTAE | IL | ILS | 507 | 507 | 815,513 | 2016-11-23 | 2026-11-20 | 7.9 |
| EU | London Stock Exchange | XLON | GB | GBP | 327 | 327 | 774,915 | 2016-11-23 | 2026-11-20 | 9.4 |
| EU | Nasdaq Stockholm | XSTO | SE | SEK | 183 | 183 | 411,272 | 2016-11-23 | 2026-11-20 | 8.9 |
| EU | Deutsche Börse Xetra | XETR | DE | EUR | 159 | 159 | 359,309 | 2016-11-23 | 2026-11-20 | 8.9 |
| EU | Euronext Paris | XPAR | FR | EUR | 152 | 152 | 372,106 | 2016-11-23 | 2026-11-20 | 9.6 |
| EU | SIX Swiss Exchange | XSWX | CH | CHF | 141 | 141 | 315,847 | 2016-11-23 | 2026-11-20 | 8.9 |
| EU | Borsa Italiana | XMIL | IT | EUR | 93 | 93 | 212,304 | 2016-11-23 | 2026-11-20 | 9.0 |
| EU | Oslo Børs | XOSL | NO | NOK | 74 | 74 | 150,083 | 2016-11-23 | 2026-11-20 | 8.1 |
| EU | Bolsa de Madrid | XMAD | ES | EUR | 68 | 68 | 156,604 | 2016-11-23 | 2026-11-20 | 9.0 |
| EU | Euronext Amsterdam | XAMS | NL | EUR | 59 | 59 | 123,519 | 2016-11-23 | 2026-11-20 | 8.2 |
| EU | Warsaw Stock Exchange | XWAR | PL | PLN | 48 | 48 | 113,864 | 2016-11-23 | 2026-11-20 | 9.3 |
| EU | Nasdaq Helsinki | XHEL | FI | EUR | 48 | 48 | 107,812 | 2016-11-23 | 2026-11-20 | 8.9 |
| EU | Nasdaq Copenhagen | XCSE | DK | DKK | 45 | 45 | 105,936 | 2016-11-23 | 2026-11-20 | 9.4 |
| EU | Euronext Brussels | XBRU | BE | EUR | 43 | 43 | 102,137 | 2016-11-23 | 2026-11-20 | 9.3 |
| US | NYSE American | XASE | US | USD | 42 | 42 | 86,351 | 2016-11-23 | 2026-11-20 | 8.2 |
| EU | Wiener Börse | XWBO | AT | EUR | 34 | 34 | 77,625 | 2016-11-23 | 2026-11-20 | 9.0 |
| EU | Euronext Lisbon | XLIS | PT | EUR | 13 | 13 | 33,254 | 2016-11-23 | 2026-11-20 | 10.0 |
| EU | Euronext Dublin | XDUB | IE | EUR | 13 | 13 | 31,973 | 2016-11-23 | 2026-11-20 | 9.7 |

Stocks per group: **US** 3,030, **IL** 507, **EU** 1,500.

## Stocks by sector and market group

| Sector | US | IL | EU | Total |
| --- | ---: | ---: | ---: | ---: |
| Basic Materials | 175 | 18 | 101 | 294 |
| Communication Services | 132 | 10 | 72 | 214 |
| Consumer Cyclical | 293 | 46 | 159 | 498 |
| Consumer Defensive | 129 | 36 | 92 | 257 |
| Energy | 170 | 22 | 53 | 245 |
| Financial Services | 616 | 63 | 299 | 978 |
| Healthcare | 444 | 46 | 134 | 624 |
| Industrials | 405 | 79 | 337 | 821 |
| Real Estate | 151 | 87 | 101 | 339 |
| Technology | 432 | 79 | 100 | 611 |
| Utilities | 83 | 21 | 52 | 156 |

## Largest companies per group

Includes dual listings, marked with the company's most liquid listing (e.g. ASML in Amsterdam trades less than on Nasdaq, so Nasdaq is its primary).

**US**

| # | Symbol | Exchange | Company | Sector | Market cap | Note |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | AAPL | XNAS | Apple Inc. | Technology | $5.0T |  |
| 2 | MSFT | XNAS | Microsoft Corporation | Technology | $3.6T |  |
| 3 | GOOGL | XNAS | Alphabet Inc. | Communication Services | $3.3T |  |
| 4 | GOOG | XNAS | Alphabet Inc. | Communication Services | $3.2T |  |
| 5 | NVDA | XNAS | NVIDIA Corporation | Technology | $3.0T |  |
| 6 | AMZN | XNAS | Amazon.com, Inc. | Consumer Cyclical | $2.7T |  |
| 7 | SPCX | XNAS | Space Exploration Technologies Corp. | Industrials | $1.7T |  |
| 8 | TSM | XNYS | Taiwan Semiconductor Manufacturing Compa | Technology | $1.7T |  |
| 9 | AVGO | XNAS | Broadcom Inc. | Technology | $1.5T |  |
| 10 | META | XNAS | Meta Platforms, Inc. | Communication Services | $1.4T |  |

**IL**

| # | Symbol | Exchange | Company | Sector | Market cap | Note |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | TEVA | XTAE | Teva Pharmaceutical Industries Limited | Healthcare | $46.7B | dual, primary XNYS:TEVA |
| 2 | ESLT | XTAE | Elbit Systems Ltd. | Industrials | $32.0B | dual, primary XNAS:ESLT |
| 3 | LUMI | XTAE | Bank Leumi le-Israel B.M. | Financial Services | $31.9B |  |
| 4 | POLI | XTAE | Bank Hapoalim B.M. | Financial Services | $28.1B |  |
| 5 | MZTF | XTAE | Mizrahi Tefahot Bank Ltd. | Financial Services | $16.1B |  |
| 6 | TSEM | XTAE | Tower Semiconductor Ltd. | Technology | $14.4B | dual, primary XNAS:TSEM |
| 7 | PHOE | XTAE | Phoenix Financial Ltd. | Financial Services | $12.7B |  |
| 8 | AZRG | XTAE | Azrieli Group Ltd. | Real Estate | $12.2B |  |
| 9 | HARL | XTAE | Harel Insurance Investments & Financial  | Financial Services | $10.9B |  |
| 10 | DSCT | XTAE | Israel Discount Bank Limited | Financial Services | $10.7B |  |

**EU**

| # | Symbol | Exchange | Company | Sector | Market cap | Note |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | ASML | XAMS | ASML Holding N.V. | Technology | $493.8B | dual, primary XNAS:ASML |
| 2 | RO | XSWX | Roche Holding AG | Healthcare | $380.0B |  |
| 3 | ROP | XSWX | Roche Holding AG | Healthcare | $374.5B |  |
| 4 | NOVN | XSWX | Novartis AG | Healthcare | $285.9B |  |
| 5 | HSBA | XLON | HSBC Holdings plc | Financial Services | $275.8B |  |
| 6 | AZN | XSTO | AstraZeneca PLC | Healthcare | $272.4B | dual, primary XNYS:AZN |
| 7 | AZN | XLON | AstraZeneca PLC | Healthcare | $272.1B | dual, primary XNYS:AZN |
| 8 | SHELL | XAMS | Shell plc | Energy | $265.2B | dual, primary XNYS:SHEL |
| 9 | SHEL | XLON | Shell plc | Energy | $264.0B | dual, primary XNYS:SHEL |
| 10 | NESN | XSWX | Nestlé S.A. | Consumer Defensive | $260.7B |  |

## Fundamentals (financial statements)

US companies come from SEC EDGAR (official filings, quarterly and annual, typically back to 2009, each value with its filing date). Other companies come from Yahoo (about 4 years annual and 6 quarters; dated by when we fetched them). Counts are per company (primary listings); dual listings use their primary's data.

| Source | Values stored | Companies | Latest value known since |
| --- | ---: | ---: | --- |
| sec | 2,634,999 | 2,840 | 2026-11-20 |
| yahoo | 89,345 | 548 | 2026-11-21 |

| Group | Companies | With SEC data | With Yahoo data | Without data | Country known | Industry known |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EU | 1,430 | 0 (0%) | 511 (36%) | 919 (64%) | 506 (35%) | 505 (35%) |
| US | 2,997 | 2,808 (94%) | 20 (1%) | 169 (6%) | 25 (1%) | 25 (1%) |
| IL | 499 | 0 (0%) | 17 (3%) | 482 (97%) | 17 (3%) | 17 (3%) |

111 industries are in use under the 11 sectors. The nightly job keeps fundamentals fresh in batches: SEC data is re-checked about weekly, Yahoo monthly, profiles (country, industry) every 90 days.

### Companies by country of domicile

Where companies are based, which can differ from where they trade (e.g. many Israeli companies trade mainly on Nasdaq). Primary listings only.

| Country | Companies |
| --- | ---: |
| (unknown) | 4,378 |
| GB | 70 |
| CH | 62 |
| DE | 61 |
| SE | 54 |
| FR | 52 |
| IT | 35 |
| NL | 28 |
| ES | 25 |
| US | 24 |
| DK | 22 |
| FI | 17 |
| IL | 17 |
| NO | 14 |
| PL | 14 |
| BE | 13 |
| AT | 11 |
| IE | 6 |
| LU | 5 |
| PT | 4 |

## FX rates (units per 1 USD, latest)

| Currency | Rate | As of |
| --- | ---: | --- |
| CHF | 0.8441 | 2026-11-20 |
| DKK | 6.8142 | 2026-11-21 |
| EUR | 0.9116 | 2026-11-20 |
| GBP | 0.7644 | 2026-11-21 |
| HKD | 7.8389 | 2026-11-21 |
| ILS | 3.2982 | 2026-11-20 |
| JPY | 159.7070 | 2026-11-20 |
| KRW | 1,334.7900 | 2026-11-20 |
| NOK | 9.7494 | 2026-11-21 |
| PLN | 4.0423 | 2026-11-20 |
| SEK | 10.2245 | 2026-11-21 |
| TWD | 33.0263 | 2026-11-20 |

## Data quality

| Check | Findings | Examples |
| --- | ---: | --- |
| Active securities with no price history | 0 | – |
| Active securities whose last bar is over 5 business days behind their exchange's latest bar | 0 | – |
| Bars where high < low or close lies outside the high/low range | 0 | – |
| Day-over-day moves above 50% with no split on that date | 1,371 | XTAE:TSEM 2017-05-04 -86.1%<br>XTAE:TSEM 2017-05-08 683.4%<br>XTAE:DLEKG 2020-03-12 -51.0% |
| Active securities without a sector | 0 | – |

Unexplained jumps are a mix of real moves (e.g. March 2020) and bad ticks in the free data; review before relying on a specific series. Already repaired automatically on ingest: agorot/pence quotes, 100x unit breaks, and inconsistent high/low values.

## How to use the data

### Conventions

| Topic | Rule |
|-------|------|
| Price units | Always the listing currency's **main unit** (shekels, pounds), never agorot or pence. |
| `close` | Adjusted for **splits only**. Use it for price levels and charts. |
| `adj_close` | Adjusted for splits **and dividends**. Use it for returns, correlations and backtests. |
| Splits | A new split rewrites earlier `close` values; the nightly update re-fetches that stock's full history. |
| FX | `fx_rates` rows are *units of `quote` per 1 USD* (e.g. ILS 3.7). Price in USD = local price ÷ rate. |
| Market cap | From the daily quote snapshot, in local currency and USD (`quote_snapshots`). |
| Dual listings | `primary_security_id` points to the company's most liquid listing. Exclude rows where it is set to count each company once (e.g. sector indices). |
| Sectors | 11 sectors aligned with Yahoo's names; industries (e.g. "Banks - Regional") below them. |
| Country | `securities.country_code` is the company's country of domicile (ISO code), not the exchange's. |
| Fundamentals | `financial_facts`: one row per metric, period (`FY` or `Q`) and the date the value became known. Use the latest `known_since` per period for current figures, or filter `known_since <= date` for point-in-time backtests. Money is in the reporting currency (`unit`), which can differ from the listing currency. |
| Inactive stocks | Not returned by the source for 14+ days, or rejected as a passive cross-listing. History is kept. |
| Delay | Prices are end-of-day; today's bar appears after the evening run for that market. |

### In the web app

- **Stocks** (`/stocks`): search by symbol or name, filter by exchange and sector, sorted by market cap.
- **Data** (`/data`): coverage per exchange, the quality checks above and recent pipeline runs.

### Command line (`stockscanner`, inside `backend/` or the backend container)

| Command | Use it to |
|---------|-----------|
| `stockscanner status` | Quick coverage and recent runs in the terminal |
| `stockscanner report` | Regenerate this report (`--output` to change the path) |
| `stockscanner quality` | Full data-quality findings |
| `stockscanner update` | Fetch the latest prices now (otherwise the scheduler does it) |
| `stockscanner nightly -g IL` | Run one market's full nightly job now (FX, universe, prices) |
| `stockscanner universe -g US` | Re-select which stocks are tracked in a group |
| `stockscanner backfill --years 10` | Load history for stocks that have none |
| `stockscanner fundamentals --source sec` | Refresh SEC fundamentals (US); `--source yahoo` for the rest |
| `stockscanner profiles` | Refresh country and industry |

In Docker, prefix with `docker compose exec backend`.

### API (http://localhost:8000/docs for the interactive version)

| Endpoint | Returns |
|----------|---------|
| `GET /api/exchanges` | Exchanges with stock counts and latest bar date |
| `GET /api/sectors` | Sectors with stock counts |
| `GET /api/securities?q=teva&exchange=XTAE&sector=Healthcare&limit=50` | Search the universe |
| `GET /api/securities/{id}` | One stock: identifiers, history range, latest snapshot |
| `GET /api/securities/{id}/bars?start=2025-01-01` | Daily prices |
| `GET /api/securities/{id}/fundamentals?period_type=FY&periods=8` | Financial statements, one row per metric (`Q` for quarters) |
| `GET /api/ingest/runs` | Pipeline run history |
| `GET /api/data/quality` | Quality checks |

### SQL (psql, Python, notebooks)

Connect: `postgresql://stockscanner:stockscanner@localhost:5432/stockscanner`

```sql
-- Daily prices for one stock
SELECT b.date, b.close, b.adj_close, b.volume
FROM daily_bars b
JOIN securities s ON s.id = b.security_id
JOIN exchanges e ON e.id = s.exchange_id
WHERE e.mic = 'XTAE' AND s.symbol = 'TEVA'
ORDER BY b.date;

-- Stocks in a sector on one exchange, largest first (latest snapshot)
SELECT s.symbol, s.name, q.market_cap_usd
FROM securities s
JOIN exchanges e ON e.id = s.exchange_id
JOIN sectors sec ON sec.id = s.sector_id
JOIN LATERAL (SELECT market_cap_usd FROM quote_snapshots
              WHERE security_id = s.id ORDER BY date DESC LIMIT 1) q ON true
WHERE s.is_active AND e.mic = 'XTAE' AND sec.name = 'Technology'
ORDER BY q.market_cap_usd DESC;

-- Prices converted to USD
SELECT b.date, b.close / f.rate AS close_usd
FROM daily_bars b
JOIN securities s ON s.id = b.security_id
JOIN fx_rates f ON f.base = 'USD' AND f.quote = s.currency_code AND f.date = b.date
WHERE s.id = 2;
```

```sql
-- Annual revenue and net income for one company (latest known values)
SELECT DISTINCT ON (f.metric, f.period_end) f.metric, f.period_end, f.value, f.unit
FROM financial_facts f
JOIN securities s ON s.id = f.security_id
JOIN exchanges e ON e.id = s.exchange_id
WHERE e.mic = 'XNAS' AND s.symbol = 'AAPL' AND f.period_type = 'FY'
  AND f.metric IN ('revenue', 'net_income')
ORDER BY f.metric, f.period_end DESC, f.known_since DESC;

-- What was known on a past date (point-in-time, for backtests)
SELECT DISTINCT ON (f.metric, f.period_end) f.metric, f.period_end, f.value
FROM financial_facts f
WHERE f.security_id = 123 AND f.known_since <= DATE '2022-06-30'
ORDER BY f.metric, f.period_end DESC, f.known_since DESC;
```

In Python: `pandas.read_sql(query, "postgresql+psycopg://stockscanner:stockscanner@localhost/stockscanner")`.

### Known limitations (free data)

- End-of-day only, no real-time prices.
- Delisted companies mostly missing before we started tracking them (survivorship bias in backtests).
- Some illiquid stocks have noisy prices; check the quality section before trusting a series.
- Non-US fundamentals: only ~4 years from Yahoo, without filing dates (European filings via ESEF are planned).
- Quarterly SEC data has no separate Q4 for flow metrics (companies report it only inside the annual figure).
- Exchange holiday calendars are not loaded yet.
