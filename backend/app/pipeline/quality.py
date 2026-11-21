"""Data-quality checks over stored prices. Read-only; returns findings for review."""

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

JUMP_THRESHOLD = 0.5  # a >50% day move without a split is suspicious
STALE_BUSINESS_DAYS = 5
SAMPLE_SIZE = 10


@dataclass
class Check:
    name: str
    description: str
    count: int
    samples: list[str] = field(default_factory=list)


@dataclass
class QualityReport:
    generated_at: dt.datetime
    checks: list[Check]

    @property
    def issues(self) -> int:
        return sum(c.count for c in self.checks)


_CHECKS: list[tuple[str, str, str]] = [
    (
        "missing_prices",
        "Active securities with no price history",
        """
        SELECT e.mic || ':' || s.symbol AS label
        FROM securities s JOIN exchanges e ON e.id = s.exchange_id
        WHERE s.is_active AND NOT EXISTS (SELECT 1 FROM daily_bars b WHERE b.security_id = s.id)
        """,
    ),
    (
        "stale_prices",
        f"Active securities whose last bar is over {STALE_BUSINESS_DAYS} business days behind "
        "their exchange's latest bar",
        """
        WITH last AS (
            SELECT s.id, s.symbol, e.mic, s.exchange_id, max(b.date) AS last_date
            FROM securities s
            JOIN exchanges e ON e.id = s.exchange_id
            JOIN daily_bars b ON b.security_id = s.id
            WHERE s.is_active
            GROUP BY s.id, s.symbol, e.mic, s.exchange_id
        ), exchange_last AS (
            SELECT exchange_id, max(last_date) AS ex_last FROM last GROUP BY exchange_id
        )
        SELECT l.mic || ':' || l.symbol || ' (last ' || l.last_date || ')' AS label
        FROM last l JOIN exchange_last x ON x.exchange_id = l.exchange_id
        WHERE (
            SELECT count(*) FROM generate_series(l.last_date + 1, x.ex_last, interval '1 day') d
            WHERE extract(isodow FROM d) < 6
        ) > :stale_days
        """,
    ),
    (
        "inconsistent_ohlc",
        "Bars where high < low or close lies outside the high/low range",
        """
        SELECT e.mic || ':' || s.symbol || ' ' || b.date AS label
        FROM daily_bars b
        JOIN securities s ON s.id = b.security_id
        JOIN exchanges e ON e.id = s.exchange_id
        WHERE b.high IS NOT NULL AND b.low IS NOT NULL
          AND (b.high < b.low OR b.close > b.high * 1.001 OR b.close < b.low * 0.999)
        """,
    ),
    (
        "unexplained_jumps",
        f"Day-over-day moves above {int(JUMP_THRESHOLD * 100)}% with no split on that date",
        """
        WITH moves AS (
            SELECT b.security_id, b.date, b.close,
                   lag(b.close) OVER (PARTITION BY b.security_id ORDER BY b.date) AS prev
            FROM daily_bars b
        )
        SELECT e.mic || ':' || s.symbol || ' ' || m.date || ' '
               || round((m.close / m.prev - 1)::numeric * 100, 1) || '%' AS label
        FROM moves m
        JOIN securities s ON s.id = m.security_id
        JOIN exchanges e ON e.id = s.exchange_id
        WHERE m.prev > 0 AND abs(m.close / m.prev - 1) > :jump
          AND NOT EXISTS (
            SELECT 1 FROM corporate_actions a
            WHERE a.security_id = m.security_id AND a.action_type = 'split' AND a.ex_date = m.date
          )
        """,
    ),
    (
        "missing_sector",
        "Active securities without a sector",
        """
        SELECT e.mic || ':' || s.symbol AS label
        FROM securities s JOIN exchanges e ON e.id = s.exchange_id
        WHERE s.is_active AND s.sector_id IS NULL
        """,
    ),
]


def run_quality_checks(session: Session) -> QualityReport:
    params = {"stale_days": STALE_BUSINESS_DAYS, "jump": JUMP_THRESHOLD}
    checks: list[Check] = []
    for name, description, sql in _CHECKS:
        count = session.execute(text(f"SELECT count(*) FROM ({sql}) q"), params).scalar_one()
        samples = (
            list(
                session.execute(
                    text(f"SELECT label FROM ({sql}) q LIMIT :n"), {**params, "n": SAMPLE_SIZE}
                ).scalars()
            )
            if count
            else []
        )
        checks.append(Check(name, description, count, samples))
    return QualityReport(generated_at=dt.datetime.now(dt.UTC), checks=checks)
