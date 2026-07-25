.PHONY: all format format-check lint typecheck test tests integration_tests help run dev \
	platform-api platform-webhook platform-harness platform-deps platform-migrate \
	platform-up platform-down platform-build platform-logs platform-ps

# Default target executed when no arguments are given to make.
all: help

######################
# DEVELOPMENT
######################

dev:
	uv run langgraph dev

run:
	uv run uvicorn agent.webapp:app --reload --port 8000

# Multi-service platform (see docs/PLATFORM.md)
# Prefer Compose v2 plugin; fall back to docker-compose binary.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
COMPOSE_CMD := $(COMPOSE) -f deploy/docker-compose.yml --env-file deploy/.env

platform-deps:
	@test -f deploy/.env || cp deploy/.env.example deploy/.env
	$(COMPOSE_CMD) up -d postgres nats

platform-migrate:
	$(COMPOSE_CMD) run --rm migrate

# Full stack in Docker (api + webhook + harness + postgres + nats). No KEDA.
platform-build:
	@test -f deploy/.env || cp deploy/.env.example deploy/.env
	$(COMPOSE_CMD) build

platform-up:
	@test -f deploy/.env || cp deploy/.env.example deploy/.env
	$(COMPOSE_CMD) up --build -d
	@echo ""
	@echo "API     http://localhost:$${API_HOST_PORT:-8080}"
	@echo "UI      http://localhost:$${UI_HOST_PORT:-3000}/platform"
	@echo "Webhook http://localhost:$${WEBHOOK_HOST_PORT:-8081}"
	@echo "NATS    nats://localhost:$${NATS_HOST_PORT:-4222}  (monitor :$${NATS_MONITOR_HOST_PORT:-8222})"
	@echo "Harness is a separate worker container consuming JetStream TASKS."
	@echo "Scale workers: $(COMPOSE_CMD) up -d --scale harness=3"

platform-down:
	$(COMPOSE_CMD) down

platform-logs:
	$(COMPOSE_CMD) logs -f api webhook harness ui

platform-ps:
	$(COMPOSE_CMD) ps

# Host processes (use platform-deps for postgres/nats first)
platform-api:
	uv run uvicorn openswe_platform.api.app:app --reload --port 8080

platform-webhook:
	uv run uvicorn openswe_platform.webhook.app:app --reload --port 8081

platform-harness:
	uv run python -m openswe_platform.harness.worker

install:
	uv sync --extra dev

######################
# TESTING
######################

TEST_FILE ?= tests/

test tests:
	@if [ -d "$(TEST_FILE)" ] || [ -f "$(TEST_FILE)" ]; then \
		uv run pytest -vvv $(TEST_FILE); \
	else \
		echo "Skipping tests: path not found: $(TEST_FILE)"; \
	fi

integration_tests:
	@if [ -d "tests/integration_tests/" ] || [ -f "tests/integration_tests/" ]; then \
		uv run pytest -vvv tests/integration_tests/; \
	else \
		echo "Skipping integration tests: path not found: tests/integration_tests/"; \
	fi

######################
# LINTING AND FORMATTING
######################

PYTHON_FILES=.

lint:
	uv run ruff check $(PYTHON_FILES)
	uv run ruff format $(PYTHON_FILES) --diff

format:
	uv run ruff format $(PYTHON_FILES)
	uv run ruff check --fix $(PYTHON_FILES)

format-check:
	uv run ruff format $(PYTHON_FILES) --check

typecheck:
	npx --yes basedpyright agent openswe_platform tests

######################
# HELP
######################

help:
	@echo '----'
	@echo 'dev                          - run LangGraph dev server (legacy monolith)'
	@echo 'run                          - run legacy FastAPI only'
	@echo 'platform-deps                - start postgres + nats only'
	@echo 'platform-build               - build api/webhook/harness images'
	@echo 'platform-up                  - build+run full stack (no KEDA)'
	@echo 'platform-down                - stop compose stack'
	@echo 'platform-logs / platform-ps  - logs / status'
	@echo 'platform-api                 - host API on :8080 (needs platform-deps)'
	@echo 'platform-webhook             - host webhooks on :8081'
	@echo 'platform-harness             - host harness worker (picks up NATS jobs)'
	@echo 'install                      - install dependencies (incl. dev extras)'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo 'typecheck                    - run basedpyright on agent/ openswe_platform/ tests/'
	@echo 'test                         - run unit tests'
	@echo 'integration_tests            - run integration tests'
	@echo '----'
