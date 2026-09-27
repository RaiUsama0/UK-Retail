.PHONY: setup lint test db-up db-down db-logs

setup:
	pip install -e ".[dev,dashboard]"

lint:
	ruff check src tests dashboards/streamlit

test:
	pytest

db-up:
	docker compose up -d
	docker compose ps

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres
