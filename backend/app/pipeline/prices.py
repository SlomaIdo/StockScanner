"""Daily price ingest: historical backfill and incremental updates.

Prices are stored in the listing currency's main unit (provider sub-unit quotes such as
agorot or pence are divided by the identifier's ``price_divisor``).

Yahoo's close is split-adjusted, so a new split changes all earlier prices. When an update
sees a split we have not stored yet, the security's full history is fetched again.

Two clean-ups run on every ingest:
- OHLC is made consistent: high/low are widened to contain open and close (illiquid stocks
  often report e.g. a high below the open).
- Unit breaks are repaired: free data sometimes switches between a currency and its sub-unit
  mid-history (e.g. many TASE stocks jump exactly 100x on one day). A ~100x day move with no
  split is rescaled so older bars match the most recent ones.
"""

import datetime as dt
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Select, bindparam, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    CorporateAction,
    CorporateActionType,
    DailyBar,
    Exchange,
    Security,
    SecurityIdentifier,
)
from app.pipeline.runs import RunTracker, track_run
from app.providers.base import PriceHistory, PriceProvider, ProviderError

log = logging.getLogger(__name__)

DEFAULT_BACKFILL_YEARS = 10
UPDATE_OVERLAP_DAYS = 5
BATCH_SIZE = 200
# A one-day move in this band with no split is treated as a 100x unit mix-up.
UNIT_BREAK_BAND = (70.0, 140.0)


@dataclass(frozen=True)
class Target:
    security_id: int
    provider_symbol: str
    divisor: int
    start: dt.date


@dataclass
class IngestStats:
    securities_ok: int = 0
    securities_failed: int = 0
    bars: int = 0
    refetched_after_split: list[str] = field(default_factory=list)
    unit_breaks_repaired: int = 0


def _targets_query(provider: str, mics: list[str] | None) -> Select[int, str, int]:
    stmt = (
        select(Security.id, SecurityIdentifier.external_symbol, SecurityIdentifier.price_divisor)
        .join(SecurityIdentifier, SecurityIdentifier.security_id == Security.id)
        .join(Exchange, Exchange.id == Security.exchange_id)
        .where(Security.is_active.is_(True), SecurityIdentifier.provider == provider)
        .order_by(Security.id)
    )
    if mics:
        stmt = stmt.where(Exchange.mic.in_(mics))
    return stmt


def backfill_prices(
    session: Session,
    provider: PriceProvider,
    mics: list[str] | None = None,
    start: dt.date | None = None,
    only_missing: bool = True,
    limit: int | None = None,
) -> IngestStats:
    """Fetch full history from ``start`` (default 10 years ago) for active securities.

    With ``only_missing`` (default), securities that already have bars are skipped.
    """
    start = start or dt.date.today() - dt.timedelta(days=365 * DEFAULT_BACKFILL_YEARS)
    stmt = _targets_query(provider.name, mics)
    if only_missing:
        has_bars = select(DailyBar.security_id).where(DailyBar.security_id == Security.id)
        stmt = stmt.where(~has_bars.exists())
    if limit:
        stmt = stmt.limit(limit)
    targets = [Target(sid, sym, div, start) for sid, sym, div in session.execute(stmt)]
    with track_run(session, "backfill", ",".join(mics or ["all"])) as run:
        return _ingest(session, provider, targets, run, detect_new_splits=False)


def update_prices(
    session: Session, provider: PriceProvider, mics: list[str] | None = None
) -> IngestStats:
    """Fetch recent bars for active securities, from their last stored bar minus an overlap.

    Securities without any bars yet get a full backfill.
    """
    last_bar = (
        select(DailyBar.security_id, func.max(DailyBar.date).label("last"))
        .group_by(DailyBar.security_id)
        .subquery()
    )
    stmt = _targets_query(provider.name, mics).add_columns(last_bar.c.last)
    stmt = stmt.outerjoin(last_bar, last_bar.c.security_id == Security.id)
    default_start = dt.date.today() - dt.timedelta(days=365 * DEFAULT_BACKFILL_YEARS)
    targets = [
        Target(
            sid,
            sym,
            div,
            last - dt.timedelta(days=UPDATE_OVERLAP_DAYS) if last else default_start,
        )
        for sid, sym, div, last in session.execute(stmt)
    ]
    with track_run(session, "update", ",".join(mics or ["all"])) as run:
        return _ingest(session, provider, targets, run, detect_new_splits=True)


def _ingest(
    session: Session,
    provider: PriceProvider,
    targets: list[Target],
    run: RunTracker,
    detect_new_splits: bool,
) -> IngestStats:
    stats = IngestStats()
    run.note(f"{len(targets)} securities to fetch")
    # Batch securities that share a start date so each provider call covers many symbols.
    by_start: dict[dt.date, list[Target]] = defaultdict(list)
    for t in targets:
        by_start[t.start].append(t)

    refetch: list[Target] = []
    for start, group in sorted(by_start.items()):
        for i in range(0, len(group), BATCH_SIZE):
            batch = group[i : i + BATCH_SIZE]
            try:
                histories = provider.daily_history([t.provider_symbol for t in batch], start)
            except ProviderError as exc:
                run.note(f"batch starting {batch[0].provider_symbol} failed: {exc}")
                stats.securities_failed += len(batch)
                continue
            known_splits = _known_splits(session, [t.security_id for t in batch])
            for t in batch:
                history = histories.get(t.provider_symbol)
                if history is None:
                    stats.securities_failed += 1
                    continue
                if detect_new_splits and _has_new_split(t, history, known_splits):
                    first = session.scalar(
                        select(func.min(DailyBar.date)).where(DailyBar.security_id == t.security_id)
                    )
                    if first and first < t.start:
                        refetch.append(Target(t.security_id, t.provider_symbol, t.divisor, first))
                stats.bars += _store_history(session, provider.name, t, history)
                stats.securities_ok += 1
            stats.unit_breaks_repaired += repair_unit_breaks(
                session, [t.security_id for t in batch]
            )
            session.commit()
            log.info(
                "progress: %d ok, %d failed, %d bars",
                stats.securities_ok,
                stats.securities_failed,
                stats.bars,
            )

    for t in refetch:
        try:
            history = provider.daily_history([t.provider_symbol], t.start).get(t.provider_symbol)
        except ProviderError as exc:
            run.note(f"refetch after split failed for {t.provider_symbol}: {exc}")
            continue
        if history:
            _store_history(session, provider.name, t, history)
            stats.unit_breaks_repaired += repair_unit_breaks(session, [t.security_id])
            stats.refetched_after_split.append(t.provider_symbol)
        session.commit()
    if stats.refetched_after_split:
        run.note(f"re-fetched after split: {', '.join(stats.refetched_after_split)}")

    run.ok = stats.securities_ok
    run.failed = stats.securities_failed
    if stats.unit_breaks_repaired:
        run.note(f"repaired {stats.unit_breaks_repaired} 100x unit breaks")
    run.note(f"stored {stats.bars} bars")
    return stats


def _known_splits(session: Session, security_ids: list[int]) -> set[tuple[int, dt.date]]:
    rows = session.execute(
        select(CorporateAction.security_id, CorporateAction.ex_date).where(
            CorporateAction.security_id.in_(security_ids),
            CorporateAction.action_type == CorporateActionType.SPLIT,
        )
    )
    return {(sid, day) for sid, day in rows}


def _has_new_split(target: Target, history: PriceHistory, known: set[tuple[int, dt.date]]) -> bool:
    return any((target.security_id, s.ex_date) not in known for s in history.splits)


def _scaled(value: float | None, divisor: int) -> float | None:
    return value / divisor if value is not None else None


def consistent_ohlc(
    open_: float | None, high: float | None, low: float | None, close: float
) -> tuple[float | None, float | None]:
    """Widen high/low so the bar contains its open and close."""
    points = [close] + ([open_] if open_ is not None else [])
    if high is not None:
        high = max(high, *points)
    if low is not None:
        low = min(low, *points)
    return high, low


_FIND_UNIT_BREAKS = text(
    """
    WITH moves AS (
        SELECT security_id, date,
               close / lag(close) OVER (PARTITION BY security_id ORDER BY date) AS ratio
        FROM daily_bars
        WHERE security_id IN :ids
    )
    SELECT m.security_id, m.date, m.ratio
    FROM moves m
    WHERE (m.ratio BETWEEN :lo AND :hi OR m.ratio BETWEEN 1.0 / :hi AND 1.0 / :lo)
      AND NOT EXISTS (
        SELECT 1 FROM corporate_actions a
        WHERE a.security_id = m.security_id AND a.action_type = 'split' AND a.ex_date = m.date
      )
    ORDER BY m.security_id, m.date DESC
    """
).bindparams(bindparam("ids", expanding=True))

_RESCALE_BEFORE = text(
    """
    UPDATE daily_bars
    SET open = open * :f, high = high * :f, low = low * :f,
        close = close * :f, adj_close = adj_close * :f
    WHERE security_id = :sid AND date < :day
    """
)


def repair_unit_breaks(session: Session, security_ids: list[int]) -> int:
    """Rescale history before each ~100x jump so it matches the most recent prices.

    Breaks are processed newest first; rescaling a prefix leaves earlier ratios unchanged,
    so several breaks in one series are all handled.
    """
    if not security_ids:
        return 0
    lo, hi = UNIT_BREAK_BAND
    breaks = session.execute(_FIND_UNIT_BREAKS, {"ids": security_ids, "lo": lo, "hi": hi}).all()
    for security_id, day, ratio in breaks:
        factor = 100.0 if ratio > 1 else 0.01
        session.execute(_RESCALE_BEFORE, {"f": factor, "sid": security_id, "day": day})
        log.info("repaired 100x unit break: security %s before %s", security_id, day)
    return len(breaks)


def _store_history(session: Session, source: str, target: Target, history: PriceHistory) -> int:
    d = target.divisor
    rows = []
    for b in history.bars:
        high, low = consistent_ohlc(b.open, b.high, b.low, b.close)
        rows.append(
            {
                "security_id": target.security_id,
                "date": b.date,
                "open": _scaled(b.open, d),
                "high": _scaled(high, d),
                "low": _scaled(low, d),
                "close": b.close / d,
                "adj_close": _scaled(b.adj_close, d),
                "volume": b.volume,
                "source": source,
            }
        )
    if rows:
        stmt = insert(DailyBar)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["security_id", "date"],
                set_={
                    k: stmt.excluded[k]
                    for k in ("open", "high", "low", "close", "adj_close", "volume", "source")
                },
            ),
            rows,
        )

    currency = session.scalar(
        select(Security.currency_code).where(Security.id == target.security_id)
    )
    actions = [
        {
            "security_id": target.security_id,
            "ex_date": s.ex_date,
            "action_type": CorporateActionType.SPLIT,
            "value": Decimal(str(s.ratio)),
            "currency_code": None,
            "source": source,
        }
        for s in history.splits
    ] + [
        {
            "security_id": target.security_id,
            "ex_date": v.ex_date,
            "action_type": CorporateActionType.DIVIDEND,
            "value": Decimal(str(round(v.amount / d, 8))),
            "currency_code": currency,
            "source": source,
        }
        for v in history.dividends
    ]
    if actions:
        stmt_a = insert(CorporateAction)
        session.execute(
            stmt_a.on_conflict_do_update(
                index_elements=["security_id", "ex_date", "action_type"],
                set_={"value": stmt_a.excluded.value, "source": stmt_a.excluded.source},
            ),
            actions,
        )
    return len(rows)
