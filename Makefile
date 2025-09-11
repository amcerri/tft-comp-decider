# Makefile for tft-comp-decider (developer convenience)
# Usage: `make help`

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Virtualenv & tools
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
RUFF := $(VENV)/bin/ruff
BLACK := $(VENV)/bin/black
MYPY := $(VENV)/bin/mypy
PYTEST := $(VENV)/bin/pytest
STREAMLIT := $(VENV)/bin/streamlit

DATA_DIR ?= $(CURDIR)/data

APP := src/tft_decider/ui/app.py
PKG := tft_decider

.PHONY: help venv install format lint typecheck test check run freeze clean

help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "}; /^[a-zA-Z0-9_\/%-]+:.*## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

venv: ## Create a local virtual environment in .venv
	python3 -m venv $(VENV)
	@echo "✅ venv created at $(VENV)"

install: venv ## Install project with dev dependencies
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	@echo "✅ installed with dev extras"

format: ## Auto-format code (ruff --fix, black)
	$(RUFF) check . --fix
	$(BLACK) .

lint: ## Lint code (ruff) and verify formatting (black --check)
	$(RUFF) check .
	$(BLACK) --check .

typecheck: ## Static type checking (mypy)
	$(MYPY) src

test: ## Run tests with pytest
	$(PYTEST)

check: lint typecheck test ## Run lint, typecheck, and tests
	@echo "✅ all checks passed"

run: ## Run the Streamlit app
	@echo "ℹ️  Using data dir: $(DATA_DIR) (override with TFT_DATA_DIR or make DATA_DIR=...)"
	TFT_DATA_DIR="$(DATA_DIR)" "$(STREAMLIT)" run "$(APP)"

freeze: ## Export an environment lock file (requirements.txt)
	$(PIP) freeze > requirements.txt
	@echo "✅ requirements.txt updated"

clean: ## Remove caches and build artifacts
	rm -rf .ruff_cache .mypy_cache .pytest_cache htmlcov .coverage* build dist *.egg-info
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
	@echo "🧹 cleaned"