.PHONY: up down backend-dev web-dev migrate seed test lint

up:            ## Start db, backend and web in Docker
	docker compose up --build

down:
	docker compose down

backend-dev:   ## Run the API with auto-reload (needs a running Postgres)
	cd backend && uv run uvicorn app.main:app --reload

web-dev:       ## Run the web app in dev mode
	cd web && npm run dev

migrate:
	cd backend && uv run alembic upgrade head

seed:
	cd backend && uv run python -m app.seed

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
	cd web && npm run lint && npm run typecheck
