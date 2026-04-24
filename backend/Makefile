.PHONY: help install run test lint fmt clean

.DEFAULT_GOAL := help

# ----------------------------------------------------------------------------
# Load configuration from .env (falls back to .env.example if .env missing)
# ----------------------------------------------------------------------------
ENV_FILE := $(if $(wildcard .env),.env,.env.example)
include $(ENV_FILE)
export

# Map APP_ENV to pip extras
APP_ENV ?= dev
ifeq ($(APP_ENV),prod)
    PIP_EXTRAS := .
else ifeq ($(APP_ENV),full)
    PIP_EXTRAS := .[dev,redis,postgres]
else
    PIP_EXTRAS := .[dev]
endif

help:  ## Show this help
	@echo "Code Gen Agent — Makefile"
	@echo ""
	@echo "Active config: $(ENV_FILE)  (APP_ENV=$(APP_ENV))"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "To switch environment: edit APP_ENV in .env (dev | prod | full)"

install:  ## Install deps according to APP_ENV in .env
	@echo ">>> Installing for APP_ENV=$(APP_ENV) -> pip install -e \"$(PIP_EXTRAS)\""
	pip install -e "$(PIP_EXTRAS)"

run:  ## Start the FastAPI server
	@echo ">>> Starting server (APP_ENV=$(APP_ENV), backend=$(AGENT_STATE_BACKEND), host=$(AGENT_HOST):$(AGENT_PORT))"
	python -m code_gen_agent.server

test:  ## Run pytest
	pytest -v

lint:  ## Run ruff linter
	ruff check code_gen_agent tests

fmt:  ## Format code with ruff
	ruff format code_gen_agent tests

clean:  ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache *.egg-info dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
