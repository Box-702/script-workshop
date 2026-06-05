.PHONY: help install dev dev-api dev-web test lint clean docker-up docker-down db-upgrade db-downgrade db-new db-history

PYTHON ?= python3
PIP ?= pip
PNPM ?= pnpm

help:
	@echo "Script Workshop — make targets"
	@echo "  install      install backend + frontend deps"
	@echo "  dev          run api + web together"
	@echo "  dev-api      run fastapi on :8000"
	@echo "  dev-web      run next.js on :3000"
	@echo "  test         run all tests"
	@echo "  lint         run linters"
	@echo "  clean        remove caches and build outputs"

install:
	cd apps/api && $(PYTHON) -m venv .venv && . .venv/bin/activate && $(PIP) install -U pip && $(PIP) install -e ".[dev]"
	$(PNPM) install

dev:
	@echo "Use two terminals:"
	@echo "  make dev-api"
	@echo "  make dev-web"
	@$(MAKE) -j2 dev-api dev-web

dev-api:
	cd apps/api && . .venv/bin/activate && uvicorn app.main:app --reload --host $${API_HOST:-127.0.0.1} --port $${API_PORT:-8000}

dev-web:
	cd apps/web && $(PNPM) dev

test:
	cd apps/api && . .venv/bin/activate && pytest
	$(PNPM) --dir apps/web typecheck

db-upgrade:
	cd apps/api && . .venv/bin/activate && alembic upgrade head

db-downgrade:
	cd apps/api && . .venv/bin/activate && alembic downgrade -1

db-new:
	@if [ -z "$(msg)" ]; then echo "usage: make db-new msg=\"describe change\""; exit 1; fi
	cd apps/api && . .venv/bin/activate && alembic revision --autogenerate -m "$(msg)"

db-history:
	cd apps/api && . .venv/bin/activate && alembic history --verbose

lint:
	cd apps/api && . .venv/bin/activate && ruff check .
	$(PNPM) --dir apps/web lint

clean:
	rm -rf apps/api/.venv apps/api/data apps/api/storage
	rm -rf apps/web/node_modules apps/web/.next apps/web/out
	rm -rf .pytest_cache .ruff_cache

docker-up:
	docker compose up --build

docker-down:
	docker compose down -v
