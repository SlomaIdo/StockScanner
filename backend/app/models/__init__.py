"""Import all models so they register on ``Base.metadata`` (used by Alembic)."""

from app.models.market_data import CorporateAction, CorporateActionType, DailyBar, FxRate
from app.models.reference import Currency, Exchange, Industry, Sector
from app.models.security import Security, SecurityIdentifier, SecurityType

__all__ = [
    "CorporateAction",
    "CorporateActionType",
    "Currency",
    "DailyBar",
    "Exchange",
    "FxRate",
    "Industry",
    "Sector",
    "Security",
    "SecurityIdentifier",
    "SecurityType",
]
