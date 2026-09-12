.PHONY: up down backend-install backend-test backend-lint frontend-install frontend-test frontend-lint test lint

up:            ## Start the full stack
	docker compose up --build

down:
	docker compose down

backend-install:
	cd backend && uv sync --all-extras

backend-test:
	cd backend && uv run pytest

backend-lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy marginalia

frontend-install:
	cd frontend && npm ci

frontend-test:
	cd frontend && npm test -- --run

frontend-lint:
	cd frontend && npm run lint && npm run typecheck

test: backend-test frontend-test
lint: backend-lint frontend-lint
