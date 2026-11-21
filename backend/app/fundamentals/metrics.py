"""The standard fundamentals schema: every source is mapped onto these metric codes.

Conventions:
- Flow metrics (income statement, cash flow) cover a period: FY (annual) or Q (quarter).
- Stock metrics (balance sheet) are measured at the period end.
- Outflows (capex, dividends, buybacks) are stored as positive numbers.
- Money values are in the company's reporting currency (see the fact's ``unit``), which can
  differ from the listing currency (Teva reports in USD, trades in ILS on TASE).
"""

from dataclasses import dataclass
from enum import StrEnum


class Statement(StrEnum):
    INCOME = "income"
    BALANCE = "balance"
    CASH_FLOW = "cash_flow"


class UnitKind(StrEnum):
    MONEY = "money"
    PER_SHARE = "per_share"
    SHARES = "shares"


@dataclass(frozen=True)
class Metric:
    code: str
    label: str
    statement: Statement
    unit: UnitKind = UnitKind.MONEY


METRICS: dict[str, Metric] = {
    m.code: m
    for m in [
        # Income statement
        Metric("revenue", "Revenue", Statement.INCOME),
        Metric("cost_of_revenue", "Cost of revenue", Statement.INCOME),
        Metric("gross_profit", "Gross profit", Statement.INCOME),
        Metric("rd_expense", "Research & development", Statement.INCOME),
        Metric("operating_income", "Operating income", Statement.INCOME),
        Metric("ebitda", "EBITDA", Statement.INCOME),
        Metric("interest_expense", "Interest expense", Statement.INCOME),
        Metric("income_tax", "Income tax", Statement.INCOME),
        Metric("net_income", "Net income", Statement.INCOME),
        Metric("eps_basic", "EPS (basic)", Statement.INCOME, UnitKind.PER_SHARE),
        Metric("eps_diluted", "EPS (diluted)", Statement.INCOME, UnitKind.PER_SHARE),
        Metric("shares_diluted", "Diluted weighted shares", Statement.INCOME, UnitKind.SHARES),
        # Balance sheet
        Metric("total_assets", "Total assets", Statement.BALANCE),
        Metric("current_assets", "Current assets", Statement.BALANCE),
        Metric("cash", "Cash & equivalents", Statement.BALANCE),
        Metric("total_liabilities", "Total liabilities", Statement.BALANCE),
        Metric("current_liabilities", "Current liabilities", Statement.BALANCE),
        Metric("long_term_debt", "Long-term debt", Statement.BALANCE),
        Metric("total_debt", "Total debt", Statement.BALANCE),
        Metric("total_equity", "Shareholders' equity", Statement.BALANCE),
        Metric("shares_outstanding", "Shares outstanding", Statement.BALANCE, UnitKind.SHARES),
        # Cash flow
        Metric("operating_cash_flow", "Operating cash flow", Statement.CASH_FLOW),
        Metric("capex", "Capital expenditure", Statement.CASH_FLOW),
        Metric("free_cash_flow", "Free cash flow", Statement.CASH_FLOW),
        Metric("dividends_paid", "Dividends paid", Statement.CASH_FLOW),
        Metric("buybacks", "Share buybacks", Statement.CASH_FLOW),
    ]
}

# Stored as positive numbers even when a source reports them negative.
OUTFLOW_METRICS = frozenset({"capex", "dividends_paid", "buybacks"})
