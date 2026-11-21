"""Data pipeline command-line interface.

Usage: ``uv run stockscanner --help`` (or ``python -m app.cli``).
"""

import datetime as dt
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.models import DailyBar, Exchange, IngestRun, Security
from app.pipeline.fundamentals import map_sec_ciks, update_fundamentals, update_profiles
from app.pipeline.fx import update_fx
from app.pipeline.prices import backfill_prices, update_prices
from app.pipeline.quality import run_quality_checks
from app.pipeline.report import build_report
from app.pipeline.universe import build_universe, resolve_groups
from app.providers.sec import SecProvider
from app.providers.yahoo import YahooProvider

DEFAULT_REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "DATA_REPORT.md"

app = typer.Typer(help="StockScanner data pipeline", no_args_is_help=True)

GroupOpt = Annotated[
    list[str] | None, typer.Option("--group", "-g", help="Market group: US, IL, EU, ASIA")
]
MicOpt = Annotated[
    list[str] | None, typer.Option("--mic", "-m", help="Exchange MIC, e.g. XTAE (overrides group)")
]


def _session() -> Session:
    configure_logging(get_settings().log_level)
    return get_sessionmaker()()


def _mics(groups: list[str] | None, mics: list[str] | None) -> list[str] | None:
    if mics:
        return [m.upper() for m in mics]
    if groups:
        return [m for g in resolve_groups(groups) for m in g.mics]
    return None


@app.command()
def fx(years: Annotated[int | None, typer.Option(help="History to fetch")] = None) -> None:
    """Fetch FX rates against USD (incremental unless --years is given)."""
    start = dt.date.today() - dt.timedelta(days=365 * years) if years else None
    with _session() as session:
        rows = update_fx(session, YahooProvider(), start)
    typer.echo(f"Stored {rows} FX rates")


@app.command()
def universe(group: GroupOpt = None) -> None:
    """Refresh the tracked universe and today's quote snapshots."""
    with _session() as session:
        result = build_universe(session, YahooProvider(), resolve_groups(group))
    typer.echo(
        f"Selected {result.selected} securities "
        f"({result.created} new, {result.deactivated} deactivated)"
    )


@app.command()
def backfill(
    group: GroupOpt = None,
    mic: MicOpt = None,
    years: Annotated[int, typer.Option(help="Years of history")] = 10,
    limit: Annotated[int | None, typer.Option(help="Max securities (for testing)")] = None,
    all_securities: Annotated[
        bool, typer.Option("--all", help="Refetch securities that already have history")
    ] = False,
) -> None:
    """Fetch price history for securities that have none yet."""
    start = dt.date.today() - dt.timedelta(days=365 * years)
    with _session() as session:
        stats = backfill_prices(
            session,
            YahooProvider(),
            _mics(group, mic),
            start=start,
            only_missing=not all_securities,
            limit=limit,
        )
    typer.echo(
        f"{stats.securities_ok} ok, {stats.securities_failed} failed, {stats.bars} bars stored"
    )


@app.command()
def update(group: GroupOpt = None, mic: MicOpt = None) -> None:
    """Fetch the latest bars for all active securities."""
    with _session() as session:
        stats = update_prices(session, YahooProvider(), _mics(group, mic))
    typer.echo(
        f"{stats.securities_ok} ok, {stats.securities_failed} failed, {stats.bars} bars stored"
    )


def _sec() -> SecProvider:
    return SecProvider(get_settings().sec_user_agent)


@app.command("sec-map")
def sec_map() -> None:
    """Link US listings to SEC company ids (CIK)."""
    with _session() as session:
        created = map_sec_ciks(session, _sec().ticker_map())
    typer.echo(f"Mapped {created} new US listings to SEC CIKs")


@app.command()
def fundamentals(
    source: Annotated[str, typer.Option(help="sec (US filers) or yahoo (everyone else)")] = "sec",
    limit: Annotated[int | None, typer.Option(help="Max companies this run")] = None,
    max_age: Annotated[int, typer.Option(help="Refetch data older than this many days")] = 7,
) -> None:
    """Fetch financial statements for companies with missing or stale data."""
    provider = _sec() if source == "sec" else YahooProvider()
    with _session() as session:
        if source == "sec":
            map_sec_ciks(session, _sec().ticker_map())
        stats = update_fundamentals(session, provider, max_age, limit)
    typer.echo(
        f"{stats.companies_ok} companies updated, {stats.companies_failed} without data, "
        f"{stats.facts_stored} new facts"
    )


@app.command()
def profiles(
    limit: Annotated[int | None, typer.Option(help="Max companies this run")] = None,
    max_age: Annotated[int, typer.Option(help="Refetch profiles older than this")] = 90,
) -> None:
    """Fetch country of domicile and industry for tracked companies (Yahoo)."""
    with _session() as session:
        updated = update_profiles(session, YahooProvider(), max_age, limit)
    typer.echo(f"Updated {updated} profiles")


@app.command()
def nightly(group: GroupOpt = None) -> None:
    """Full nightly job: FX, universe, prices, then a batch of fundamentals and profiles."""
    run_nightly(group)


# Per-night batch sizes: the stalest companies go first, so everything cycles through.
NIGHTLY_SEC_BATCH = 800  # ~0.5 s each; full US refresh about every 4 nights
NIGHTLY_YAHOO_FUNDAMENTALS_BATCH = 300  # ~3 s each
NIGHTLY_PROFILE_BATCH = 300


def run_nightly(group: list[str] | None) -> None:
    provider = YahooProvider()
    groups = resolve_groups(group)
    with _session() as session:
        update_fx(session, provider)
        build_universe(session, provider, groups)
        update_prices(session, provider, [m for g in groups for m in g.mics])
        names = {g.name for g in groups}
        if "US" in names:
            sec = _sec()
            map_sec_ciks(session, sec.ticker_map())
            update_fundamentals(session, sec, max_age_days=7, limit=NIGHTLY_SEC_BATCH)
            update_profiles(session, provider, max_age_days=90, limit=NIGHTLY_PROFILE_BATCH)
        if names - {"US"}:
            update_fundamentals(
                session, provider, max_age_days=30, limit=NIGHTLY_YAHOO_FUNDAMENTALS_BATCH
            )


@app.command()
def quality() -> None:
    """Run data-quality checks and print findings."""
    with _session() as session:
        report = run_quality_checks(session)
    for check in report.checks:
        mark = "OK " if check.count == 0 else "!! "
        typer.echo(f"{mark}{check.name}: {check.count}  ({check.description})")
        for sample in check.samples:
            typer.echo(f"      {sample}")


@app.command()
def report(
    output: Annotated[Path, typer.Option(help="Where to write the Markdown report")] = (
        DEFAULT_REPORT_PATH
    ),
) -> None:
    """Write a Markdown report: coverage, freshness, quality and a usage guide."""
    with _session() as session:
        markdown = build_report(session)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    typer.echo(f"Wrote {output}")


@app.command()
def status() -> None:
    """Show coverage per exchange and the latest pipeline runs."""
    with _session() as session:
        rows = session.execute(
            select(
                Exchange.mic,
                Exchange.name,
                func.count(func.distinct(Security.id)).filter(Security.is_active),
                func.max(DailyBar.date),
            )
            .outerjoin(Security, Security.exchange_id == Exchange.id)
            .outerjoin(DailyBar, DailyBar.security_id == Security.id)
            .group_by(Exchange.mic, Exchange.name)
            .order_by(Exchange.mic)
        ).all()
        typer.echo(f"{'MIC':6} {'Exchange':32} {'Stocks':>7}  Last bar")
        for mic, name, count, last in rows:
            typer.echo(f"{mic:6} {name[:32]:32} {count:>7}  {last or '-'}")
        typer.echo("\nRecent runs:")
        for run in session.scalars(select(IngestRun).order_by(IngestRun.id.desc()).limit(10)):
            typer.echo(
                f"  #{run.id} {run.job:9} {run.status:8} ok={run.items_ok} "
                f"failed={run.items_failed} {run.started_at:%Y-%m-%d %H:%M} {run.scope or ''}"
            )


if __name__ == "__main__":
    app()
