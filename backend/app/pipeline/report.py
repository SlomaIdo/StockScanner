"""Generate a Markdown report on the stock database: coverage, freshness, quality, usage.

Usage: ``stockscanner report`` (writes ``docs/DATA_REPORT.md`` by default).
"""

import datetime as dt
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pipeline.quality import run_quality_checks
from app.pipeline.universe import GROUPS

DASH = "\u2013"  # shown for missing values


def _q(session: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in session.execute(text(sql), params)]


def _n(value: int | float | None) -> str:
    return DASH if value is None else f"{value:,.0f}"


def _usd(value: float | None) -> str:
    if value is None:
        return DASH
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if value >= size:
            return f"${value / size:,.1f}{unit}"
    return f"${value:,.0f}"


def _table(headers: list[str], rows: list[list[str]], align: str | None = None) -> str:
    align = align or "l" * len(headers)
    sep = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(sep) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def build_report(session: Session) -> str:
    now = dt.datetime.now(dt.UTC)
    mic_group = {mic: g.name for g in GROUPS.values() for mic in g.mics}

    totals = _q(
        session,
        """
        SELECT
          (SELECT count(*) FROM securities WHERE is_active) AS active,
          (SELECT count(*) FROM securities WHERE NOT is_active) AS inactive,
          (SELECT count(*) FROM securities WHERE is_active
              AND last_seen_on < (SELECT max(last_seen_on) FROM securities)) AS grace,
          (SELECT count(*) FROM securities WHERE is_active AND primary_security_id IS NOT NULL)
              AS dual,
          (SELECT count(*) FROM daily_bars) AS bars,
          (SELECT min(date) FROM daily_bars) AS first_bar,
          (SELECT max(date) FROM daily_bars) AS last_bar,
          (SELECT count(*) FROM corporate_actions WHERE action_type = 'split') AS splits,
          (SELECT count(*) FROM corporate_actions WHERE action_type = 'dividend') AS dividends,
          (SELECT count(*) FROM quote_snapshots) AS snapshots,
          (SELECT count(DISTINCT date) FROM quote_snapshots) AS snapshot_days,
          (SELECT max(date) FROM quote_snapshots) AS last_snapshot,
          (SELECT count(DISTINCT quote) FROM fx_rates) AS fx_currencies,
          (SELECT max(date) FROM fx_rates) AS last_fx
        """,
    )[0]

    exchanges = _q(
        session,
        """
        WITH per_sec AS (
            SELECT s.id, s.exchange_id, count(b.date) AS bars,
                   min(b.date) AS first_bar, max(b.date) AS last_bar
            FROM securities s
            LEFT JOIN daily_bars b ON b.security_id = s.id
            WHERE s.is_active
            GROUP BY s.id
        )
        SELECT e.mic, e.name, e.country_code, e.currency_code,
               count(p.id) AS stocks,
               count(p.id) FILTER (WHERE p.bars > 0) AS with_prices,
               coalesce(sum(p.bars), 0) AS bars,
               min(p.first_bar) AS first_bar, max(p.last_bar) AS last_bar,
               avg((p.last_bar - p.first_bar) / 365.25) AS avg_years
        FROM exchanges e
        JOIN per_sec p ON p.exchange_id = e.id
        GROUP BY e.id ORDER BY count(p.id) DESC
        """,
    )

    sectors = _q(
        session,
        """
        SELECT coalesce(sec.name, '(none)') AS sector, e.mic, count(*) AS n
        FROM securities s
        JOIN exchanges e ON e.id = s.exchange_id
        LEFT JOIN sectors sec ON sec.id = s.sector_id
        WHERE s.is_active
        GROUP BY 1, 2
        """,
    )

    top = _q(
        session,
        """
        SELECT e.mic, s.symbol, s.name, sec.name AS sector, snap.market_cap_usd,
               pe.mic || ':' || p.symbol AS primary_listing
        FROM securities s
        JOIN exchanges e ON e.id = s.exchange_id
        LEFT JOIN sectors sec ON sec.id = s.sector_id
        LEFT JOIN securities p ON p.id = s.primary_security_id
        LEFT JOIN exchanges pe ON pe.id = p.exchange_id
        JOIN LATERAL (
            SELECT market_cap_usd FROM quote_snapshots q
            WHERE q.security_id = s.id ORDER BY q.date DESC LIMIT 1
        ) snap ON true
        WHERE s.is_active
        ORDER BY snap.market_cap_usd DESC NULLS LAST
        """,
    )

    runs = _q(
        session,
        """
        SELECT DISTINCT ON (job) job, status, scope, started_at, finished_at,
               items_ok, items_failed
        FROM ingest_runs ORDER BY job, started_at DESC
        """,
    )
    last_success = {
        r["job"]: r["finished_at"]
        for r in _q(
            session,
            """
            SELECT job, max(finished_at) AS finished_at FROM ingest_runs
            WHERE status IN ('success', 'partial') GROUP BY job
            """,
        )
    }
    fx = _q(
        session,
        """
        SELECT DISTINCT ON (quote) quote, date, rate FROM fx_rates
        WHERE base = 'USD' ORDER BY quote, date DESC
        """,
    )
    fundamentals = _q(
        session,
        """
        WITH company AS (
            SELECT s.id, e.mic,
                   EXISTS (SELECT 1 FROM financial_facts f WHERE f.security_id = s.id
                           AND f.source = 'sec') AS has_sec,
                   EXISTS (SELECT 1 FROM financial_facts f WHERE f.security_id = s.id
                           AND f.source = 'yahoo') AS has_yahoo,
                   (SELECT max(period_end) FROM financial_facts f WHERE f.security_id = s.id
                    AND f.period_type = 'FY' AND f.metric = 'revenue') AS last_fy,
                   (SELECT min(period_end) FROM financial_facts f WHERE f.security_id = s.id
                    AND f.period_type = 'FY' AND f.metric = 'revenue') AS first_fy,
                   s.country_code IS NOT NULL AS has_country,
                   s.industry_id IS NOT NULL AS has_industry
            FROM securities s JOIN exchanges e ON e.id = s.exchange_id
            WHERE s.is_active AND s.primary_security_id IS NULL
        )
        SELECT mic, count(*) AS companies,
               count(*) FILTER (WHERE has_sec) AS sec,
               count(*) FILTER (WHERE has_yahoo AND NOT has_sec) AS yahoo,
               count(*) FILTER (WHERE has_country) AS with_country,
               count(*) FILTER (WHERE has_industry) AS with_industry,
               percentile_disc(0.5) WITHIN GROUP (ORDER BY first_fy) AS median_first_fy,
               max(last_fy) AS latest_fy
        FROM company GROUP BY mic
        """,
    )
    fact_totals = _q(
        session,
        """
        SELECT source, count(*) AS facts, count(DISTINCT security_id) AS companies,
               max(known_since) AS latest_known
        FROM financial_facts GROUP BY source ORDER BY source
        """,
    )
    countries = _q(
        session,
        """
        SELECT coalesce(s.country_code, '(unknown)') AS country, count(*) AS n
        FROM securities s
        WHERE s.is_active AND s.primary_security_id IS NULL
        GROUP BY 1 ORDER BY 2 DESC LIMIT 20
        """,
    )
    industries = _q(
        session,
        """
        SELECT count(DISTINCT industry_id) AS industries FROM securities
        WHERE is_active AND industry_id IS NOT NULL
        """,
    )[0]["industries"]
    quality = run_quality_checks(session)

    out: list[str] = []
    w = out.append

    w("# StockScanner data report")
    w("")
    w(
        f"Generated {now:%Y-%m-%d %H:%M} UTC from the live database. "
        "Regenerate any time with `stockscanner report`."
    )
    w("")

    # -- summary ---------------------------------------------------------------
    w("## At a glance")
    w("")
    w(
        _table(
            ["", ""],
            [
                ["Active stocks", _n(totals["active"])],
                ["  of which dual listings", _n(totals["dual"])],
                [
                    "  of which in grace period",
                    f"{_n(totals['grace'])} (not picked in the latest refresh; kept active for "
                    "14 days so a flaky day doesn't drop them)",
                ],
                ["Inactive (delisted / dropped)", _n(totals["inactive"])],
                ["Exchanges with data", _n(len(exchanges))],
                ["Daily price bars", _n(totals["bars"])],
                ["Price history", f"{totals['first_bar'] or DASH} → {totals['last_bar'] or DASH}"],
                ["Latest trading day loaded", str(totals["last_bar"] or DASH)],
                ["Splits / dividends recorded", f"{_n(totals['splits'])} / {_n(totals['dividends'])}"],
                [
                    "Quote snapshots (market cap, P/E, …)",
                    f"{_n(totals['snapshots'])} over {_n(totals['snapshot_days'])} day(s), "
                    f"latest {totals['last_snapshot'] or DASH}",
                ],
                ["FX currencies vs USD", f"{_n(totals['fx_currencies'])}, latest {totals['last_fx'] or DASH}"],
                ["Data source", "Yahoo Finance (free, delayed, personal use)"],
            ],
        )
    )  # fmt: skip
    w("")

    # -- freshness -------------------------------------------------------------
    w("## Freshness: when was it updated")
    w("")
    w(
        _table(
            ["Job", "Last run status", "Scope", "Started (UTC)", "OK / failed", "Last success (UTC)"],
            [
                [
                    r["job"],
                    r["status"],
                    (r["scope"] or "all")[:40],
                    f"{r['started_at']:%Y-%m-%d %H:%M}",
                    f"{r['items_ok']} / {r['items_failed']}",
                    f"{last_success[r['job']]:%Y-%m-%d %H:%M}" if r["job"] in last_success else "never",
                ]
                for r in runs
            ],
        )
    )  # fmt: skip
    w("")
    w("Nightly schedule (weekdays, run by the `scheduler` service):")
    w("")
    w(
        _table(
            ["Group", "Exchanges", "Runs at (local time)", "Universe rule", "Enabled"],
            [
                [
                    g.name,
                    ", ".join(g.mics),
                    f"{g.schedule_time} {g.schedule_timezone}",
                    (f"top {g.top_n:,}" if g.top_n else "all")
                    + f", market cap > {_usd(g.min_market_cap_usd)}",
                    "yes" if g.enabled else "no",
                ]
                for g in GROUPS.values()
            ],
        )
    )
    w("")

    # -- coverage --------------------------------------------------------------
    w("## Coverage by exchange")
    w("")
    w(
        _table(
            ["Group", "Exchange", "MIC", "Country", "Ccy", "Stocks", "With prices", "Bars",
             "History from", "Last bar", "Avg years"],
            [
                [
                    mic_group.get(e["mic"], DASH), e["name"], e["mic"], e["country_code"],
                    e["currency_code"], _n(e["stocks"]), _n(e["with_prices"]), _n(e["bars"]),
                    str(e["first_bar"] or DASH), str(e["last_bar"] or DASH),
                    f"{e['avg_years']:.1f}" if e["avg_years"] is not None else DASH,
                ]
                for e in exchanges
            ],
            "llllrrrrllr",
        )
    )  # fmt: skip
    w("")
    by_group: dict[str, int] = {}
    for e in exchanges:
        by_group[mic_group.get(e["mic"], "other")] = (
            by_group.get(mic_group.get(e["mic"], "other"), 0) + e["stocks"]
        )
    w("Stocks per group: " + ", ".join(f"**{g}** {_n(n)}" for g, n in by_group.items()) + ".")
    w("")

    # -- sectors ---------------------------------------------------------------
    w("## Stocks by sector and market group")
    w("")
    groups = list(by_group)
    matrix: dict[str, dict[str, int]] = {}
    for row in sectors:
        g = mic_group.get(row["mic"], "other")
        matrix.setdefault(row["sector"], {}).setdefault(g, 0)
        matrix[row["sector"]][g] += row["n"]
    w(
        _table(
            ["Sector", *groups, "Total"],
            [
                [name, *(_n(counts.get(g, 0)) for g in groups), _n(sum(counts.values()))]
                for name, counts in sorted(matrix.items())
            ],
            "l" + "r" * (len(groups) + 1),
        )
    )
    w("")

    # -- largest ---------------------------------------------------------------
    w("## Largest companies per group")
    w("")
    w(
        "Includes dual listings, marked with the company's most liquid listing (e.g. ASML in "
        "Amsterdam trades less than on Nasdaq, so Nasdaq is its primary)."
    )
    w("")
    for g in groups:
        rows = [r for r in top if mic_group.get(r["mic"]) == g][:10]
        if not rows:
            continue
        w(f"**{g}**")
        w("")
        w(
            _table(
                ["#", "Symbol", "Exchange", "Company", "Sector", "Market cap", "Note"],
                [
                    [str(i), r["symbol"], r["mic"], r["name"][:40], r["sector"] or DASH,
                     _usd(r["market_cap_usd"]),
                     f"dual, primary {r['primary_listing']}" if r["primary_listing"] else ""]
                    for i, r in enumerate(rows, 1)
                ],
                "rllllll",
            )
        )  # fmt: skip
        w("")

    # -- fundamentals ----------------------------------------------------------
    w("## Fundamentals (financial statements)")
    w("")
    w(
        "US companies come from SEC EDGAR (official filings, quarterly and annual, typically "
        "back to 2009, each value with its filing date). Other companies come from Yahoo "
        "(about 4 years annual and 6 quarters; dated by when we fetched them). Counts are per "
        "company (primary listings); dual listings use their primary's data."
    )
    w("")
    w(
        _table(
            ["Source", "Values stored", "Companies", "Latest value known since"],
            [
                [r["source"], _n(r["facts"]), _n(r["companies"]), str(r["latest_known"])]
                for r in fact_totals
            ]
            or [["(none yet)", "0", "0", DASH]],
            "lrrl",
        )
    )
    w("")
    group_totals: dict[str, dict[str, int]] = {}
    group_years: dict[str, list[Any]] = {}
    for r in fundamentals:
        g = mic_group.get(r["mic"], "other")
        t = group_totals.setdefault(
            g, {"companies": 0, "sec": 0, "yahoo": 0, "country": 0, "industry": 0}
        )
        t["companies"] += r["companies"]
        t["sec"] += r["sec"]
        t["yahoo"] += r["yahoo"]
        t["country"] += r["with_country"]
        t["industry"] += r["with_industry"]
        group_years.setdefault(g, []).append(r["latest_fy"])

    def pct(part: int, whole: int) -> str:
        return f"{_n(part)} ({part / whole:.0%})" if whole else "0"

    w(
        _table(
            ["Group", "Companies", "With SEC data", "With Yahoo data", "Without data",
             "Country known", "Industry known"],
            [
                [
                    g, _n(t["companies"]), pct(t["sec"], t["companies"]),
                    pct(t["yahoo"], t["companies"]),
                    pct(t["companies"] - t["sec"] - t["yahoo"], t["companies"]),
                    pct(t["country"], t["companies"]), pct(t["industry"], t["companies"]),
                ]
                for g, t in group_totals.items()
            ],
            "lrrrrrr",
        )
    )  # fmt: skip
    w("")
    w(
        f"{_n(industries)} industries are in use under the 11 sectors. The nightly job keeps "
        "fundamentals fresh in batches: SEC data is re-checked about weekly, Yahoo monthly, "
        "profiles (country, industry) every 90 days."
    )
    w("")
    w("### Companies by country of domicile")
    w("")
    w(
        "Where companies are based, which can differ from where they trade (e.g. many Israeli "
        "companies trade mainly on Nasdaq). Primary listings only."
    )
    w("")
    w(
        _table(
            ["Country", "Companies"],
            [[r["country"], _n(r["n"])] for r in countries],
            "lr",
        )
    )
    w("")

    # -- FX --------------------------------------------------------------------
    w("## FX rates (units per 1 USD, latest)")
    w("")
    w(
        _table(
            ["Currency", "Rate", "As of"],
            [[r["quote"], f"{r['rate']:,.4f}", str(r["date"])] for r in fx],
            "lrl",
        )
    )
    w("")

    # -- quality ---------------------------------------------------------------
    w("## Data quality")
    w("")
    w(
        _table(
            ["Check", "Findings", "Examples"],
            [
                [c.description, _n(c.count), "<br>".join(c.samples[:3]) or DASH]
                for c in quality.checks
            ],
            "lrl",
        )
    )
    w("")
    w(
        "Unexplained jumps are a mix of real moves (e.g. March 2020) and bad ticks in the free "
        "data; review before relying on a specific series. Already repaired automatically on "
        "ingest: agorot/pence quotes, 100x unit breaks, and inconsistent high/low values."
    )
    w("")

    w(USAGE_GUIDE)
    return "\n".join(out)


USAGE_GUIDE = """## How to use the data

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
"""
