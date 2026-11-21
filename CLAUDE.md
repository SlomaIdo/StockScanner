# StockScanner: notes for Claude

- Plan and progress live in `docs/ROADMAP.md`; tick items off as they land.
- Backend: `backend/` (FastAPI, SQLAlchemy 2, Alembic, uv). Settings use the `SS_` env prefix.
  - Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app tests && uv run pytest -q`
  - Schema changes: edit models, then `uv run alembic revision --autogenerate`, review it,
    and make sure `uv run alembic check` is clean (CI enforces it).
  - Tests need a reachable Postgres; they build a fresh `<db>_test` database via migrations.
- Web: `web/` (Next.js 16, app router, Tailwind 4). Read `web/AGENTS.md` first: this Next.js
  version differs from older ones; consult `web/node_modules/next/dist/docs/`.
  - Checks: `npm run lint && npm run typecheck && npm run build`
- Data sources are free only (Yahoo, Stooq, EDGAR, ESEF, FRED). Every source goes behind a
  provider adapter. Never commit API keys.
