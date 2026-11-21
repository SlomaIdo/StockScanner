import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Security
from app.pipeline.fx import update_fx
from app.pipeline.prices import backfill_prices
from app.pipeline.universe import UniverseGroup, build_universe
from app.providers.base import Bar, PriceHistory
from tests.fakes import FakeProvider, listing

TODAY = dt.date.today()


def _load(db: Session) -> None:
    fx = FakeProvider(fx={"ILS": [(TODAY - dt.timedelta(days=1), 3.7)]})
    update_fx(db, fx, start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(
        listings={
            "XTAE": [
                listing(
                    "TEVA.TA", "XTAE", "Teva Pharmaceutical", currency="ILS", divisor=100,
                    market_cap=150e9, sector="Healthcare",
                ),
                listing("ESLT.TA", "XTAE", "Elbit Systems", currency="ILS", market_cap=100e9,
                        sector="Industrials"),
            ],
            "XNAS": [listing("AAPL", "XNAS", "Apple Inc.", market_cap=3e12)],
        },
        histories={
            "TEVA.TA": PriceHistory(
                bars=[
                    Bar(dt.date(2026, 11, 19), 13000, 13300, 12900, 13100, 13100, 500),
                    Bar(dt.date(2026, 11, 20), 13100, 13400, 13000, 13210, 13210, 600),
                ]
            )
        },
    )  # fmt: skip
    groups = [
        UniverseGroup("IL", ("XTAE",), 1e6, None, "UTC", "18:00"),
        UniverseGroup("US", ("XNAS",), 1e6, None, "UTC", "18:00"),
    ]
    build_universe(db, provider, groups)
    backfill_prices(db, provider, start=dt.date(2026, 11, 1))


def _teva_id(db: Session) -> int:
    return db.execute(select(Security.id).where(Security.symbol == "TEVA")).scalar_one()


def test_exchanges(client: TestClient, db: Session) -> None:
    _load(db)
    exchanges = {e["mic"]: e for e in client.get("/api/exchanges").json()}
    assert exchanges["XTAE"]["securities"] == 2
    assert exchanges["XTAE"]["last_bar_date"] == "2026-11-20"
    assert exchanges["XLON"]["securities"] == 0


def test_sectors(client: TestClient, db: Session) -> None:
    _load(db)
    sectors = {s["name"]: s["securities"] for s in client.get("/api/sectors").json()}
    assert sectors["Healthcare"] == 1
    assert sectors["Technology"] == 1


def test_list_securities_sorted_by_market_cap(client: TestClient, db: Session) -> None:
    _load(db)
    body = client.get("/api/securities").json()
    assert body["total"] == 3
    assert [i["symbol"] for i in body["items"]] == ["AAPL", "TEVA", "ESLT"]


def test_list_securities_filters(client: TestClient, db: Session) -> None:
    _load(db)
    by_exchange = client.get("/api/securities", params={"exchange": "xtae"}).json()
    assert by_exchange["total"] == 2
    search = client.get("/api/securities", params={"q": "teva"}).json()
    assert [i["symbol"] for i in search["items"]] == ["TEVA"]
    assert search["items"][0]["price"] == 10.0  # from the snapshot listing
    by_sector = client.get("/api/securities", params={"sector": "Industrials"}).json()
    assert [i["symbol"] for i in by_sector["items"]] == ["ESLT"]
    assert client.get("/api/securities", params={"limit": 500}).status_code == 422


def test_security_detail_and_bars(client: TestClient, db: Session) -> None:
    _load(db)
    teva_id = _teva_id(db)
    detail = client.get(f"/api/securities/{teva_id}").json()
    assert detail["exchange_mic"] == "XTAE"
    assert detail["bar_count"] == 2
    assert detail["identifiers"] == [
        {"provider": "fake", "external_symbol": "TEVA.TA", "price_divisor": 100}
    ]

    bars = client.get(f"/api/securities/{teva_id}/bars").json()
    assert [b["close"] for b in bars] == [131.0, 132.1]
    recent = client.get(f"/api/securities/{teva_id}/bars", params={"start": "2026-11-20"})
    assert len(recent.json()) == 1


def test_security_not_found(client: TestClient, db: Session) -> None:
    assert client.get("/api/securities/999999").status_code == 404
    assert client.get("/api/securities/999999/bars").status_code == 404


def test_runs_and_quality(client: TestClient, db: Session) -> None:
    _load(db)
    runs = client.get("/api/ingest/runs").json()
    assert [r["job"] for r in runs][:3] == ["backfill", "universe", "fx"]
    quality = client.get("/api/data/quality").json()
    checks = {c["name"]: c["count"] for c in quality["checks"]}
    assert checks["missing_prices"] == 2  # ESLT and AAPL have no bars
    assert checks["inconsistent_ohlc"] == 0


def test_data_report(db: Session) -> None:
    from app.pipeline.report import build_report

    _load(db)
    report = build_report(db)
    assert report.startswith("# StockScanner data report")
    for section in (
        "## At a glance",
        "## Freshness",
        "## Coverage by exchange",
        "## Data quality",
        "## How to use the data",
    ):
        assert section in report
    assert "| IL | Tel Aviv Stock Exchange | XTAE |" in report
    assert "2026-11-20" in report  # latest bar date
