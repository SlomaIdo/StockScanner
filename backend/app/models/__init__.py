"""Import all models so they register on ``Base.metadata`` (used by Alembic)."""

from app.models.fundamentals import FinancialFact
from app.models.ingest import IngestRun, IngestStatus
from app.models.market_data import (
    CorporateAction,
    CorporateActionType,
    DailyBar,
    FxRate,
    QuoteSnapshot,
)
from app.models.reference import Currency, Exchange, Industry, Sector
from app.models.security import Security, SecurityIdentifier, SecurityType

__all__ = [
    "CorporateAction",
    "CorporateActionType",
    "Currency",
    "DailyBar",
    "Exchange",
    "FinancialFact",
    "FxRate",
    "Industry",
    "IngestRun",
    "IngestStatus",
    "QuoteSnapshot",
    "Sector",
    "Security",
    "SecurityIdentifier",
    "SecurityType",
]
