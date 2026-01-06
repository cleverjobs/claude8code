# ==============================================================================
# claude8code - Build, Test, and Deploy Commands
# ==============================================================================
# Development:
#   make install      - Install all dependencies (dev + observability)
#   make install-prod - Install production dependencies only
#   make run          - Run development server
#   make test         - Run all tests
#   make check        - Run pre-commit checks
#   make lint         - Run linting
#   make format       - Format code
#
# Docker:
#   make up           - Start with Docker Compose
#   make down         - Stop containers
#   make build        - Build Docker image
#   make push         - Push to Docker Hub
#
# Observability:
#   make up-observability - Start with Prometheus/Grafana
#
# Release:
#   make release VERSION=x.y.z - Create a new release
# ==============================================================================

.PHONY: install install-prod run test test-unit test-integration coverage check lint format \
        build push up down logs clean up-observability down-observability help release

DOCKER_HUB_USER := krisjobs
IMAGE := $(DOCKER_HUB_USER)/claude8code
VERSION ?= $(shell grep 'version = ' pyproject.toml | head -1 | cut -d'"' -f2)

# ------------------------------------------------------------------------------
# Development Setup
# ------------------------------------------------------------------------------

install:
	@echo "Installing all dependencies (dev + observability)..."
	uv sync --extra dev --extra observability
	@echo "Done! Run 'make run' to start the server."

install-prod:
	@echo "Installing production dependencies only..."
	uv sync --frozen
	@echo "Done!"

run:
	@echo "Starting development server..."
	uv run claude8code --reload --debug

# ------------------------------------------------------------------------------
# Testing
# ------------------------------------------------------------------------------

test: lint test-unit
	@echo "All tests passed!"

test-unit:
	@echo "Running unit tests..."
	USE_CLAUDE_MOCK=true uv run pytest tests/ -v

test-integration: build
	@echo "Running integration tests..."
	docker compose up -d
	@sleep 5
	@echo "Testing health endpoint..."
	@curl -sf http://localhost:8787/health && echo " OK" || (echo " FAILED"; docker compose down; exit 1)
	@echo "Testing models endpoint..."
	@curl -sf http://localhost:8787/v1/models && echo " OK" || (echo " FAILED"; docker compose down; exit 1)
	@echo "Testing metrics endpoint..."
	@curl -sf http://localhost:8787/metrics && echo " OK" || (echo " FAILED"; docker compose down; exit 1)
	@echo "All integration tests passed!"
	docker compose down

coverage:
	@echo "Running tests with coverage..."
	USE_CLAUDE_MOCK=true uv run pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing
	@echo "Coverage report generated in htmlcov/"

# ------------------------------------------------------------------------------
# Code Quality
# ------------------------------------------------------------------------------

check:
	@echo "Running all pre-commit checks..."
	uv run pre-commit run --all-files

lint:
	@echo "Running linter..."
	uv run ruff check src/ tests/
	@echo "Running type checker..."
	uv run mypy src/ tests/

format:
	@echo "Formatting code..."
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/

# ------------------------------------------------------------------------------
# Docker Operations
# ------------------------------------------------------------------------------

build:
	@echo "Building Docker image..."
	docker build -t $(IMAGE):latest -t $(IMAGE):$(VERSION) .

push: build
	@echo "Pushing to Docker Hub..."
	docker push $(IMAGE):latest
	docker push $(IMAGE):$(VERSION)
	@echo "Pushed $(IMAGE):latest and $(IMAGE):$(VERSION)"

up:
	@echo "Starting claude8code..."
	docker compose up -d

down:
	@echo "Stopping claude8code..."
	docker compose down

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi local
	docker compose -f docker-compose.observability.yml down -v --rmi local 2>/dev/null || true
	rm -rf htmlcov/ .coverage coverage.xml .pytest_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Cleaned up containers, volumes, images, and caches"

# ------------------------------------------------------------------------------
# Observability Stack
# ------------------------------------------------------------------------------

up-observability:
	@echo "Starting claude8code with Prometheus/Grafana..."
	docker compose -f docker-compose.observability.yml up -d
	@echo ""
	@echo "Services started:"
	@echo "  - claude8code: http://localhost:8787"
	@echo "  - Prometheus:  http://localhost:9090"
	@echo "  - Grafana:     http://localhost:3000 (admin/admin)"

down-observability:
	@echo "Stopping observability stack..."
	docker compose -f docker-compose.observability.yml down

# ------------------------------------------------------------------------------
# Release
# ------------------------------------------------------------------------------

release:
ifndef VERSION
	$(error VERSION is required. Usage: make release VERSION=x.y.z)
endif
	@echo "Creating release v$(VERSION)..."
	@echo "Updating version in pyproject.toml..."
	@sed -i '' 's/version = ".*"/version = "$(VERSION)"/' pyproject.toml
	@echo "Committing version bump..."
	git add pyproject.toml
	git commit -m "chore: bump version to $(VERSION)"
	@echo "Creating tag..."
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo ""
	@echo "Release v$(VERSION) created locally."
	@echo "To publish, run:"
	@echo "  git push origin main"
	@echo "  git push origin v$(VERSION)"

# ------------------------------------------------------------------------------
# Help
# ------------------------------------------------------------------------------

help:
	@echo "claude8code - Build, Test, and Deploy Commands"
	@echo ""
	@echo "Development:"
	@echo "  make install         - Install all dependencies (dev + observability)"
	@echo "  make install-prod    - Install production dependencies only"
	@echo "  make run             - Run development server with auto-reload"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Run linting and unit tests"
	@echo "  make test-unit       - Run unit tests only"
	@echo "  make test-integration - Run integration tests (requires Docker)"
	@echo "  make coverage        - Run tests with coverage report"
	@echo ""
	@echo "Code Quality:"
	@echo "  make check           - Run all pre-commit checks (ruff + mypy)"
	@echo "  make lint            - Run ruff and mypy"
	@echo "  make format          - Format code with ruff"
	@echo ""
	@echo "Docker:"
	@echo "  make build           - Build Docker image"
	@echo "  make push            - Build and push to Docker Hub"
	@echo "  make up              - Start with Docker Compose"
	@echo "  make down            - Stop containers"
	@echo "  make logs            - View container logs"
	@echo "  make clean           - Remove all containers, volumes, caches"
	@echo ""
	@echo "Observability:"
	@echo "  make up-observability   - Start with Prometheus/Grafana"
	@echo "  make down-observability - Stop observability stack"
	@echo ""
	@echo "Release:"
	@echo "  make release VERSION=x.y.z - Create a new release"
	@echo ""
	@echo "Current version: $(VERSION)"
