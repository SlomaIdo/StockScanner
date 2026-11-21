"""Build the tracked universe: which securities we follow, per market group.

Steps:
1. Ask the provider for equities on each exchange above a market-cap floor, tagged by sector.
2. Drop listings quoted in a foreign currency (e.g. Toyota in JPY on London), and passive
   quote lines with almost no trading relative to their size (e.g. Samsung quoted in EUR on
   Vienna: daily turnover ~0.000001% of market cap, vs >0.003% for real listings).
3. Resolve cross-listings: when the same company appears on several exchanges, the exchange
   where it trades most (by dollar volume) is primary. Other listings are kept as linked
   secondaries only if they carry real trading (>= 10% of the primary's dollar volume), e.g.
   Teva on TASE next to NYSE; passive quotes like Apple on Xetra are dropped.
4. Keep the top N per group by USD market cap.
5. Upsert securities, provider identifiers and today's quote snapshot.
"""

import datetime as dt
import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Exchange, QuoteSnapshot, Sector, Security, SecurityIdentifier, SecurityType
from app.pipeline.fx import latest_usd_rates
from app.pipeline.runs import track_run
from app.providers.base import Listing, ProviderError, UniverseProvider

log = logging.getLogger(__name__)

STALE_AFTER_DAYS = 14
DUAL_LISTING_MIN_VOLUME_SHARE = 0.10
# Daily dollar volume / market cap. Real listings, even illiquid ones, are well above this.
MIN_DAILY_TURNOVER = 1e-6

# Listings no general rule catches, excluded by hand: (exchange MIC, symbol) -> reason.
EXCLUDED_LISTINGS: dict[tuple[str, str], str] = {
    ("XETR", "1ANT"): "tracker certificate on a private company (Anthropic); not a listed equity",
    ("XSWX", "NOVNEE"): "second trading line of Novartis (same shares as NOVN)",
}


@dataclass(frozen=True)
class UniverseGroup:
    name: str
    mics: tuple[str, ...]
    min_market_cap_usd: float
    top_n: int | None
    schedule_timezone: str
    schedule_time: str  # HH:MM local, weekdays; after all exchanges in the group close
    enabled: bool = True


GROUPS: dict[str, UniverseGroup] = {
    g.name: g
    for g in [
        UniverseGroup("US", ("XNYS", "XNAS", "XASE"), 100e6, 3000, "America/New_York", "18:30"),
        UniverseGroup("IL", ("XTAE",), 1e6, None, "Asia/Jerusalem", "18:30"),
        UniverseGroup(
            "EU",
            (
                "XLON", "XETR", "XPAR", "XAMS", "XBRU", "XLIS", "XDUB", "XMIL",
                "XMAD", "XSWX", "XSTO", "XCSE", "XHEL", "XOSL", "XWBO", "XWAR",
            ),
            100e6,
            1500,
            "Europe/Berlin",
            "19:00",
        ),
        UniverseGroup(
            "ASIA", ("XTKS", "XKRX", "XTAI", "XHKG"), 500e6, 1500, "Asia/Tokyo", "18:30",
            enabled=False,
        ),
    ]
}  # fmt: skip


def resolve_groups(names: list[str] | None) -> list[UniverseGroup]:
    if not names:
        return [g for g in GROUPS.values() if g.enabled]
    unknown = [n for n in names if n.upper() not in GROUPS]
    if unknown:
        raise ValueError(f"Unknown group(s): {', '.join(unknown)}. Known: {', '.join(GROUPS)}")
    return [GROUPS[n.upper()] for n in names]


_LEGAL_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc",
    "ag", "sa", "se", "nv", "bv", "spa", "ab", "asa", "as", "oyj", "group", "holding",
    "holdings", "the", "class", "a", "b", "adr", "ads",
}  # fmt: skip


def company_key(name: str) -> str:
    """Normalize a company name for cross-listing matching ("Apple Inc." -> "apple")."""
    cleaned = re.sub(r"\b(class|series|cl)\s+[a-z0-9]\b", " ", name.lower())
    tokens = re.sub(r"[^a-z0-9 ]+", " ", cleaned).split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


@dataclass(frozen=True)
class Candidate:
    group: str
    listing: Listing
    market_cap_usd: float
    dollar_volume_usd: float


def is_passive_quote(c: Candidate) -> bool:
    """A quote line with (almost) no trading relative to market cap, e.g. foreign stocks
    listed in local currency on Vienna's or Warsaw's global segments."""
    if c.market_cap_usd <= 0:
        return False
    return c.dollar_volume_usd / c.market_cap_usd < MIN_DAILY_TURNOVER


@dataclass(frozen=True)
class Resolved:
    candidate: Candidate
    primary_symbol: str | None  # provider symbol of the primary listing; None if primary


def resolve_cross_listings(candidates: list[Candidate]) -> list[Resolved]:
    """Pick each company's primary exchange and keep only meaningful secondary listings.

    Several share classes on the same exchange (e.g. GOOGL and GOOG) are all kept as primary.
    """
    by_company: dict[str, list[Candidate]] = defaultdict(list)
    for c in candidates:
        by_company[company_key(c.listing.name) or c.listing.provider_symbol].append(c)

    resolved: list[Resolved] = []
    for group in by_company.values():
        volume_by_exchange: dict[str, float] = defaultdict(float)
        for c in group:
            volume_by_exchange[c.listing.exchange_mic] += c.dollar_volume_usd
        home = max(volume_by_exchange, key=lambda mic: volume_by_exchange[mic])
        home_volume = volume_by_exchange[home]
        primary = max(
            (c for c in group if c.listing.exchange_mic == home),
            key=lambda c: c.dollar_volume_usd,
        )
        for c in group:
            mic = c.listing.exchange_mic
            if mic == home:
                resolved.append(Resolved(c, None))
            elif volume_by_exchange[mic] >= DUAL_LISTING_MIN_VOLUME_SHARE * home_volume:
                resolved.append(Resolved(c, primary.listing.provider_symbol))
    return resolved


@dataclass
class UniverseResult:
    selected: int = 0
    created: int = 0
    deactivated: int = 0


def build_universe(
    session: Session, provider: UniverseProvider, groups: list[UniverseGroup]
) -> UniverseResult:
    today = dt.date.today()
    rates = latest_usd_rates(session)
    exchanges = {e.mic: e for e in session.scalars(select(Exchange))}
    sectors = {s.name: s.id for s in session.scalars(select(Sector))}
    result = UniverseResult()

    scope = ",".join(g.name for g in groups)
    with track_run(session, "universe", scope) as run:
        candidates: list[Candidate] = []
        rejected: list[str] = []  # provider symbols deliberately excluded this run
        for group in groups:
            for mic in group.mics:
                exchange = exchanges[mic]
                rate = rates.get(exchange.currency_code)
                if rate is None:
                    run.failed += 1
                    run.note(f"{mic}: no FX rate for {exchange.currency_code}; run `fx` first")
                    continue
                if not provider.supports_exchange(mic):
                    run.note(f"{mic}: not supported by {provider.name}")
                    continue
                try:
                    listings = provider.list_equities(
                        mic, list(sectors), group.min_market_cap_usd * rate
                    )
                except ProviderError as exc:
                    run.failed += 1
                    run.note(f"{mic}: {exc}")
                    continue
                foreign = passive = 0
                for listing in listings:
                    if listing.currency != exchange.currency_code:
                        foreign += 1
                        continue
                    if (mic, listing.symbol) in EXCLUDED_LISTINGS:
                        rejected.append(listing.provider_symbol)
                        continue
                    candidate = Candidate(
                        group=group.name,
                        listing=listing,
                        market_cap_usd=(listing.market_cap or 0.0) / rate,
                        dollar_volume_usd=(listing.avg_volume_3m or 0.0)
                        * (listing.price or 0.0)
                        / rate,
                    )
                    if is_passive_quote(candidate):
                        passive += 1
                        rejected.append(listing.provider_symbol)
                        continue
                    candidates.append(candidate)
                run.ok += 1
                run.note(
                    f"{mic}: {len(listings)} listings ({foreign} foreign-currency, "
                    f"{passive} passive quotes dropped)"
                )

        # Also compare against listings already tracked in *other* groups, so a group refreshed
        # on its own (as the nightly scheduler does) still recognises cross-listings, e.g. a
        # US company's Xetra line during the EU refresh.
        refreshed_mics = [m for g in groups for m in g.mics]
        references, reference_ids = _reference_candidates(
            session, provider.name, refreshed_mics, rates
        )
        resolved = resolve_cross_listings(candidates + references)
        selected: list[Resolved] = []
        for group in groups:
            in_group = sorted(
                (r for r in resolved if r.candidate.group == group.name),
                key=lambda r: r.candidate.market_cap_usd,
                reverse=True,
            )
            chosen = in_group[: group.top_n] if group.top_n else in_group
            secondaries = sum(1 for r in chosen if r.primary_symbol)
            run.note(
                f"group {group.name}: {len(chosen)} selected of {len(in_group)} "
                f"({secondaries} secondary listings)"
            )
            selected.extend(chosen)

        ids: dict[str, int] = dict(reference_ids)
        for r in selected:
            security, created = _upsert_security(
                session, provider.name, r.candidate, exchanges, sectors, today
            )
            ids[r.candidate.listing.provider_symbol] = security.id
            result.created += int(created)
        for r in selected:
            security_id = ids[r.candidate.listing.provider_symbol]
            primary_id = ids.get(r.primary_symbol) if r.primary_symbol else None
            session.execute(
                update(Security)
                .where(Security.id == security_id)
                .values(primary_security_id=primary_id)
            )
        result.selected = len(selected)
        session.commit()

        # Listings we deliberately rejected (passive quotes, minor cross-listings) are
        # deactivated now rather than after the grace period.
        kept = {r.candidate.listing.provider_symbol for r in resolved}
        rejected += [
            c.listing.provider_symbol for c in candidates if c.listing.provider_symbol not in kept
        ]
        if rejected:
            rejected_ids = select(SecurityIdentifier.security_id).where(
                SecurityIdentifier.provider == provider.name,
                SecurityIdentifier.external_symbol.in_(rejected),
            )
            dropped = session.execute(
                update(Security)
                .where(Security.is_active.is_(True), Security.id.in_(rejected_ids))
                .values(is_active=False)
            )
            result.deactivated += dropped.rowcount  # type: ignore[attr-defined]
            session.commit()

        # Securities no longer returned at all get a grace period (screeners can be flaky),
        # and only within exchanges that were refreshed successfully this run.
        refreshed = {c.listing.exchange_mic for c in candidates}
        if refreshed:
            cutoff = today - dt.timedelta(days=STALE_AFTER_DAYS)
            stale = session.execute(
                update(Security)
                .where(
                    Security.is_active.is_(True),
                    Security.exchange_id.in_([exchanges[m].id for m in refreshed]),
                    Security.last_seen_on < cutoff,
                )
                .values(is_active=False)
            )
            result.deactivated += stale.rowcount  # type: ignore[attr-defined]
            session.commit()
        run.note(
            f"selected={result.selected} created={result.created} deactivated={result.deactivated}"
        )
    return result


REFERENCE_GROUP = "__reference__"


def _reference_candidates(
    session: Session, provider_name: str, refreshed_mics: list[str], rates: dict[str, float]
) -> tuple[list[Candidate], dict[str, int]]:
    """Active securities outside the refreshed exchanges, as candidates built from their
    latest snapshot. They take part in cross-listing resolution but are never re-selected."""
    rows = session.execute(
        text(
            """
            SELECT s.id, i.external_symbol, s.symbol, e.mic, s.name, s.currency_code,
                   i.price_divisor, q.price, q.market_cap, q.avg_volume_3m
            FROM securities s
            JOIN exchanges e ON e.id = s.exchange_id
            JOIN security_identifiers i ON i.security_id = s.id AND i.provider = :provider
            JOIN LATERAL (
                SELECT price, market_cap, avg_volume_3m FROM quote_snapshots
                WHERE security_id = s.id ORDER BY date DESC LIMIT 1
            ) q ON true
            WHERE s.is_active AND NOT (e.mic = ANY(:mics))
            """
        ),
        {"provider": provider_name, "mics": refreshed_mics},
    )
    candidates: list[Candidate] = []
    ids: dict[str, int] = {}
    for r in rows:
        rate = rates.get(r.currency_code)
        if not rate:
            continue
        listing = Listing(
            provider_symbol=r.external_symbol,
            symbol=r.symbol,
            exchange_mic=r.mic,
            name=r.name,
            currency=r.currency_code,
            price_divisor=r.price_divisor,
            sector=None,
            price=r.price,
            market_cap=r.market_cap,
            avg_volume_3m=r.avg_volume_3m,
        )
        candidates.append(
            Candidate(
                group=REFERENCE_GROUP,
                listing=listing,
                market_cap_usd=(r.market_cap or 0.0) / rate,
                dollar_volume_usd=(r.avg_volume_3m or 0.0) * (r.price or 0.0) / rate,
            )
        )
        ids[r.external_symbol] = r.id
    return candidates, ids


def _upsert_security(
    session: Session,
    provider_name: str,
    c: Candidate,
    exchanges: dict[str, Exchange],
    sectors: dict[str, int],
    today: dt.date,
) -> tuple[Security, bool]:
    listing = c.listing
    exchange = exchanges[listing.exchange_mic]
    identifier = session.scalar(
        select(SecurityIdentifier).where(
            SecurityIdentifier.provider == provider_name,
            SecurityIdentifier.external_symbol == listing.provider_symbol,
        )
    )
    security = identifier.security if identifier else None
    if security is None:
        security = session.scalar(
            select(Security).where(
                Security.exchange_id == exchange.id, Security.symbol == listing.symbol
            )
        )
    created = security is None
    if security is None:
        security = Security(
            exchange_id=exchange.id,
            symbol=listing.symbol,
            security_type=SecurityType.EQUITY,
        )
        session.add(security)

    security.name = listing.name
    security.currency_code = listing.currency
    security.sector_id = sectors.get(listing.sector) if listing.sector else None
    security.is_active = True
    security.last_seen_on = today
    if listing.first_trade_date and not security.listed_on:
        security.listed_on = listing.first_trade_date
    session.flush()

    if identifier is None:
        identifier = SecurityIdentifier(
            security_id=security.id,
            provider=provider_name,
            external_symbol=listing.provider_symbol,
        )
        session.add(identifier)
    identifier.price_divisor = listing.price_divisor

    snapshot = {
        "security_id": security.id,
        "date": today,
        "price": listing.price,
        "market_cap": listing.market_cap,
        "market_cap_usd": c.market_cap_usd or None,
        "shares_outstanding": listing.shares_outstanding,
        "avg_volume_3m": listing.avg_volume_3m,
        "trailing_pe": listing.trailing_pe,
        "price_to_book": listing.price_to_book,
        "dividend_yield": listing.dividend_yield,
        "source": provider_name,
    }
    stmt = insert(QuoteSnapshot).values(snapshot)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["security_id", "date"],
            set_={k: stmt.excluded[k] for k in snapshot if k not in ("security_id", "date")},
        )
    )
    return security, created
