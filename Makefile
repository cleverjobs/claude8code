# ==============================================================================
# claude8code - Build and Deploy Commands
# ==============================================================================
# Local Development:
#   make up       - Start local dev server
#   make down     - Stop containers
#   make logs     - View container logs
#   make test     - Build and test health endpoint
#
# Docker Hub:
#   make build    - Build Docker image
#   make push     - Build and push to Docker Hub
# ==============================================================================

.PHONY: build push test up down logs clean help

DOCKER_HUB_USER := krisjobs
IMAGE := $(DOCKER_HUB_USER)/claude8code

# ------------------------------------------------------------------------------
# Docker Hub Operations
# ------------------------------------------------------------------------------

build:
	@echo "Building Docker image..."
	docker build -t $(IMAGE):latest .

push: build
	@echo "Pushing to Docker Hub..."
	docker push $(IMAGE):latest
	@echo "Pushed $(IMAGE):latest"

# ------------------------------------------------------------------------------
# Local Development
# ------------------------------------------------------------------------------

up:
	@echo "Starting claude8code..."
	docker compose up -d

down:
	@echo "Stopping claude8code..."
	docker compose down

logs:
	docker compose logs -f

test: build
	@echo "Running integration test..."
	docker compose up -d
	@sleep 5
	@echo "Testing health endpoint..."
	@curl -sf http://localhost:8787/health && echo " OK" || (echo " FAILED"; docker compose down; exit 1)
	@echo "Testing models endpoint..."
	@curl -sf http://localhost:8787/v1/models && echo " OK" || (echo " FAILED"; docker compose down; exit 1)
	@echo "All tests passed!"
	docker compose down

clean:
	docker compose down -v --rmi local
	@echo "Cleaned up containers, volumes, and local images"

# ------------------------------------------------------------------------------
# Help
# ------------------------------------------------------------------------------

help:
	@echo "claude8code - Build and Deploy Commands"
	@echo ""
	@echo "Local Development:"
	@echo "  make up     - Start local dev server"
	@echo "  make down   - Stop containers"
	@echo "  make logs   - View container logs"
	@echo "  make test   - Build and test health endpoint"
	@echo "  make clean  - Remove containers, volumes, images"
	@echo ""
	@echo "Docker Hub:"
	@echo "  make build  - Build Docker image"
	@echo "  make push   - Build and push to Docker Hub"
