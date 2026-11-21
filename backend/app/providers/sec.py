"""SEC EDGAR adapter: official XBRL financial data for SEC filers (free, no key).

Covers US companies (10-K/10-Q, us-gaap taxonomy) and foreign companies listed in the US
(20-F/40-F, often the ifrs-full taxonomy). Every value carries its filing date, so history
is point-in-time.

SEC asks automated clients to identify themselves with a User-Agent that includes contact
details and to stay under 10 requests per second; set ``SS_SEC_USER_AGENT``.
"""

import datetime as dt
import logging
import re
import time
from collections import defaultdict
from typing import Any

import httpx

from app.fundamentals.metrics import METRICS, OUTFLOW_METRICS, UnitKind
from app.providers.base import Fact, Profile, ProviderError

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# Standard metric -> candidate XBRL concepts, in priority order. Companies switch concepts
# over time (e.g. Revenues -> RevenueFromContractWithCustomer... after ASC 606), so each
# period takes the highest-priority concept that reports it.
CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:SalesRevenueGoodsNet",
        "us-gaap:RevenuesNetOfInterestExpense",
        "ifrs-full:Revenue",
        "ifrs-full:RevenueFromContractsWithCustomers",
    ],
    "cost_of_revenue": [
        "us-gaap:CostOfRevenue",
        "us-gaap:CostOfGoodsAndServicesSold",
        "us-gaap:CostOfGoodsSold",
        "ifrs-full:CostOfSales",
    ],
    "gross_profit": ["us-gaap:GrossProfit", "ifrs-full:GrossProfit"],
    "rd_expense": [
        "us-gaap:ResearchAndDevelopmentExpense",
        "us-gaap:ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
        "ifrs-full:ResearchAndDevelopmentExpense",
    ],
    "operating_income": [
        "us-gaap:OperatingIncomeLoss",
        "ifrs-full:ProfitLossFromOperatingActivities",
    ],
    "interest_expense": [
        "us-gaap:InterestExpense",
        "us-gaap:InterestExpenseNonoperating",
        "ifrs-full:FinanceCosts",
    ],
    "income_tax": [
        "us-gaap:IncomeTaxExpenseBenefit",
        "ifrs-full:IncomeTaxExpenseContinuingOperations",
    ],
    "net_income": [
        "us-gaap:NetIncomeLoss",
        "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",
        "us-gaap:ProfitLoss",
        "ifrs-full:ProfitLossAttributableToOwnersOfParent",
        "ifrs-full:ProfitLoss",
    ],
    "eps_basic": ["us-gaap:EarningsPerShareBasic", "ifrs-full:BasicEarningsLossPerShare"],
    "eps_diluted": [
        "us-gaap:EarningsPerShareDiluted",
        "us-gaap:EarningsPerShareBasicAndDiluted",
        "ifrs-full:DilutedEarningsLossPerShare",
    ],
    "shares_diluted": [
        "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
        "ifrs-full:AdjustedWeightedAverageShares",
    ],
    "total_assets": ["us-gaap:Assets", "ifrs-full:Assets"],
    "current_assets": ["us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets"],
    "cash": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "us-gaap:Cash",
        "ifrs-full:CashAndCashEquivalents",
    ],
    "total_liabilities": ["us-gaap:Liabilities", "ifrs-full:Liabilities"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities"],
    "long_term_debt": [
        "us-gaap:LongTermDebt",
        "us-gaap:LongTermDebtNoncurrent",
        "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings",
    ],
    "total_equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "ifrs-full:EquityAttributableToOwnersOfParent",
        "ifrs-full:Equity",
    ],
    # Balance-sheet share count. (The cover-page dei:EntityCommonStockSharesOutstanding is
    # dated on the filing's cover date, not a period end, so it is not used.)
    "shares_outstanding": ["us-gaap:CommonStockSharesOutstanding"],
    "operating_cash_flow": [
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
        "us-gaap:NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
        "ifrs-full:CashFlowsFromUsedInOperatingActivities",
    ],
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap:PaymentsToAcquireProductiveAssets",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "ifrs-full:PurchaseOfPropertyPlantAndEquipment",
    ],
    "dividends_paid": [
        "us-gaap:PaymentsOfDividends",
        "us-gaap:PaymentsOfDividendsCommonStock",
        "ifrs-full:DividendsPaidClassifiedAsFinancingActivities",
        "ifrs-full:DividendsPaid",
    ],
    "buybacks": [
        "us-gaap:PaymentsForRepurchaseOfCommonStock",
        "ifrs-full:PaymentsToAcquireOrRedeemEntitysShares",
    ],
}

# Units a metric may be reported in; anything else (e.g. a custom "BillionsCubicFeet"
# unit on an EPS tag) is a tagging error and skipped.
_UNIT_PATTERNS = {
    UnitKind.MONEY: re.compile(r"^[A-Z]{3}$"),
    UnitKind.PER_SHARE: re.compile(r"^[A-Z]{3}/shares$"),
    UnitKind.SHARES: re.compile(r"^shares$"),
}


def valid_unit(metric: str, unit: str) -> bool:
    return bool(_UNIT_PATTERNS[METRICS[metric].unit].match(unit))


ANNUAL_DAYS = (340, 380)
QUARTER_DAYS = (80, 100)


def _date(value: str | None) -> dt.date | None:
    return dt.date.fromisoformat(value) if value else None


def _period_type(start: dt.date | None, end: dt.date, fp: str | None) -> str | None:
    """FY or Q for a fact, or None for other spans (e.g. 6- or 9-month year-to-date)."""
    if start is None:  # instant (balance sheet): follow the filing's fiscal period
        if fp == "FY":
            return "FY"
        return "Q" if fp in ("Q1", "Q2", "Q3", "Q4") else None
    days = (end - start).days
    if ANNUAL_DAYS[0] <= days <= ANNUAL_DAYS[1]:
        return "FY"
    if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
        return "Q"
    return None


def parse_companyfacts(payload: dict[str, Any]) -> list[Fact]:
    """Map a companyfacts payload onto standard metrics.

    For each (metric, period type, period end) the highest-priority concept wins. Within that
    concept every distinct value is kept with the date it was first filed, so restatements
    are preserved and the history is point-in-time.
    """
    facts_by_taxonomy: dict[str, Any] = payload.get("facts", {})
    out: list[Fact] = []
    for metric, concepts in CONCEPTS.items():
        # (period_type, end) -> (priority, list of raw facts)
        chosen: dict[tuple[str, dt.date], tuple[int, list[tuple[Fact, float]]]] = {}
        for priority, concept in enumerate(concepts):
            taxonomy, name = concept.split(":")
            units = facts_by_taxonomy.get(taxonomy, {}).get(name, {}).get("units", {})
            for unit, rows in units.items():
                if not valid_unit(metric, unit):
                    continue
                per_period: dict[tuple[str, dt.date], list[tuple[Fact, float]]] = defaultdict(list)
                for row in rows:
                    end = _date(row.get("end"))
                    filed = _date(row.get("filed"))
                    if end is None or filed is None or row.get("val") is None:
                        continue
                    start = _date(row.get("start"))
                    ptype = _period_type(start, end, row.get("fp"))
                    if ptype is None:
                        continue
                    value = float(row["val"])
                    if metric in OUTFLOW_METRICS:
                        value = abs(value)
                    fact = Fact(
                        metric=metric,
                        period_type=ptype,
                        period_end=end,
                        period_start=start,
                        value=value,
                        unit=unit,
                        known_since=filed,
                        fiscal_year=row.get("fy"),
                        fiscal_period=row.get("fp"),
                        form=row.get("form"),
                    )
                    per_period[(ptype, end)].append((fact, value))
                for key, items in per_period.items():
                    current = chosen.get(key)
                    if current is None or priority < current[0]:
                        chosen[key] = (priority, items)
        for items in (v[1] for v in chosen.values()):
            out.extend(_first_filings_of_each_value(items))
    return out + _derive_free_cash_flow(out)


def _first_filings_of_each_value(items: list[tuple[Fact, float]]) -> list[Fact]:
    """Keep a fact only when its value differs from the previously filed one."""
    kept: list[Fact] = []
    last: float | None = None
    for fact, value in sorted(items, key=lambda i: i[0].known_since):
        if last is None or abs(value - last) > 1e-9 * max(1.0, abs(last)):
            kept.append(fact)
            last = value
    return kept


def _derive_free_cash_flow(facts: list[Fact]) -> list[Fact]:
    """Free cash flow = operating cash flow - capex, using the latest-known values."""
    latest: dict[tuple[str, str, dt.date], Fact] = {}
    for f in facts:
        if f.metric in ("operating_cash_flow", "capex"):
            key = (f.metric, f.period_type, f.period_end)
            if key not in latest or f.known_since > latest[key].known_since:
                latest[key] = f
    derived: list[Fact] = []
    for (metric, ptype, end), ocf in latest.items():
        if metric != "operating_cash_flow":
            continue
        capex = latest.get(("capex", ptype, end))
        if capex is None or capex.unit != ocf.unit:
            continue
        derived.append(
            Fact(
                metric="free_cash_flow",
                period_type=ptype,
                period_end=end,
                period_start=ocf.period_start,
                value=ocf.value - capex.value,
                unit=ocf.unit,
                known_since=max(ocf.known_since, capex.known_since),
                fiscal_year=ocf.fiscal_year,
                fiscal_period=ocf.fiscal_period,
                form=ocf.form,
            )
        )
    return derived


class SecProvider:
    name = "sec"

    def __init__(self, user_agent: str, request_pause: float = 0.12) -> None:
        self.client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=60,
        )
        self.request_pause = request_pause

    def _get(self, url: str) -> Any:
        for attempt in range(4):
            try:
                response = self.client.get(url)
            except httpx.HTTPError as exc:
                if attempt == 3:
                    raise ProviderError(f"SEC request failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            finally:
                time.sleep(self.request_pause)
            if response.status_code == 404:
                return None
            if response.status_code in (429, 503) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            if response.status_code != 200:
                raise ProviderError(f"SEC {url} returned HTTP {response.status_code}")
            return response.json()
        raise ProviderError(f"SEC {url} kept failing")

    def ticker_map(self) -> dict[str, tuple[int, str]]:
        """Ticker (exchange style, e.g. ``BRK.B``) -> (CIK, SEC exchange name)."""
        payload = self._get(TICKERS_URL)
        if not payload:
            raise ProviderError("SEC ticker list is empty")
        fields = payload["fields"]
        out: dict[str, tuple[int, str]] = {}
        for row in payload["data"]:
            record = dict(zip(fields, row, strict=False))
            ticker = str(record["ticker"]).upper().replace("-", ".")
            out.setdefault(ticker, (int(record["cik"]), str(record.get("exchange") or "")))
        return out

    def fundamentals(self, external_symbol: str) -> tuple[Profile | None, list[Fact]]:
        payload = self._get(FACTS_URL.format(cik=int(external_symbol)))
        if not payload:
            return None, []
        return None, parse_companyfacts(payload)
