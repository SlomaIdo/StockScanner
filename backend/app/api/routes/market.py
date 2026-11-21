"""Read API over reference data, the tracked universe and prices."""

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import (
    BarOut,
    ExchangeOut,
    IngestRunOut,
    QualityCheckOut,
    QualityReportOut,
    SectorOut,
    SecurityDetail,
    SecurityPage,
)
from app.db.session import get_db
from app.models import DailyBar, IngestRun, Security
from app.pipeline.quality import run_quality_checks

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]

# Latest quote snapshot per security.
_LATEST_SNAPSHOT = """
    LEFT JOIN LATERAL (
        SELECT q.price, q.market_cap_usd, q.date AS snapshot_date
        FROM quote_snapshots q WHERE q.security_id = s.id
        ORDER BY q.date DESC LIMIT 1
    ) snap ON true
"""


@router.get("/exchanges", response_model=list[ExchangeOut], tags=["reference"])
def list_exchanges(db: Db) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT e.mic, e.name, e.country_code, e.timezone, e.currency_code,
                   count(s.id) AS securities, max(last.d) AS last_bar_date
            FROM exchanges e
            LEFT JOIN securities s ON s.exchange_id = e.id AND s.is_active
            LEFT JOIN LATERAL (
                SELECT b.date AS d FROM daily_bars b
                WHERE b.security_id = s.id ORDER BY b.date DESC LIMIT 1
            ) last ON true
            GROUP BY e.id ORDER BY count(s.id) DESC, e.mic
            """
        )
    )
    return [dict(r._mapping) for r in rows]


@router.get("/sectors", response_model=list[SectorOut], tags=["reference"])
def list_sectors(db: Db) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT sec.id, sec.name, count(s.id) AS securities
            FROM sectors sec LEFT JOIN securities s ON s.sector_id = sec.id AND s.is_active
            GROUP BY sec.id ORDER BY sec.name
            """
        )
    )
    return [dict(r._mapping) for r in rows]


@router.get("/securities", response_model=SecurityPage, tags=["securities"])
def list_securities(
    db: Db,
    q: Annotated[str | None, Query(description="Search symbol or name")] = None,
    exchange: Annotated[str | None, Query(description="Exchange MIC")] = None,
    sector: Annotated[str | None, Query(description="Sector name")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    where = ["s.is_active"]
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if q:
        where.append("(s.symbol ILIKE :prefix OR s.name ILIKE :contains)")
        params |= {"prefix": f"{q}%", "contains": f"%{q}%"}
    if exchange:
        where.append("e.mic = :mic")
        params["mic"] = exchange.upper()
    if sector:
        where.append("sec.name = :sector")
        params["sector"] = sector
    base = f"""
        FROM securities s
        JOIN exchanges e ON e.id = s.exchange_id
        LEFT JOIN sectors sec ON sec.id = s.sector_id
        WHERE {" AND ".join(where)}
    """
    total = db.execute(text(f"SELECT count(*) {base}"), params).scalar_one()
    rows = db.execute(
        text(
            f"""
            SELECT s.id, s.symbol, s.name, e.mic AS exchange_mic, s.currency_code,
                   sec.name AS sector, snap.price, snap.market_cap_usd, snap.snapshot_date,
                   s.primary_security_id
            FROM securities s
            JOIN exchanges e ON e.id = s.exchange_id
            LEFT JOIN sectors sec ON sec.id = s.sector_id
            {_LATEST_SNAPSHOT}
            WHERE {" AND ".join(where)}
            ORDER BY snap.market_cap_usd DESC NULLS LAST, s.symbol
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    )
    return {"total": total, "items": [dict(r._mapping) for r in rows]}


@router.get("/securities/{security_id}", response_model=SecurityDetail, tags=["securities"])
def get_security(security_id: int, db: Db) -> dict[str, Any]:
    security = db.scalar(
        select(Security)
        .where(Security.id == security_id)
        .options(selectinload(Security.identifiers))
    )
    if security is None:
        raise HTTPException(status_code=404, detail="Security not found")
    row = db.execute(
        text(
            f"""
            SELECT e.mic AS exchange_mic, sec.name AS sector, snap.price, snap.market_cap_usd,
                   snap.snapshot_date,
                   (SELECT min(date) FROM daily_bars WHERE security_id = s.id) AS first_bar_date,
                   (SELECT max(date) FROM daily_bars WHERE security_id = s.id) AS last_bar_date,
                   (SELECT count(*) FROM daily_bars WHERE security_id = s.id) AS bar_count
            FROM securities s
            JOIN exchanges e ON e.id = s.exchange_id
            LEFT JOIN sectors sec ON sec.id = s.sector_id
            {_LATEST_SNAPSHOT}
            WHERE s.id = :id
            """
        ),
        {"id": security_id},
    ).one()
    return {
        "id": security.id,
        "symbol": security.symbol,
        "name": security.name,
        "currency_code": security.currency_code,
        "primary_security_id": security.primary_security_id,
        "country_code": security.country_code,
        "isin": security.isin,
        "listed_on": security.listed_on,
        "last_seen_on": security.last_seen_on,
        "is_active": security.is_active,
        "identifiers": security.identifiers,
        **row._mapping,
    }


@router.get("/securities/{security_id}/bars", response_model=list[BarOut], tags=["securities"])
def get_bars(
    security_id: int,
    db: Db,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[DailyBar]:
    if db.get(Security, security_id) is None:
        raise HTTPException(status_code=404, detail="Security not found")
    stmt = select(DailyBar).where(DailyBar.security_id == security_id).order_by(DailyBar.date)
    if start:
        stmt = stmt.where(DailyBar.date >= start)
    if end:
        stmt = stmt.where(DailyBar.date <= end)
    return list(db.scalars(stmt))


@router.get("/ingest/runs", response_model=list[IngestRunOut], tags=["data"])
def list_runs(db: Db, limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[IngestRun]:
    return list(db.scalars(select(IngestRun).order_by(IngestRun.id.desc()).limit(limit)))


@router.get("/data/quality", response_model=QualityReportOut, tags=["data"])
def data_quality(db: Db) -> QualityReportOut:
    report = run_quality_checks(db)
    return QualityReportOut(
        generated_at=report.generated_at,
        issues=report.issues,
        checks=[
            QualityCheckOut(
                name=c.name, description=c.description, count=c.count, samples=c.samples
            )
            for c in report.checks
        ],
    )
