"""Fundamentals ingest: SEC EDGAR for SEC filers, Yahoo for everyone else, plus profiles.

- ``map_sec_ciks``: link US listings to SEC company ids (CIK) via the SEC ticker list.
- ``update_fundamentals``: fetch statements for companies whose data is missing or stale.
- ``update_profiles``: country of domicile and industry (Yahoo) for every tracked company.

Work is incremental: each run takes the stalest companies first, up to a limit, so the
nightly job spreads the load and a full refresh happens every few days.
"""

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import ScalarSelect, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.fundamentals.countries import country_code
from app.models import (
    Exchange,
    FinancialFact,
    Industry,
    QuoteSnapshot,
    Sector,
    Security,
    SecurityIdentifier,
)
from app.pipeline.runs import track_run
from app.providers.base import Fact, FundamentalsProvider, Profile, ProviderError

log = logging.getLogger(__name__)

US_MICS = ("XNYS", "XNAS", "XASE")
SEC = "sec"
YAHOO = "yahoo"


@dataclass
class FundamentalsStats:
    companies_ok: int = 0
    companies_failed: int = 0
    facts_stored: int = 0


# -- SEC company ids ------------------------------------------------------------------


def map_sec_ciks(session: Session, ticker_map: dict[str, tuple[int, str]]) -> int:
    """Attach SEC CIKs to active US listings (one listing per company, the largest)."""
    rows = session.execute(
        select(Security.id, Security.symbol)
        .join(Exchange, Exchange.id == Security.exchange_id)
        .where(Security.is_active.is_(True), Exchange.mic.in_(US_MICS))
        .order_by(_latest_market_cap(Security.id).desc().nulls_last())
    ).all()
    existing = {
        ext: sid
        for sid, ext in session.execute(
            select(SecurityIdentifier.security_id, SecurityIdentifier.external_symbol).where(
                SecurityIdentifier.provider == SEC
            )
        )
    }
    mapped_securities = set(existing.values())
    created = 0
    for security_id, symbol in rows:
        hit = ticker_map.get(symbol.upper())
        if hit is None or security_id in mapped_securities:
            continue
        cik = str(hit[0])
        if cik in existing:  # another share class of the same company already holds it
            continue
        session.add(SecurityIdentifier(security_id=security_id, provider=SEC, external_symbol=cik))
        existing[cik] = security_id
        mapped_securities.add(security_id)
        created += 1
    session.commit()
    return created


def _latest_market_cap(security_id: object) -> ScalarSelect[float | None]:
    return (
        select(QuoteSnapshot.market_cap_usd)
        .where(QuoteSnapshot.security_id == security_id)
        .order_by(QuoteSnapshot.date.desc())
        .limit(1)
        .scalar_subquery()
    )


# -- fundamentals ---------------------------------------------------------------------


def update_fundamentals(
    session: Session,
    provider: FundamentalsProvider,
    max_age_days: int,
    limit: int | None = None,
) -> FundamentalsStats:
    """Fetch fundamentals for companies with missing or stale data from ``provider``.

    SEC covers securities that have a CIK. Yahoo covers primary listings without SEC data.
    """
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=max_age_days)
    ident = SecurityIdentifier
    stmt = (
        select(ident)
        .join(Security, Security.id == ident.security_id)
        .where(
            Security.is_active.is_(True),
            ident.provider == provider.name,
            or_(ident.fundamentals_fetched_at.is_(None), ident.fundamentals_fetched_at < cutoff),
        )
        .order_by(
            ident.fundamentals_fetched_at.asc().nulls_first(),
            _latest_market_cap(Security.id).desc().nulls_last(),
        )
    )
    if provider.name != SEC:
        # Fill in for companies without SEC data: non-US companies, and SEC filers whose
        # filings have no XBRL data yet (recent IPOs, many foreign and fund filers).
        stmt = stmt.where(
            Security.primary_security_id.is_(None),
            ~select(FinancialFact.id)
            .where(and_(FinancialFact.security_id == Security.id, FinancialFact.source == SEC))
            .exists(),
        )
    if limit:
        stmt = stmt.limit(limit)
    identifiers = list(session.scalars(stmt))

    stats = FundamentalsStats()
    with track_run(
        session, f"fundamentals:{provider.name}", f"{len(identifiers)} companies"
    ) as run:
        for identifier in identifiers:
            try:
                profile, facts = provider.fundamentals(identifier.external_symbol)
            except ProviderError as exc:
                stats.companies_failed += 1
                run.note(f"{identifier.external_symbol}: {exc}")
                continue
            now = dt.datetime.now(dt.UTC)
            symbol = identifier.external_symbol
            try:
                identifier.fundamentals_fetched_at = now
                if profile is not None:
                    apply_profile(session, identifier.security_id, profile)
                    identifier.profile_fetched_at = now
                stored = (
                    store_facts(session, identifier.security_id, provider.name, facts)
                    if facts
                    else 0
                )
                session.commit()
            except SQLAlchemyError as exc:
                # One bad payload must not stop the run; it is retried next time.
                session.rollback()
                stats.companies_failed += 1
                run.note(f"{symbol}: could not store: {str(exc).splitlines()[0][:200]}")
                continue
            if facts:
                stats.facts_stored += stored
                stats.companies_ok += 1
            else:
                stats.companies_failed += 1
            if (stats.companies_ok + stats.companies_failed) % 50 == 0:
                log.info(
                    "progress: %d ok, %d without data, %d facts",
                    stats.companies_ok,
                    stats.companies_failed,
                    stats.facts_stored,
                )
        run.ok = stats.companies_ok
        run.failed = stats.companies_failed
        run.note(f"stored {stats.facts_stored} new facts")
    return stats


def store_facts(session: Session, security_id: int, source: str, facts: list[Fact]) -> int:
    """Insert facts that are new or whose value changed; returns how many were stored."""
    latest: dict[tuple[str, str, dt.date], float] = {}
    rows = session.execute(
        select(
            FinancialFact.metric,
            FinancialFact.period_type,
            FinancialFact.period_end,
            FinancialFact.value,
        )
        .where(FinancialFact.security_id == security_id, FinancialFact.source == source)
        .order_by(FinancialFact.known_since)
    )
    for metric, ptype, end, value in rows:
        latest[(metric, ptype, end)] = value

    new_rows = []
    for fact in sorted(facts, key=lambda f: f.known_since):
        key = (fact.metric, fact.period_type, fact.period_end)
        previous = latest.get(key)
        if previous is not None and abs(previous - fact.value) <= 1e-9 * max(1.0, abs(previous)):
            continue
        latest[key] = fact.value
        new_rows.append(
            {
                "security_id": security_id,
                "source": source,
                "metric": fact.metric,
                "period_type": fact.period_type,
                "period_start": fact.period_start,
                "period_end": fact.period_end,
                "fiscal_year": fact.fiscal_year,
                "fiscal_period": fact.fiscal_period,
                "value": fact.value,
                "unit": fact.unit,
                "known_since": fact.known_since,
                "form": fact.form,
            }
        )
    if not new_rows:
        return 0
    result = session.execute(
        insert(FinancialFact)
        .on_conflict_do_nothing(
            index_elements=[
                "security_id",
                "source",
                "metric",
                "period_type",
                "period_end",
                "known_since",
            ]
        )
        .returning(FinancialFact.id),
        new_rows,
    )
    return len(result.all())


# -- profiles -------------------------------------------------------------------------


class ProfileProvider(FundamentalsProvider, Protocol):
    def profile(self, external_symbol: str) -> Profile | None: ...


def update_profiles(
    session: Session, provider: ProfileProvider, max_age_days: int, limit: int | None = None
) -> int:
    """Fetch country and industry for active securities whose profile is missing or stale."""
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=max_age_days)
    ident = SecurityIdentifier
    stmt = (
        select(ident)
        .join(Security, Security.id == ident.security_id)
        .where(
            Security.is_active.is_(True),
            ident.provider == provider.name,
            or_(ident.profile_fetched_at.is_(None), ident.profile_fetched_at < cutoff),
        )
        .order_by(
            ident.profile_fetched_at.asc().nulls_first(),
            _latest_market_cap(Security.id).desc().nulls_last(),
        )
    )
    if limit:
        stmt = stmt.limit(limit)
    identifiers = list(session.scalars(stmt))
    updated = 0
    with track_run(session, "profiles", f"{len(identifiers)} companies") as run:
        for identifier in identifiers:
            try:
                profile = provider.profile(identifier.external_symbol)
            except ProviderError as exc:
                run.failed += 1
                run.note(f"{identifier.external_symbol}: {exc}")
                continue
            identifier.profile_fetched_at = dt.datetime.now(dt.UTC)
            if profile is not None:
                apply_profile(session, identifier.security_id, profile)
                updated += 1
                run.ok += 1
            else:
                run.failed += 1
            session.commit()
    return updated


def apply_profile(session: Session, security_id: int, profile: Profile) -> None:
    security = session.get(Security, security_id)
    if security is None:
        return
    code = country_code(profile.country)
    if code:
        security.country_code = code
    elif profile.country:
        log.debug("unknown country name %r for security %s", profile.country, security_id)
    if profile.industry:
        sector_name = profile.sector or (security.sector.name if security.sector else None)
        sector_id = (
            session.scalar(select(Sector.id).where(Sector.name == sector_name))
            if sector_name
            else None
        )
        if sector_id is not None:
            security.industry_id = _industry_id(session, sector_id, profile.industry)


def _industry_id(session: Session, sector_id: int, name: str) -> int:
    session.execute(
        insert(Industry).values(sector_id=sector_id, name=name).on_conflict_do_nothing()
    )
    industry_id = session.scalar(
        select(Industry.id).where(Industry.sector_id == sector_id, Industry.name == name)
    )
    assert industry_id is not None
    return industry_id


def facts_owner(session: Session, security: Security) -> int | None:
    """Which security holds this company's fundamentals.

    Facts live on one listing per company: the security itself, else its primary listing,
    else another share class of the same company on the same exchange (e.g. GOOG -> GOOGL).
    """
    from app.pipeline.universe import company_key

    has_facts = select(FinancialFact.id).where(FinancialFact.security_id == Security.id).exists()
    candidates = [security.id]
    if security.primary_security_id:
        candidates.append(security.primary_security_id)
    for candidate in candidates:
        if session.scalar(select(func.count()).where(FinancialFact.security_id == candidate)):
            return candidate
    key = company_key(security.name)
    siblings = session.execute(
        select(Security.id, Security.name).where(
            Security.exchange_id == security.exchange_id,
            Security.id != security.id,
            has_facts,
        )
    ).all()
    return next((sid for sid, name in siblings if company_key(name) == key), None)
