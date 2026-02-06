.PHONY: help install run test lint fmt typecheck migrate migrate-new migrate-down db-init clean check run-prod test-watch

help:
	@echo "Available targets:"
	@grep "^[a-z-]*:" Makefile | cut -d: -f1 | sed 's/^/  make /'

install:
	@echo "Installing dependencies..."
	uv sync
	@echo "✓ Dependencies installed"

run:
	@echo "Starting service on port 15010..."
	uv run uvicorn app.main:app --host 0.0.0.0 --port 15010 --reload --reload-dir app --reload-dir migrations

run-prod:
	@echo "Starting service (production)..."
	uv run uvicorn app.main:app --host 0.0.0.0 --port 15010

test:
	@echo "Running tests..."
	uv run pytest -v

test-watch:
	@echo "Running tests in watch mode..."
	uv run pytest --watch

lint:
	@echo "Linting..."
	uv run ruff check app tests

fmt:
	@echo "Formatting..."
	uv run black app tests
	uv run ruff check --fix app tests

typecheck:
	@echo "Type checking..."
	uv run mypy app

check: lint typecheck test
	@echo "✓ All checks passed"

migrate:
	@echo "Running database migrations..."
	uv run alembic upgrade head

migrate-new:
	@echo "Create new migration. Usage: make migrate-new MSG='description'"
	@if [ -z "$(MSG)" ]; then \
		echo "Error: Please provide MSG parameter"; \
		echo "Usage: make migrate-new MSG='Add users table'"; \
		exit 1; \
	fi
	uv run alembic revision --autogenerate -m "$(MSG)"

migrate-down:
	@echo "Rolling back one migration..."
	uv run alembic downgrade -1

db-init:
	@echo "Initializing database (running migrations)..."
	uv run alembic upgrade head

clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .mypy_cache .ruff_cache .pytest_cache
	@echo "✓ Cleaned"

.DEFAULT_GOAL := help
