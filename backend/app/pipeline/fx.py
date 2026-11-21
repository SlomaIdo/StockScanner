"""Daily FX rates, stored as units of each currency per 1 USD."""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Currency, FxRate
from app.pipeline.runs import track_run
from app.providers.base import PriceProvider

DEFAULT_HISTORY_YEARS = 10
OVERLAP_DAYS = 7


def update_fx(session: Session, provider: PriceProvider, start: dt.date | None = None) -> int:
    """Fetch FX rates from ``start`` (default: since the last stored rate, or 10 years)."""
    currencies = [c for c in session.scalars(select(Currency.code)) if c != "USD"]
    if start is None:
        last = session.scalar(select(func.max(FxRate.date)).where(FxRate.base == "USD"))
        start = (
            last - dt.timedelta(days=OVERLAP_DAYS)
            if last
            else dt.date.today() - dt.timedelta(days=365 * DEFAULT_HISTORY_YEARS)
        )

    with track_run(session, "fx", ",".join(currencies)) as run:
        rates = provider.fx_to_usd(currencies, start)
        rows = [
            {"base": "USD", "quote": ccy, "date": day, "rate": rate, "source": provider.name}
            for ccy, series in rates.items()
            for day, rate in series
        ]
        if rows:
            stmt = insert(FxRate)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["base", "quote", "date"],
                    set_={"rate": stmt.excluded.rate, "source": stmt.excluded.source},
                ),
                rows,
            )
        session.commit()
        run.ok = len(rates)
        missing = sorted(set(currencies) - set(rates))
        run.failed = len(missing)
        if missing:
            run.note(f"no FX data for: {', '.join(missing)}")
        return len(rows)


def latest_usd_rates(session: Session) -> dict[str, float]:
    """Most recent rate per currency (units per USD). USD maps to 1.0."""
    latest = (
        select(FxRate.quote, func.max(FxRate.date).label("date"))
        .where(FxRate.base == "USD")
        .group_by(FxRate.quote)
        .subquery()
    )
    rows = session.execute(
        select(FxRate.quote, FxRate.rate).join(
            latest, (FxRate.quote == latest.c.quote) & (FxRate.date == latest.c.date)
        )
    ).all()
    rates = {quote: rate for quote, rate in rows}
    rates["USD"] = 1.0
    return rates
