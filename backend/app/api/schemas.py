import datetime as dt

from pydantic import BaseModel, ConfigDict


class ExchangeOut(BaseModel):
    mic: str
    name: str
    country_code: str
    timezone: str
    currency_code: str
    securities: int
    last_bar_date: dt.date | None


class SectorOut(BaseModel):
    id: int
    name: str
    securities: int


class SecurityOut(BaseModel):
    id: int
    symbol: str
    name: str
    exchange_mic: str
    currency_code: str
    sector: str | None
    price: float | None
    market_cap_usd: float | None
    snapshot_date: dt.date | None
    primary_security_id: int | None


class SecurityPage(BaseModel):
    total: int
    items: list[SecurityOut]


class IdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    external_symbol: str
    price_divisor: int


class SecurityDetail(SecurityOut):
    country_code: str | None
    industry: str | None
    isin: str | None
    listed_on: dt.date | None
    last_seen_on: dt.date | None
    is_active: bool
    identifiers: list[IdentifierOut]
    first_bar_date: dt.date | None
    last_bar_date: dt.date | None
    bar_count: int


class BarOut(BaseModel):
    date: dt.date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float | None
    volume: int | None


class IngestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job: str
    scope: str | None
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    items_ok: int
    items_failed: int
    message: str | None


class QualityCheckOut(BaseModel):
    name: str
    description: str
    count: int
    samples: list[str]


class QualityReportOut(BaseModel):
    generated_at: dt.datetime
    issues: int
    checks: list[QualityCheckOut]


class MetricRow(BaseModel):
    code: str
    label: str
    statement: str
    unit: str | None
    values: list[float | None]


class FundamentalsOut(BaseModel):
    security_id: int
    owner_security_id: int | None
    source: str | None
    period_type: str
    periods: list[dt.date]
    metrics: list[MetricRow]
