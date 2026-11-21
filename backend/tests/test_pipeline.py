import datetime as dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CorporateAction,
    CorporateActionType,
    DailyBar,
    FxRate,
    IngestRun,
    IngestStatus,
    QuoteSnapshot,
    Security,
    SecurityIdentifier,
)
from app.pipeline.fx import latest_usd_rates, update_fx
from app.pipeline.prices import backfill_prices, consistent_ohlc, update_prices
from app.pipeline.quality import run_quality_checks
from app.pipeline.universe import UniverseGroup, build_universe, company_key
from app.providers.base import Bar, Dividend, PriceHistory, Split
from tests.fakes import FakeProvider, listing

TODAY = dt.date.today()
FX = {
    "ILS": [(TODAY - dt.timedelta(days=1), 3.7)],
    "EUR": [(TODAY - dt.timedelta(days=1), 0.9)],
    "GBP": [(TODAY - dt.timedelta(days=1), 0.8)],
}


def group(name: str, *mics: str, top_n: int | None = None, floor: float = 1e6) -> UniverseGroup:
    return UniverseGroup(name, mics, floor, top_n, "UTC", "18:00")


def bars(start: dt.date, closes: list[float], **kw: float | None) -> list[Bar]:
    return [
        Bar(
            date=start + dt.timedelta(days=i),
            open=kw.get("open", c),
            high=kw.get("high", c),
            low=kw.get("low", c),
            close=c,
            adj_close=c,
            volume=100,
        )
        for i, c in enumerate(closes)
    ]


def security_by_symbol(db: Session, symbol: str, mic: str | None = None) -> Security:
    stmt = select(Security).where(Security.symbol == symbol)
    if mic:
        from app.models import Exchange

        stmt = stmt.join(Exchange).where(Exchange.mic == mic)
    return db.execute(stmt).scalar_one()


# -- FX ---------------------------------------------------------------------------


def test_update_fx_and_latest_rates(db: Session) -> None:
    provider = FakeProvider(
        fx={"ILS": [(dt.date(2026, 11, 19), 3.70), (dt.date(2026, 11, 20), 3.72)]}
    )
    stored = update_fx(db, provider, start=dt.date(2026, 11, 1))
    assert stored == 2
    rates = latest_usd_rates(db)
    assert rates["ILS"] == pytest.approx(3.72)
    assert rates["USD"] == 1.0
    run = db.scalars(select(IngestRun).order_by(IngestRun.id.desc())).first()
    assert run is not None and run.job == "fx"
    assert run.status == IngestStatus.PARTIAL  # other seeded currencies had no data


# -- universe ---------------------------------------------------------------------


def test_company_key() -> None:
    assert company_key("Apple Inc.") == "apple"
    assert company_key("APPLE INC") == "apple"
    assert company_key("Teva Pharmaceutical Industries Ltd") == "teva pharmaceutical industries"
    assert company_key("Alphabet Inc. Class A") == "alphabet"


def test_universe_resolves_listings(db: Session) -> None:
    update_fx(db, FakeProvider(fx=FX), start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(
        listings={
            "XNAS": [
                listing("AAPL", "XNAS", "Apple Inc.", avg_volume=5e7, price=200, market_cap=3e12),
                listing("NICE", "XNAS", "NICE Ltd.", avg_volume=4e5, price=150, market_cap=9e9),
                listing("GOOGL", "XNAS", "Alphabet Inc. Class A", market_cap=2e12),
                listing("GOOG", "XNAS", "Alphabet Inc. Class C", market_cap=2e12),
            ],
            "XETR": [
                # Passive foreign quote: tiny volume vs. Nasdaq -> dropped.
                listing("APC.DE", "XETR", "Apple Inc.", currency="EUR", avg_volume=1e4),
            ],
            "XTAE": [
                # Real dual listing: ~25% of the US dollar volume -> kept as secondary.
                listing(
                    "NICE.TA", "XTAE", "NICE Ltd.", currency="ILS", divisor=100,
                    avg_volume=7e4, price=600, market_cap=33e9,
                ),
                listing(
                    "TEVA.TA", "XTAE", "Teva Pharmaceutical Industries Limited",
                    currency="ILS", divisor=100, market_cap=150e9,
                ),
            ],
            "XLON": [
                # Quoted in a foreign currency -> dropped.
                listing("TYT.L", "XLON", "Toyota Motor Corp", currency="JPY", market_cap=4e13),
            ],
        }
    )  # fmt: skip
    groups = [group("US", "XNAS"), group("EU", "XETR", "XLON"), group("IL", "XTAE")]
    result = build_universe(db, provider, groups)

    assert result.selected == 6
    symbols = set(db.scalars(select(SecurityIdentifier.external_symbol)))
    assert symbols == {"AAPL", "NICE", "GOOGL", "GOOG", "NICE.TA", "TEVA.TA"}

    nice_ta = security_by_symbol(db, "NICE", "XTAE")
    nice_us = security_by_symbol(db, "NICE", "XNAS")
    assert nice_ta.primary_security_id == nice_us.id
    assert nice_us.primary_security_id is None
    assert nice_ta.currency_code == "ILS"
    assert nice_ta.identifiers[0].price_divisor == 100

    teva = security_by_symbol(db, "TEVA")
    snapshot = db.execute(
        select(QuoteSnapshot).where(QuoteSnapshot.security_id == teva.id)
    ).scalar_one()
    assert snapshot.market_cap_usd == pytest.approx(150e9 / 3.7)
    assert teva.sector is not None and teva.sector.name == "Technology"

    # Re-running is idempotent.
    again = build_universe(db, provider, groups)
    assert again.created == 0
    assert db.scalar(select(func.count()).select_from(Security)) == 6


def test_universe_deactivates_rejected_cross_listing_immediately(db: Session) -> None:
    update_fx(db, FakeProvider(fx=FX), start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(
        listings={"XTAE": [listing("PANW.TA", "XTAE", "Palo Alto Networks", currency="ILS")]}
    )
    build_universe(db, provider, [group("IL", "XTAE")])
    assert security_by_symbol(db, "PANW").is_active

    # Once the far more liquid US listing is in the same run, the TASE quote is rejected.
    provider.listings["XNAS"] = [
        listing("PANW", "XNAS", "Palo Alto Networks, Inc.", avg_volume=1e8)
    ]
    result = build_universe(db, provider, [group("IL", "XTAE"), group("US", "XNAS")])
    assert result.deactivated == 1
    assert security_by_symbol(db, "PANW", "XTAE").is_active is False


def test_universe_top_n_and_floor(db: Session) -> None:
    update_fx(db, FakeProvider(fx=FX), start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(
        listings={
            "XNYS": [
                listing(f"S{i}", "XNYS", f"Company {i}", market_cap=(i + 1) * 1e9) for i in range(5)
            ]
        }
    )
    build_universe(db, provider, [group("US", "XNYS", top_n=2, floor=1.5e9)])
    assert set(db.scalars(select(Security.symbol))) == {"S4", "S3"}


def test_universe_deactivates_stale_securities(db: Session) -> None:
    update_fx(db, FakeProvider(fx=FX), start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(listings={"XNYS": [listing("OLD", "XNYS", "Old Co")]})
    build_universe(db, provider, [group("US", "XNYS")])
    old = security_by_symbol(db, "OLD")
    old.last_seen_on = TODAY - dt.timedelta(days=30)
    db.commit()

    provider.listings["XNYS"] = [listing("NEW", "XNYS", "New Co")]
    result = build_universe(db, provider, [group("US", "XNYS")])
    db.refresh(old)
    assert result.deactivated == 1
    assert old.is_active is False


# -- prices -----------------------------------------------------------------------


def _universe_with(db: Session, *listings_: object) -> None:
    update_fx(db, FakeProvider(fx=FX), start=TODAY - dt.timedelta(days=10))
    by_mic: dict[str, list] = {}  # type: ignore[type-arg]
    for item in listings_:
        by_mic.setdefault(item.exchange_mic, []).append(item)  # type: ignore[attr-defined]
    build_universe(db, FakeProvider(listings=by_mic), [group("ALL", *by_mic)])


def test_consistent_ohlc() -> None:
    assert consistent_ohlc(30.7, 29.55, 29.55, 30.56) == (30.7, 29.55)
    assert consistent_ohlc(None, 10.0, 9.0, 9.5) == (10.0, 9.0)


def test_backfill_converts_subunits_and_stores_actions(db: Session) -> None:
    _universe_with(db, listing("TEVA.TA", "XTAE", "Teva", currency="ILS", divisor=100))
    start = dt.date(2026, 1, 5)
    provider = FakeProvider(
        histories={
            "TEVA.TA": PriceHistory(
                bars=bars(start, [13000.0, 13210.0], open=13100.0, high=13050.0, low=12900.0),
                splits=[Split(start + dt.timedelta(days=1), 2.0)],
                dividends=[Dividend(start, 50.0)],
            )
        }
    )
    stats = backfill_prices(db, provider, start=start)
    assert stats.securities_ok == 1 and stats.bars == 2

    teva = security_by_symbol(db, "TEVA")
    first = (
        db.execute(select(DailyBar).where(DailyBar.security_id == teva.id).order_by(DailyBar.date))
        .scalars()
        .first()
    )
    assert first is not None
    assert first.close == pytest.approx(130.0)
    assert first.high == pytest.approx(131.0)  # widened to contain the open (131.00)
    actions = {
        a.action_type: a
        for a in db.scalars(select(CorporateAction).where(CorporateAction.security_id == teva.id))
    }
    assert float(actions[CorporateActionType.DIVIDEND].value) == pytest.approx(0.5)
    assert actions[CorporateActionType.DIVIDEND].currency_code == "ILS"
    assert float(actions[CorporateActionType.SPLIT].value) == 2.0

    # Securities that already have bars are skipped by default.
    assert backfill_prices(db, provider, start=start).securities_ok == 0


def test_backfill_repairs_100x_unit_break(db: Session) -> None:
    _universe_with(db, listing("ISRA.TA", "XTAE", "Isras", currency="ILS", divisor=100))
    start = dt.date(2026, 5, 13)
    # Provider history is 100x too small before the break (as seen on Yahoo for TASE).
    provider = FakeProvider(
        histories={"ISRA.TA": PriceHistory(bars=bars(start, [2.33, 2.25, 222.3, 228.5]))}
    )
    stats = backfill_prices(db, provider, start=start)
    assert stats.unit_breaks_repaired == 1
    sec = security_by_symbol(db, "ISRA")
    closes = db.scalars(
        select(DailyBar.close).where(DailyBar.security_id == sec.id).order_by(DailyBar.date)
    ).all()
    assert closes == pytest.approx([2.33, 2.25, 2.223, 2.285])
    assert not next(c for c in run_quality_checks(db).checks if c.name == "unexplained_jumps").count


def test_update_fetches_from_last_bar_with_overlap(db: Session) -> None:
    _universe_with(db, listing("AAPL", "XNAS", "Apple"))
    provider = FakeProvider(
        histories={"AAPL": PriceHistory(bars=bars(dt.date(2026, 11, 1), [10.0] * 20))}
    )
    backfill_prices(db, provider, start=dt.date(2026, 11, 1))
    provider.history_calls.clear()

    update_prices(db, provider)
    assert provider.history_calls == [(("AAPL",), dt.date(2026, 11, 20) - dt.timedelta(days=5))]


def test_update_refetches_full_history_after_new_split(db: Session) -> None:
    _universe_with(db, listing("NVDA", "XNAS", "Nvidia"))
    start = dt.date(2026, 11, 1)
    provider = FakeProvider(histories={"NVDA": PriceHistory(bars=bars(start, [1000.0] * 10))})
    backfill_prices(db, provider, start=start)

    # A 10:1 split happens; the provider now serves split-adjusted history.
    split_day = start + dt.timedelta(days=10)
    provider.histories["NVDA"] = PriceHistory(
        bars=bars(start, [100.0] * 15), splits=[Split(split_day, 10.0)]
    )
    stats = update_prices(db, provider)
    assert stats.refetched_after_split == ["NVDA"]
    sec = security_by_symbol(db, "NVDA")
    closes = set(db.scalars(select(DailyBar.close).where(DailyBar.security_id == sec.id)))
    assert closes == {100.0}


def test_failed_symbols_are_counted(db: Session) -> None:
    _universe_with(db, listing("GONE", "XNYS", "Gone Inc"))
    stats = backfill_prices(db, FakeProvider())
    assert stats.securities_failed == 1
    run = db.scalars(select(IngestRun).where(IngestRun.job == "backfill")).one()
    assert run.status == IngestStatus.FAILED


def test_quality_checks_flag_problems(db: Session) -> None:
    _universe_with(db, listing("JUMP", "XNYS", "Jumpy"), listing("NONE", "XNYS", "No Data"))
    provider = FakeProvider(
        histories={"JUMP": PriceHistory(bars=bars(dt.date(2026, 11, 2), [10.0, 10.0, 25.0]))}
    )
    backfill_prices(db, provider, start=dt.date(2026, 11, 1))
    report = {c.name: c for c in run_quality_checks(db).checks}
    assert report["missing_prices"].count == 1
    assert report["unexplained_jumps"].count == 1
    assert report["inconsistent_ohlc"].count == 0
    assert (db.scalar(select(func.count()).select_from(FxRate)) or 0) > 0
