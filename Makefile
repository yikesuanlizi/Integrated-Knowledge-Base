.PHONY: help install dev up down logs test lint clean format import smoke

help:
	@echo "Agentic Knowledge OS - Make targets"
	@echo "  install   Install Python dependencies"
	@echo "  dev       Start FastAPI dev server"
	@echo "  up        Start infrastructure (Milvus/ES/Postgres/MinIO)"
	@echo "  down      Stop infrastructure"
	@echo "  logs      Tail infrastructure logs"
	@echo "  test      Run smoke tests"
	@echo "  smoke     Run end-to-end smoke test"
	@echo "  clean     Clean caches and outputs"

install:
	pip install -e .

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f --tail=200

clean:
	rm -rf wiki_output/ build/ dist/ .pytest_cache/ __pycache__/ */__pycache__/ */*/__pycache__/
	find . -name "*.pyc" -delete

smoke:
	python scripts/smoke_test.py

import:
	@echo "Usage: curl -X POST http://localhost:8000/api/ingest/path -H 'Content-Type: application/json' -d '{\"path\": \"./samples\"}'"
