import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    CorporateAction,
    CorporateActionType,
    Currency,
    DailyBar,
    Exchange,
    FxRate,
    Sector,
    Security,
    SecurityIdentifier,
    SecurityType,
)
from app.reference_data import CURRENCIES, EXCHANGES, SECTORS
from app.seed import seed_reference_data


def _exchange(db: Session, mic: str) -> Exchange:
    return db.execute(select(Exchange).where(Exchange.mic == mic)).scalar_one()


def _security(db: Session, symbol: str = "TEVA", mic: str = "XTAE") -> Security:
    exchange = _exchange(db, mic)
    security = Security(
        exchange=exchange,
        symbol=symbol,
        name="Teva Pharmaceutical Industries",
        security_type=SecurityType.EQUITY,
        currency_code=exchange.currency_code,
        country_code="IL",
        isin="IL0006290147",
    )
    security.identifiers.append(
        SecurityIdentifier(provider="yahoo", external_symbol=f"{symbol}.TA")
    )
    db.add(security)
    db.flush()
    return security


def test_seed_is_idempotent(db: Session) -> None:
    seed_reference_data(db)
    assert db.scalar(select(func.count()).select_from(Currency)) == len(CURRENCIES)
    assert db.scalar(select(func.count()).select_from(Exchange)) == len(EXCHANGES)
    assert db.scalar(select(func.count()).select_from(Sector)) == len(SECTORS)


def test_exchange_reference_data(db: Session) -> None:
    tase = _exchange(db, "XTAE")
    assert tase.timezone == "Asia/Jerusalem"
    assert tase.currency.code == "ILS"
    assert tase.yahoo_suffix == ".TA"


def test_security_with_bars_and_actions(db: Session) -> None:
    security = _security(db)
    db.add_all(
        [
            DailyBar(
                security_id=security.id, date=dt.date(2026, 11, 19), close=60.1, source="test"
            ),
            DailyBar(
                security_id=security.id,
                date=dt.date(2026, 11, 20),
                open=60.0,
                high=61.5,
                low=59.8,
                close=61.2,
                adj_close=61.2,
                volume=1_250_000,
                source="test",
            ),
            CorporateAction(
                security_id=security.id,
                ex_date=dt.date(2026, 6, 1),
                action_type=CorporateActionType.SPLIT,
                value=Decimal("2"),
                source="test",
            ),
        ]
    )
    db.flush()

    closes = db.scalars(
        select(DailyBar.close).where(DailyBar.security_id == security.id).order_by(DailyBar.date)
    ).all()
    assert closes == [60.1, 61.2]
    assert security.identifiers[0].external_symbol == "TEVA.TA"


def test_symbol_unique_per_exchange(db: Session) -> None:
    _security(db, symbol="ABC")
    with pytest.raises(IntegrityError):
        _security(db, symbol="ABC")


def test_same_symbol_allowed_on_different_exchanges(db: Session) -> None:
    first = _security(db, symbol="XYZ", mic="XTAE")
    exchange = _exchange(db, "XNYS")
    second = Security(
        exchange=exchange,
        symbol="XYZ",
        name="Another company",
        security_type=SecurityType.EQUITY,
        currency_code="USD",
    )
    db.add(second)
    db.flush()
    assert first.id != second.id


def test_duplicate_daily_bar_rejected(db: Session) -> None:
    security = _security(db)
    day = dt.date(2026, 11, 20)
    db.add(DailyBar(security_id=security.id, date=day, close=1.0, source="test"))
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(DailyBar(security_id=security.id, date=day, close=2.0, source="test"))
        db.flush()


def test_fx_rate(db: Session) -> None:
    db.add(FxRate(base="USD", quote="ILS", date=dt.date(2026, 11, 20), rate=3.71, source="test"))
    db.flush()
    rate = db.scalar(select(FxRate.rate).where(FxRate.base == "USD", FxRate.quote == "ILS"))
    assert rate == pytest.approx(3.71)
