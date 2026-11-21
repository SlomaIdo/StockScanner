# StockScanner Roadmap

A personal platform to scan and browse stocks worldwide, and a workbench for
bringing ML and AI tools to market analysis.

Status legend: `[ ]` todo · `[~]` in progress · `[x]` done

## Guiding principles

1. **Data is the hard part.** ~60–70k listed equities across 80+ exchanges.
   Every data source sits behind one provider-adapter interface, so we can
   start free and swap in a paid global provider without a rewrite.
2. **End-of-day first, real-time later.** EOD prices + fundamentals cover
   scanning, screening and most ML work; global real-time is costly and
   licensed per exchange.
3. **Personal tool first.** Single user, no multi-tenant auth or billing.
4. **Backtest before believing.** No model output is trusted until it passes an
   honest backtest (no lookahead, no survivorship bias).

## Architecture

```
  Web app (PWA, Next.js + TradingView Lightweight Charts)
                     │ REST / WebSocket
  FastAPI backend: screener · symbols · alerts · AI assistant
        │                 │                    │
  Postgres+Timescale   Job runner           ML workspace
  (prices,             (ingest,             (features, models,
   fundamentals)        indicators, scans)   backtests, notebooks)
                          │
              Data provider adapters
       (yfinance / EODHD / FMP / news / macro)
```

## Open decisions

| # | Decision | Default until decided |
|---|----------|-----------------------|
| 1 | Data budget: free vs paid global provider | Start free (yfinance), adapter-based |
| 2 | App form: PWA vs native mobile | PWA |
| 3 | Hosting: local vs cloud | Local (docker-compose) first |
| 4 | First markets | US, Israel (TASE), Europe |
| 5 | Investing style focus | Mixed: fundamentals + swing technicals |

## Phase 0: Foundation

- [ ] Monorepo layout: `backend/`, `web/`, `ml/`, `docs/`
- [ ] `docker-compose` with Postgres + TimescaleDB
- [ ] FastAPI skeleton with health endpoint, config, logging
- [ ] Next.js skeleton
- [ ] CI: lint (ruff, eslint), type-check, tests
- [ ] Core data model: exchanges, securities (ISIN/FIGI mapping), daily bars,
      corporate actions, currencies

## Phase 1: Data pipeline

- [ ] Provider adapter interface
- [ ] First adapter (free source)
- [ ] Global symbol universe loader
- [ ] Historical price backfill
- [ ] Nightly incremental updates per exchange, in local market timezone
- [ ] Split/dividend adjustment
- [ ] Currency normalization (local + USD)
- [ ] Data-quality checks and ingest monitoring

## Phase 2: Scanner & browser (MVP)

- [ ] Technical indicators engine (RSI, MAs, ATR, breakouts, volume spikes)
- [ ] Fundamentals ingest (P/E, growth, margins, debt)
- [ ] Screener API with composable filters
- [ ] Screener UI with saved scans
- [ ] Stock detail page: chart, key stats, fundamentals, peers
- [ ] Watchlists
- [ ] Alerts (email / Telegram) when saved scans get new matches

## Phase 3: ML platform

- [ ] Feature store built on prices and fundamentals
- [ ] Backtesting engine
- [ ] Experiment tracking (MLflow)
- [ ] Anomaly / unusual-volume detection
- [ ] Market regime classification
- [ ] Return / volatility forecasting
- [ ] Similar-stock clustering (embeddings)
- [ ] Expose model outputs as screener columns

## Phase 4: AI layer

- [ ] LLM assistant using the platform APIs as tools (natural-language scans,
      company summaries)
- [ ] News and filings ingestion
- [ ] Sentiment scoring
- [ ] Daily watchlist brief

## Phase 5: Deploy & polish

- [ ] Deploy to a cloud host (Fly.io / Hetzner / Railway)
- [ ] PWA install on phone
- [ ] Backups, monitoring, cost tracking
- [ ] Optional: native mobile app
