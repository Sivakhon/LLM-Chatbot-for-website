.DEFAULT_GOAL := help
VENV ?= .venv
PY := $(abspath $(VENV))/bin/python
DATA ?= ../data/raw/mc_jeans_products.json

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create venv and install backend + frontend (dev)
	python3 -m venv "$(VENV)"
	"$(PY)" -m pip install -U pip
	"$(PY)" -m pip install -e "backend[dev,scraper]" -r frontend/requirements.txt

lint: ## Ruff lint + format check, mypy
	cd backend && "$(PY)" -m ruff check . && "$(PY)" -m ruff format --check . && "$(PY)" -m mypy app
	cd frontend && "$(PY)" -m ruff check . && "$(PY)" -m ruff format --check .

format: ## Auto-format
	cd backend && "$(PY)" -m ruff check --fix . && "$(PY)" -m ruff format .
	cd frontend && "$(PY)" -m ruff check --fix . && "$(PY)" -m ruff format .

test: ## Run the test suite
	cd backend && "$(PY)" -m pytest

ingest: ## Index products into the local vector store
	cd backend && "$(PY)" -m app.ingest $(DATA) --reset

scrape: ## Re-scrape the catalog (needs: playwright install chromium)
	cd backend && "$(PY)" -m app.scraper --pages 3 --out ../data/processed/products.json

api: ## Run the API with hot reload on :8000
	cd backend && "$(PY)" -m uvicorn app.main:create_app --factory --reload --port 8000

ui: ## Run the Streamlit UI on :8501
	cd frontend && "$(PY)" -m streamlit run app.py

up: ## Start the full stack with Docker Compose
	docker compose up --build

down: ## Stop the stack
	docker compose down

.PHONY: help install lint format test ingest scrape api ui up down
