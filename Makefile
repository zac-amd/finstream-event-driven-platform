# =============================================================================
# FinStream - Development Makefile
# =============================================================================

.PHONY: help up down logs clean build infra-up services-up test lint

help:
	@echo "FinStream Development Commands"
	@echo "=============================="
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make infra-up     - Start infrastructure only"
	@echo "  make services-up  - Start application services only"
	@echo "  make logs         - View logs"
	@echo "  make build        - Build all service images"
	@echo "  make clean        - Clean up volumes and images"
	@echo "  make test         - Run tests"
	@echo "  make lint         - Run linters"

# Start all services
up:
	@echo "Starting FinStream..."
	docker compose up -d

# Stop all services
down:
	@echo "Stopping FinStream..."
	docker compose down

# View logs
logs:
	docker compose logs -f

# Build all service images
build:
	docker compose build

# Start only infrastructure (Kafka, Redis, TimescaleDB, Observability)
infra-up:
	docker compose up -d redpanda redis timescaledb prometheus grafana jaeger loki promtail redpanda-console

# Start only application services
services-up:
	docker compose up -d market-simulator stream-processor alert-service api-gateway dashboard

# Clean up everything
clean:
	docker compose down -v --rmi local
	docker volume prune -f

# Run tests
test:
	pip install -e shared/python-lib
	pytest services/*/tests/ -v

# Lint code
lint:
	ruff check services/
	black --check services/

# Initialize Kafka topics
init-topics:
	docker exec finstream-redpanda rpk topic create market.quotes -p 10
	docker exec finstream-redpanda rpk topic create market.trades -p 10
	docker exec finstream-redpanda rpk topic create market.candles -p 10
	docker exec finstream-redpanda rpk topic create alerts -p 3

# Shell into a service
shell-%:
	docker compose exec $* /bin/sh

# Restart a specific service
restart-%:
	docker compose restart $*
