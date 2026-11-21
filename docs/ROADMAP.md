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
       (Yahoo / Stooq / EDGAR / ESEF / FRED / news)
```

## Open decisions

| # | Decision | Status |
|---|----------|--------|
| 1 | Data budget: free vs paid global provider | **Decided: free sources only** (adapter-based, paid can be added later) |
| 2 | App form: PWA vs native mobile | PWA |
| 3 | Hosting: local vs cloud | Local (docker-compose) first |
| 4 | First markets | US, Israel (TASE), Europe |
| 5 | Investing style focus | Mixed: fundamentals + swing technicals |

## Data sources (free)

| Need | Source | Notes |
|------|--------|-------|
| Daily prices, splits, dividends | Yahoo Finance (`yfinance`) | Most world exchanges; unofficial, rate-limited, personal use |
| Backup daily prices | Stooq | Cross-check Yahoo |
| US fundamentals | SEC EDGAR XBRL API | Quarterly/annual since ~2009, point-in-time via filing dates |
| EU fundamentals | filings.xbrl.org (ESEF) + Yahoo | Annual since ~2020–21 |
| Other fundamentals (incl. TASE) | Yahoo | ~4y annual, ~4–5 quarters; patchy for small caps |
| US fund holdings | SEC N-PORT | Quarterly full holdings |
| Symbol universe / IDs | Exchange directories, OpenFIGI | Built exchange by exchange |
| Sectors | Yahoo sector/industry, SEC SIC | Mapped to one internal taxonomy (GICS is proprietary) |
| Macro, FX | FRED, ECB | |
| News | RSS, GDELT | |

Known limits: no real-time, no delisted stocks (survivorship bias in
backtests), shallow non-US fundamental history. Mitigation: snapshot all
fetched data nightly so our own history accumulates.

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
- [ ] Fundamentals ingest: EDGAR (US), ESEF (EU), Yahoo (rest)
- [ ] Statement normalization into one standard schema
- [ ] Nightly fundamentals snapshots (build our own history)
- [ ] Unified sector/industry taxonomy (Yahoo + SIC mapping)
- [ ] Exchange calendars and FX rates

## Phase 2: Scanner & browser (MVP)

- [ ] Technical indicators engine (RSI, MAs, ATR, breakouts, volume spikes)
- [ ] Historical ratios computed from statements + prices (P/E, EV/EBITDA,
      ROE, ROIC, margins, growth, FCF yield, quality scores)
- [ ] Screener API with composable filters
- [ ] Screener UI with saved scans
- [ ] Stock detail page: chart, key stats, fundamentals, peers
- [ ] Watchlists
- [ ] Alerts (email / Telegram) when saved scans get new matches

## Phase 3: Global market structure (first analytics module)

- [ ] Return alignment across exchange calendars; local-currency and USD views
- [ ] Country × sector indices (market-cap weighted)
- [ ] Correlation matrices (stocks, sectors, countries) with heatmap UI
- [ ] Rolling correlations and crisis/regime comparison
- [ ] Time-zone handling: weekly returns and lagged correlations
- [ ] Clustering by return behaviour (hierarchical, with dendrogram);
      compare clusters to official sectors to find mislabelled stocks
- [ ] Correlation network (minimum spanning tree) visualization
- [ ] Lead-lag analysis across markets
- [ ] Factor decomposition: global / region / sector / idiosyncratic

## Phase 4: ML platform

- [ ] Feature store built on prices and fundamentals
- [ ] Backtesting engine
- [ ] Experiment tracking (MLflow)
- [ ] Anomaly / unusual-volume detection
- [ ] Market regime classification
- [ ] Return / volatility forecasting
- [ ] Similar-stock embeddings (returns + fundamentals), building on Phase 3
- [ ] Expose model outputs as screener columns

## Phase 5: AI layer

- [ ] LLM assistant using the platform APIs as tools (natural-language scans,
      company summaries)
- [ ] News and filings ingestion
- [ ] Extract financials from unstructured filings (e.g. TASE MAYA PDFs)
- [ ] Sentiment scoring
- [ ] Daily watchlist brief

## Phase 6: Deploy & polish

- [ ] Deploy to a cloud host (Fly.io / Hetzner / Railway)
- [ ] PWA install on phone
- [ ] Backups, monitoring, cost tracking
- [ ] Optional: native mobile app
