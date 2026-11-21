# StockScanner

My personal stock scanner app and bot to guide me with investing. The sky is the limit here.

A platform to scan and browse stocks worldwide, and a workbench for ML and AI
tools that help understand the market. See [docs/ROADMAP.md](docs/ROADMAP.md)
for the plan and progress, and [docs/DATA_REPORT.md](docs/DATA_REPORT.md) for what is in the
database and how to use it.

## Layout

| Path | What |
|------|------|
| `backend/` | FastAPI API, data model (SQLAlchemy + Alembic), data pipeline |
| `web/` | Next.js web app (installable on phone as a PWA later) |
| `ml/` | Research workspace: notebooks, correlation/clustering studies, models |
| `docs/` | Roadmap and design notes |

## Run everything with Docker

```bash
docker compose up --build
```

- Web app: http://localhost:3000 (Stocks and Data pages)
- API docs: http://localhost:8000/docs
- Postgres + TimescaleDB: `localhost:5432` (user/password/db: `stockscanner`)

The backend applies migrations and loads reference data (currencies, exchanges,
sectors) on startup.

## Loading market data

The data pipeline uses free sources only (Yahoo Finance for now). Run the first load once;
after that the `scheduler` service keeps everything up to date every weekday evening.

```bash
docker compose exec backend stockscanner fx --years 10
```

```bash
docker compose exec backend stockscanner universe
```

```bash
docker compose exec backend stockscanner backfill --years 10
```

Then load fundamentals (financial statements) and company profiles. SEC asks automated
clients to identify themselves, so first set `SS_SEC_USER_AGENT="StockScanner your-name
you@example.com"` (in `.env` or your shell) and restart the containers.

```bash
docker compose exec backend stockscanner fundamentals --source sec
```

```bash
docker compose exec backend stockscanner fundamentals --source yahoo
```

```bash
docker compose exec backend stockscanner profiles
```

The first backfill of ~5,000 stocks takes roughly 20 minutes; SEC fundamentals about 30
minutes; Yahoo fundamentals and profiles a couple of hours. After that the nightly job keeps
everything current in batches. Other commands:

| Command | What it does |
|---------|--------------|
| `stockscanner universe -g IL` | Refresh the tracked stocks for one market group (US, IL, EU, ASIA) |
| `stockscanner update` | Fetch the latest prices for everything tracked |
| `stockscanner nightly` | FX + universe + update (what the scheduler runs) |
| `stockscanner quality` | Data-quality report |
| `stockscanner status` | Coverage per exchange and recent runs |
| `stockscanner report` | Regenerate [docs/DATA_REPORT.md](docs/DATA_REPORT.md): coverage, freshness, quality, usage guide |

The universe today: top 3,000 US stocks (> $100M), all of TASE, and the largest 1,500
European stocks (> $100M). Asia is configured but disabled; enable it in
`backend/app/pipeline/universe.py`.

## Local development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22, Postgres 16
(TimescaleDB optional locally; it is used automatically when installed).

Start just the database in Docker:

```bash
docker compose up db
```

Backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

Web:

```bash
cd web
npm install
npm run dev
```

## Checks

```bash
make lint
```

```bash
make test
```

Backend tests create, migrate and drop their own `stockscanner_test` database.
CI runs the same checks on every pull request.
