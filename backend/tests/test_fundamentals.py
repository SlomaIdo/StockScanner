import datetime as dt
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.fundamentals.countries import country_code
from app.models import FinancialFact, Security, SecurityIdentifier
from app.pipeline.fundamentals import (
    facts_owner,
    map_sec_ciks,
    store_facts,
    update_fundamentals,
    update_profiles,
)
from app.pipeline.fx import update_fx
from app.pipeline.universe import UniverseGroup, build_universe
from app.providers.base import Profile
from app.providers.sec import parse_companyfacts
from app.providers.yahoo import parse_statement_frames
from tests.fakes import FakeFundamentals, FakeProvider, fact, listing

TODAY = dt.date.today()


def _row(val: float, end: str, filed: str, start: str | None = None, fp: str = "FY",
         form: str = "10-K") -> dict[str, Any]:  # fmt: skip
    row: dict[str, Any] = {"val": val, "end": end, "filed": filed, "fp": fp, "form": form}
    if start:
        row["start"] = start
    return row


def _concept(unit: str, *rows: dict[str, Any]) -> dict[str, Any]:
    return {"units": {unit: list(rows)}}


# -- SEC parsing ------------------------------------------------------------------


def test_parse_companyfacts_maps_and_prioritises_concepts() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                # Revenues (total) outranks the contract-revenue concept when both exist;
                # 2017 only has Revenues, 2018 has both.
                "Revenues": _concept(
                    "USD",
                    _row(100, "2017-12-31", "2018-02-01", "2017-01-01"),
                    _row(999, "2018-12-31", "2019-02-01", "2018-01-01"),
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _concept(
                    "USD",
                    _row(120, "2018-12-31", "2019-02-01", "2018-01-01"),
                    # 9-month year-to-date span: ignored.
                    _row(90, "2018-09-30", "2018-11-01", "2018-01-01", fp="Q3", form="10-Q"),
                    # Quarter.
                    _row(30, "2018-09-30", "2018-11-01", "2018-07-01", fp="Q3", form="10-Q"),
                ),
                "NetIncomeLoss": _concept(
                    "USD",
                    _row(10, "2018-12-31", "2019-02-01", "2018-01-01"),
                    # Same value repeated in the next 10-K: not a new fact.
                    _row(10, "2018-12-31", "2020-02-01", "2018-01-01"),
                    # Restated a year later: kept as a new fact.
                    _row(11, "2018-12-31", "2021-02-01", "2018-01-01"),
                ),
                "Assets": _concept("USD", _row(500, "2018-12-31", "2019-02-01")),
                "NetCashProvidedByUsedInOperatingActivities": _concept(
                    "USD", _row(50, "2018-12-31", "2019-02-01", "2018-01-01")
                ),
                "PaymentsToAcquirePropertyPlantAndEquipment": _concept(
                    "USD", _row(-20, "2018-12-31", "2019-02-01", "2018-01-01")
                ),
            }
        }
    }
    facts = parse_companyfacts(payload)

    def values(metric: str, ptype: str = "FY") -> list[tuple[str, float, str]]:
        return sorted(
            (str(f.period_end), f.value, str(f.known_since))
            for f in facts
            if f.metric == metric and f.period_type == ptype
        )

    assert values("revenue") == [
        ("2017-12-31", 100, "2018-02-01"),
        ("2018-12-31", 999, "2019-02-01"),
    ]
    assert values("revenue", "Q") == [("2018-09-30", 30, "2018-11-01")]
    assert values("net_income") == [
        ("2018-12-31", 10, "2019-02-01"),
        ("2018-12-31", 11, "2021-02-01"),
    ]
    assert values("total_assets") == [("2018-12-31", 500, "2019-02-01")]
    assert values("capex") == [("2018-12-31", 20, "2019-02-01")]  # stored positive
    assert values("free_cash_flow") == [("2018-12-31", 30, "2019-02-01")]


def test_parse_companyfacts_skips_invalid_units() -> None:
    payload = {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [_row(0.21, "2012-12-31", "2013-02-01", "2012-01-01")],
                        "BillionsCubicFeet": [_row(0.21, "2011-12-31", "2012-02-01", "2011-01-01")],
                    }
                },
                "Revenues": _concept("shares", _row(5, "2012-12-31", "2013-02-01", "2012-01-01")),
            }
        }
    }
    facts = parse_companyfacts(payload)
    assert [(f.metric, f.unit) for f in facts] == [("eps_diluted", "USD/shares")]


def test_parse_companyfacts_ifrs_units() -> None:
    payload = {
        "facts": {
            "ifrs-full": {
                "Revenue": _concept(
                    "TWD", _row(2.9e12, "2024-12-31", "2025-04-15", "2024-01-01", form="20-F")
                ),
                "BasicEarningsLossPerShare": _concept(
                    "TWD/shares",
                    _row(44.7, "2024-12-31", "2025-04-15", "2024-01-01", form="20-F"),
                ),
            }
        }
    }
    facts = {f.metric: f for f in parse_companyfacts(payload)}
    assert facts["revenue"].unit == "TWD"
    assert facts["revenue"].form == "20-F"
    assert facts["eps_basic"].unit == "TWD/shares"


# -- Yahoo parsing ----------------------------------------------------------------


def test_parse_statement_frames() -> None:
    cols = pd.to_datetime(["2025-12-31", "2024-12-31"])
    income = pd.DataFrame(
        {cols[0]: [36.8e9, 7.2e9, 5.1], cols[1]: [34.2e9, None, 2.7]},
        index=["Total Revenue", "Net Income Common Stockholders", "Diluted EPS"],
    )
    cash = pd.DataFrame({cols[0]: [-0.74e9], cols[1]: [-0.8e9]}, index=["Capital Expenditure"])
    facts = parse_statement_frames([("FY", income), ("FY", cash)], "EUR", TODAY)
    by = {(f.metric, f.period_end.year): f for f in facts}
    assert by[("revenue", 2025)].value == 36.8e9
    assert by[("revenue", 2025)].unit == "EUR"
    assert ("net_income", 2024) not in by  # missing values are skipped
    assert by[("eps_diluted", 2025)].unit == "EUR/shares"
    assert by[("capex", 2024)].value == 0.8e9
    assert all(f.known_since == TODAY for f in facts)


def test_country_codes() -> None:
    assert country_code("Israel") == "IL"
    assert country_code("United Kingdom") == "GB"
    assert country_code("Atlantis") is None
    assert country_code(None) is None


# -- storage and pipeline ---------------------------------------------------------


def _universe(db: Session) -> None:
    fx = FakeProvider(fx={"ILS": [(TODAY - dt.timedelta(days=1), 3.7)]})
    update_fx(db, fx, start=TODAY - dt.timedelta(days=10))
    provider = FakeProvider(
        name="yahoo",
        listings={
            "XNYS": [listing("TEVA", "XNYS", "Teva Pharmaceutical", avg_volume=1e7, price=25)],
            "XNAS": [
                listing("GOOGL", "XNAS", "Alphabet Inc. Class A", market_cap=3.3e12),
                listing("GOOG", "XNAS", "Alphabet Inc. Class C", market_cap=3.2e12),
            ],
            "XTAE": [
                listing("TEVA.TA", "XTAE", "Teva Pharmaceutical", currency="ILS", divisor=100,
                        avg_volume=2e6, price=90),
                listing("LUMI.TA", "XTAE", "Bank Leumi", currency="ILS", divisor=100,
                        sector="Financial Services"),
            ],
        },
    )  # fmt: skip
    groups = [
        UniverseGroup("US", ("XNYS", "XNAS"), 1e6, None, "UTC", "18:00"),
        UniverseGroup("IL", ("XTAE",), 1e6, None, "UTC", "18:00"),
    ]
    build_universe(db, provider, groups)


def _sec_id(db: Session, symbol: str) -> int:
    return db.execute(select(Security.id).where(Security.symbol == symbol)).scalars().first()  # type: ignore[return-value]


def test_store_facts_appends_only_changes(db: Session) -> None:
    _universe(db)
    sid = _sec_id(db, "GOOGL")
    first = [fact("revenue", "2025-12-31", 100.0, known="2026-02-01")]
    assert store_facts(db, sid, "sec", first) == 1
    assert store_facts(db, sid, "sec", first) == 0  # idempotent
    restated = [fact("revenue", "2025-12-31", 101.0, known="2027-02-01")]
    assert store_facts(db, sid, "sec", restated) == 1
    assert db.scalar(select(func.count()).select_from(FinancialFact)) == 2


def test_map_sec_ciks_one_listing_per_company(db: Session) -> None:
    _universe(db)
    created = map_sec_ciks(
        db, {"GOOGL": (1652044, "Nasdaq"), "GOOG": (1652044, "Nasdaq"), "TEVA": (818686, "NYSE")}
    )
    assert created == 2
    holders = dict(
        db.execute(
            select(SecurityIdentifier.external_symbol, Security.symbol)
            .join(Security)
            .where(SecurityIdentifier.provider == "sec")
        ).all()
    )
    assert holders == {"1652044": "GOOGL", "818686": "TEVA"}


def test_update_fundamentals_targets_and_profiles(db: Session) -> None:
    _universe(db)
    map_sec_ciks(db, {"GOOGL": (1652044, "Nasdaq"), "TEVA": (818686, "NYSE")})

    sec = FakeFundamentals(
        name="sec",
        data={
            "1652044": (None, [fact("revenue", "2025-12-31", 402.8e9)]),
            "818686": (None, [fact("revenue", "2025-12-31", 16.5e9)]),
        },
    )
    stats = update_fundamentals(db, sec, max_age_days=7)
    assert stats.companies_ok == 2
    # Fresh data is not fetched again until it is stale.
    assert update_fundamentals(db, sec, max_age_days=7).companies_ok == 0

    yahoo = FakeFundamentals(
        data={
            "LUMI.TA": (
                Profile(country="Israel", sector="Financial Services",
                        industry="Banks - Regional", reporting_currency="ILS"),
                [fact("revenue", "2025-12-31", 22.3e9, unit="ILS")],
            )
        }
    )  # fmt: skip
    update_fundamentals(db, yahoo, max_age_days=30)
    # Yahoo skips companies with SEC data (GOOGL, TEVA) and dual listings (TEVA.TA).
    assert sorted(yahoo.calls) == ["GOOG", "LUMI.TA"]

    lumi = db.get(Security, _sec_id(db, "LUMI"))
    assert lumi is not None
    assert lumi.country_code == "IL"
    assert lumi.industry is not None and lumi.industry.name == "Banks - Regional"
    assert lumi.industry.sector.name == "Financial Services"

    # Profiles: only securities without a fresh profile are fetched.
    yahoo.calls.clear()
    update_profiles(db, yahoo, max_age_days=90)
    assert "LUMI.TA" not in yahoo.calls
    assert "TEVA" in yahoo.calls


def test_yahoo_fills_in_for_sec_filers_without_data(db: Session) -> None:
    _universe(db)
    map_sec_ciks(db, {"GOOGL": (1652044, "Nasdaq"), "TEVA": (818686, "NYSE")})
    # SEC returns nothing for Teva (e.g. a filer without XBRL data).
    sec = FakeFundamentals(
        name="sec", data={"1652044": (None, [fact("revenue", "2025-12-31", 1.0)])}
    )
    update_fundamentals(db, sec, max_age_days=7)
    yahoo = FakeFundamentals()
    update_fundamentals(db, yahoo, max_age_days=30)
    assert "TEVA" in yahoo.calls
    assert "GOOGL" not in yahoo.calls


def test_facts_owner_for_dual_listing_and_share_class(db: Session) -> None:
    _universe(db)
    store_facts(db, _sec_id(db, "GOOGL"), "sec", [fact("revenue", "2025-12-31", 1.0)])
    teva_us = db.execute(
        select(Security).where(Security.symbol == "TEVA", Security.currency_code == "USD")
    ).scalar_one()
    store_facts(db, teva_us.id, "sec", [fact("revenue", "2025-12-31", 2.0)])

    teva_ta = db.execute(
        select(Security).where(Security.symbol == "TEVA", Security.currency_code == "ILS")
    ).scalar_one()
    goog = db.get(Security, _sec_id(db, "GOOG"))
    assert goog is not None
    assert facts_owner(db, teva_ta) == teva_us.id
    assert facts_owner(db, goog) == _sec_id(db, "GOOGL")


def test_fundamentals_api(client: TestClient, db: Session) -> None:
    _universe(db)
    teva_us = db.execute(
        select(Security).where(Security.symbol == "TEVA", Security.currency_code == "USD")
    ).scalar_one()
    store_facts(
        db,
        teva_us.id,
        "sec",
        [
            fact("revenue", "2024-12-31", 16.5e9),
            fact("revenue", "2025-12-31", 16.0e9),
            fact("revenue", "2025-12-31", 16.2e9, known="2027-01-01"),  # restatement wins
            fact("net_income", "2025-12-31", -0.5e9),
            fact("revenue", "2025-09-30", 4.1e9, period_type="Q"),
        ],
    )
    teva_ta = db.execute(
        select(Security.id).where(Security.symbol == "TEVA", Security.currency_code == "ILS")
    ).scalar_one()

    body = client.get(f"/api/securities/{teva_ta}/fundamentals").json()
    assert body["owner_security_id"] == teva_us.id
    assert body["source"] == "sec"
    assert body["periods"] == ["2025-12-31", "2024-12-31"]
    rows = {m["code"]: m for m in body["metrics"]}
    assert rows["revenue"]["values"] == [16.2e9, 16.5e9]
    assert rows["revenue"]["unit"] == "USD"
    assert rows["net_income"]["values"] == [-0.5e9, None]

    quarterly = client.get(f"/api/securities/{teva_ta}/fundamentals?period_type=Q").json()
    assert quarterly["periods"] == ["2025-09-30"]
    assert client.get(f"/api/securities/{teva_ta}/fundamentals?period_type=X").status_code == 422
    nothing = client.get(f"/api/securities/{_sec_id(db, 'LUMI')}/fundamentals").json()
    assert nothing["metrics"] == []


@pytest.mark.parametrize("symbol", ["GOOG"])
def test_security_detail_includes_profile(client: TestClient, db: Session, symbol: str) -> None:
    _universe(db)
    detail = client.get(f"/api/securities/{_sec_id(db, symbol)}").json()
    assert "industry" in detail and "country_code" in detail
