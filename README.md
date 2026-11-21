# StockScanner

My personal stock scanner app and bot to guide me with investing. The sky is the limit here.

A platform to scan and browse stocks worldwide, and a workbench for ML and AI
tools that help understand the market. See [docs/ROADMAP.md](docs/ROADMAP.md)
for the plan and progress.

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

- Web app: http://localhost:3000
- API docs: http://localhost:8000/docs
- Postgres + TimescaleDB: `localhost:5432` (user/password/db: `stockscanner`)

The backend applies migrations and loads reference data (currencies, exchanges,
sectors) on startup.

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
