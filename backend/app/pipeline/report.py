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
        SELECT e.mic, s.symbol, s.name, sec.name AS sector, snap.market_cap_usd
        FROM securities s
        JOIN exchanges e ON e.id = s.exchange_id
        LEFT JOIN sectors sec ON sec.id = s.sector_id
        JOIN LATERAL (
            SELECT market_cap_usd FROM quote_snapshots q
            WHERE q.security_id = s.id ORDER BY q.date DESC LIMIT 1
        ) snap ON true
        WHERE s.is_active AND s.primary_security_id IS NULL
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
    w("## Largest companies per group (primary listings)")
    w("")
    for g in groups:
        rows = [r for r in top if mic_group.get(r["mic"]) == g][:10]
        if not rows:
            continue
        w(f"**{g}**")
        w("")
        w(
            _table(
                ["#", "Symbol", "Exchange", "Company", "Sector", "Market cap"],
                [
                    [str(i), r["symbol"], r["mic"], r["name"][:40], r["sector"] or DASH,
                     _usd(r["market_cap_usd"])]
                    for i, r in enumerate(rows, 1)
                ],
                "rlllll",
            )
        )  # fmt: skip
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
| Sectors | 11 sectors aligned with Yahoo's names. Industries come later. |
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

In Docker, prefix with `docker compose exec backend`.

### API (http://localhost:8000/docs for the interactive version)

| Endpoint | Returns |
|----------|---------|
| `GET /api/exchanges` | Exchanges with stock counts and latest bar date |
| `GET /api/sectors` | Sectors with stock counts |
| `GET /api/securities?q=teva&exchange=XTAE&sector=Healthcare&limit=50` | Search the universe |
| `GET /api/securities/{id}` | One stock: identifiers, history range, latest snapshot |
| `GET /api/securities/{id}/bars?start=2025-01-01` | Daily prices |
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

In Python: `pandas.read_sql(query, "postgresql+psycopg://stockscanner:stockscanner@localhost/stockscanner")`.

### Known limitations (free data)

- End-of-day only, no real-time prices.
- Delisted companies mostly missing before we started tracking them (survivorship bias in backtests).
- Some illiquid stocks have noisy prices; check the quality section before trusting a series.
- Fundamentals (financial statements), holiday calendars and industries are not loaded yet.
"""
