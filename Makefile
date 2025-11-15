.PHONY: help build-ui dev-ui run test lint format clean install-dev-tools update-neuroglia-config restart-service

# Default target
.DEFAULT_GOAL := help

# ==============================================================================
# VARIABLES
# ==============================================================================

# Load environment variables from .env file
ifneq (,$(wildcard ./.env))
    include .env
    export
endif

# Docker settings
COMPOSE_FILE := docker-compose.yml
COMPOSE := docker-compose -f $(COMPOSE_FILE)

# Port settings with defaults (can be overridden in .env)
APP_PORT ?= 8020
KEYCLOAK_PORT ?= 8021
MONGODB_PORT ?= 8022
MONGO_EXPRESS_PORT ?= 8023
EVENT_PLAYER_PORT ?= 8025
OTEL_COLLECTOR_PORT_GRPC ?= 4317
OTEL_COLLECTOR_PORT_HTTP ?= 4318

# Application settings
APP_SERVICE_NAME := app
APP_URL := http://localhost:$(APP_PORT)
API_DOCS_URL := $(APP_URL)/api/docs

# Infrastructure settings
MONGO_URL := mongodb://localhost:$(MONGODB_PORT)
MONGO_EXPRESS_URL := http://localhost:$(MONGO_EXPRESS_PORT)
KEYCLOAK_URL := http://localhost:$(KEYCLOAK_PORT)
EVENT_PLAYER_URL := http://localhost:$(EVENT_PLAYER_PORT)

# Observability settings
OTEL_GRPC_URL := localhost:$(OTEL_COLLECTOR_PORT_GRPC)
OTEL_HTTP_URL := localhost:$(OTEL_COLLECTOR_PORT_HTTP)

# Documentation settings
DOCS_SITE_NAME ?= "Starter App"
DOCS_SITE_URL ?= "https://bvandewe.github.io/starter-app"
DOCS_FOLDER ?= ./docs
DOCS_DEV_PORT ?= 8000

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# ==============================================================================
# HELP
# ==============================================================================

##@ General

help: ## Display this help message
	@echo "$(BLUE)Starter App - Development Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# ==============================================================================
# DOCKER COMMANDS
# ==============================================================================

##@ Docker

build: ## Build Docker images for all services
	@echo "$(BLUE)Building Docker images...$(NC)"
	$(COMPOSE) build

up: ## Start services in the background
	@echo "$(BLUE)Starting Docker services...$(NC)"
	$(COMPOSE) up -d
	@echo "$(GREEN)Services started!$(NC)"
	@$(MAKE) urls

down: ## Stop and remove services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(COMPOSE) down
	@echo "$(GREEN)Services stopped!$(NC)"

start: ## Start existing containers
	@echo "$(BLUE)Starting Docker containers...$(NC)"
	$(COMPOSE) start
	@echo "$(GREEN)Containers started!$(NC)"

stop: ## Stop running containers
	@echo "$(BLUE)Stopping Docker containers...$(NC)"
	$(COMPOSE) stop
	@echo "$(GREEN)Containers stopped!$(NC)"

restart: ## Restart all services
	@echo "$(BLUE)Restarting Docker services...$(NC)"
	$(COMPOSE) restart
	@echo "$(GREEN)Services restarted!$(NC)"

restart-service: ## Restart a single Docker service (usage: make restart-service SERVICE=service_name)
	@if [ -z "$(SERVICE)" ]; then \
		echo "$(RED)Please specify SERVICE=<service_name>$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Restarting Docker service '$(SERVICE)'...$(NC)"
	$(COMPOSE) up -d --force-recreate $(SERVICE)
	@echo "$(GREEN)Service '$(SERVICE)' restarted with refreshed environment variables.$(NC)"

dev: ## Build and start services with live logs
	@echo "$(BLUE)Starting development environment...$(NC)"
	$(COMPOSE) up --build

rebuild: ## Rebuild services from scratch without cache
	@echo "$(BLUE)Rebuilding services from scratch...$(NC)"
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --force-recreate
	@echo "$(GREEN)Rebuild complete!$(NC)"

logs: ## Show logs from all services
	$(COMPOSE) logs -f

logs-app: ## Show logs from the app service only
	$(COMPOSE) logs -f $(APP_SERVICE_NAME)

ps: ## Show running containers
	$(COMPOSE) ps

docker-clean: ## Stop services and remove all volumes (WARNING: removes all data)
	@echo "$(RED)WARNING: This will remove all containers, volumes, and data!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(COMPOSE) down -v; \
		echo "$(GREEN)Cleanup complete!$(NC)"; \
	else \
		echo "$(YELLOW)Cleanup cancelled.$(NC)"; \
	fi

urls: ## Display application and service URLs
	@echo ""
	@echo "$(YELLOW)Application URLs:$(NC)"
	@echo "  Main App:        $(APP_URL)"
	@echo "  API Docs:        $(API_DOCS_URL)"
	@echo ""
	@echo "$(YELLOW)Infrastructure:$(NC)"
	@echo "  MongoDB:         $(MONGO_URL)"
	@echo "  MongoDB Express: $(MONGO_EXPRESS_URL)"
	@echo "  Keycloak Admin:  $(KEYCLOAK_URL) (admin/admin)"
	@echo "  Event Player:    $(EVENT_PLAYER_URL)"
	@echo ""
	@echo "$(YELLOW)Observability:$(NC)"
	@echo "  OTEL gRPC:       $(OTEL_GRPC_URL)"
	@echo "  OTEL HTTP:       $(OTEL_HTTP_URL)"

# ==============================================================================
# LOCAL DEVELOPMENT
# ==============================================================================

##@ Local Development

install: ## Install Python dependencies with Poetry
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	poetry install
	@echo "$(GREEN)Python dependencies installed!$(NC)"

install-ui: ## Install Node.js dependencies for UI
	@echo "$(BLUE)Installing UI dependencies...$(NC)"
	cd ui && npm install
	@echo "$(GREEN)UI dependencies installed!$(NC)"

build-ui: ## Build frontend assets
	@echo "$(BLUE)Building frontend assets...$(NC)"
	cd ui && npm run build
	@echo "$(GREEN)Frontend assets built!$(NC)"

dev-ui: ## Start UI development server with hot-reload
	@echo "$(BLUE)Starting UI development server...$(NC)"
	cd ui && npm run dev

run: build-ui ## Run the application locally (requires build-ui first)
	@echo "$(BLUE)Starting Starter App application...$(NC)"
	@echo "$(GREEN)Access at: http://localhost:8000$(NC)"
	cd src && PYTHONPATH=. poetry run uvicorn main:create_app --factory --host 0.0.0.0 --port 8000 --reload

run-debug: build-ui ## Run with debug logging
	@echo "$(BLUE)Starting Starter App with debug logging...$(NC)"
	cd src && LOG_LEVEL=DEBUG PYTHONPATH=. poetry run uvicorn main:create_app --factory --host 0.0.0.0 --port 8000 --reload --log-level debug

##@ Testing & Quality

test: ## Run tests
	@echo "$(BLUE)Running tests...$(NC)"
	poetry run pytest

test-unit: ## Run unit tests
	@echo "$(BLUE)Running unit tests...$(NC)"
	poetry run pytest -m unit

test-domain: ## Run domain tests
	@echo "$(BLUE)Running domain tests...$(NC)"
	poetry run pytest tests/domain/ -v

test-command: ## Run command tests
	@echo "$(BLUE)Running command tests...$(NC)"
	poetry run pytest -m command

test-query: ## Run query tests
	@echo "$(BLUE)Running query tests...$(NC)"
	poetry run pytest -m query

test-application: ## Run application tests
	@echo "$(BLUE)Running application tests...$(NC)"
	poetry run pytest tests/application -v

test-cov: ## Run tests with coverage
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	poetry run pytest --cov=. --cov-report=html --cov-report=term

lint: ## Run linting checks
	@echo "$(BLUE)Running linting checks...$(NC)"
	poetry run ruff check .

format: ## Format code with black
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black .

install-hooks: ## Install pre-commit git hooks
	@echo "$(BLUE)Installing pre-commit git hooks...$(NC)"
	poetry run pre-commit install --install-hooks
	@echo "$(GREEN)Git hooks installed successfully.$(NC)"

##@ Cleanup

clean: ## Clean up generated files and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .coverage htmlcov/ 2>/dev/null || true
	rm -rf ui/.parcel-cache 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(NC)"

clean-all: clean docker-clean ## Clean everything including Docker volumes

##@ Documentation

docs-install: ## Install MkDocs and dependencies
	@echo "$(BLUE)Installing MkDocs dependencies...$(NC)"
	pip install mkdocs mkdocs-material mkdocs-mermaid2-plugin
	@echo "$(GREEN)MkDocs dependencies installed!$(NC)"

docs-update-config: ## Update mkdocs.yml from .env variables
	@echo "$(BLUE)Updating mkdocs.yml from environment variables...$(NC)"
	@python3 scripts/update-mkdocs-config.py

docs-serve: docs-update-config ## Serve documentation locally with live reload
	@echo "$(BLUE)Starting documentation server...$(NC)"
	@echo "$(GREEN)Access at: http://127.0.0.1:$(DOCS_DEV_PORT)$(NC)"
	@echo "$(YELLOW)Site: $(DOCS_SITE_NAME)$(NC)"
	mkdocs serve --dev-addr=127.0.0.1:$(DOCS_DEV_PORT)

docs-build: docs-update-config ## Build documentation site
	@echo "$(BLUE)Building documentation...$(NC)"
	@echo "$(YELLOW)Site: $(DOCS_SITE_NAME)$(NC)"
	@echo "$(YELLOW)URL: $(DOCS_SITE_URL)$(NC)"
	mkdocs build --site-dir site
	@echo "$(GREEN)Documentation built in site/ directory$(NC)"

docs-deploy: docs-update-config ## Deploy documentation to GitHub Pages
	@echo "$(BLUE)Deploying documentation to GitHub Pages...$(NC)"
	@echo "$(YELLOW)Site: $(DOCS_SITE_NAME)$(NC)"
	@echo "$(YELLOW)URL: $(DOCS_SITE_URL)$(NC)"
	mkdocs gh-deploy --force
	@echo "$(GREEN)Documentation deployed!$(NC)"

docs-clean: ## Clean documentation build artifacts
	@echo "$(BLUE)Cleaning documentation build...$(NC)"
	rm -rf site/
	@echo "$(GREEN)Documentation build cleaned!$(NC)"

docs-config: ## Show current documentation configuration
	@echo "$(BLUE)Documentation Configuration:$(NC)"
	@echo "  $(YELLOW)Site Name:$(NC) $(DOCS_SITE_NAME)"
	@echo "  $(YELLOW)Site URL:$(NC)  $(DOCS_SITE_URL)"
	@echo "  $(YELLOW)Docs Folder:$(NC) $(DOCS_FOLDER)"
	@echo "  $(YELLOW)Dev Port:$(NC)   $(DOCS_DEV_PORT)"

##@ Environment Setup

setup: install install-ui build-ui install-hooks ## Complete setup for new developers
	@echo "$(GREEN)✅ Setup complete!$(NC)"
	@echo ""
	@echo "$(YELLOW)Quick Start:$(NC)"
	@echo "  make run              - Run locally"
	@echo "  make docker-up        - Run with Docker"
	@echo "  make help             - Show all commands"

env-check: ## Check environment requirements
	@echo "$(BLUE)Checking environment...$(NC)"
	@command -v python3.11 >/dev/null 2>&1 || { echo "$(RED)❌ Python 3.11 not found$(NC)"; exit 1; }
	@command -v poetry >/dev/null 2>&1 || { echo "$(RED)❌ Poetry not found$(NC)"; exit 1; }
	@command -v node >/dev/null 2>&1 || { echo "$(RED)❌ Node.js not found$(NC)"; exit 1; }
	@command -v docker >/dev/null 2>&1 || { echo "$(RED)❌ Docker not found$(NC)"; exit 1; }
	@command -v docker-compose >/dev/null 2>&1 || { echo "$(RED)❌ Docker Compose not found$(NC)"; exit 1; }
	@echo "$(GREEN)✅ All requirements satisfied!$(NC)"

##@ Information

status: ## Show current status
	@echo "$(BLUE)System Status:$(NC)"
	@echo ""
	@echo "$(YELLOW)Python Environment:$(NC)"
	@poetry env info || echo "$(RED)Poetry environment not configured$(NC)"
	@echo ""
	@echo "$(YELLOW)Docker Services:$(NC)"
	@docker-compose ps 2>/dev/null || echo "$(RED)Docker services not running$(NC)"
	@echo ""
	@echo "$(YELLOW)Service URLs:$(NC)"
	@echo "  $(GREEN)Local Dev (make run):$(NC)"
	@echo "    App:           http://localhost:8000"
	@echo "    API Docs:      http://localhost:8000/api/docs"
	@echo ""
	@echo "  $(GREEN)Docker (make docker-up):$(NC)"
	@echo "    App:           http://localhost:8080"
	@echo "    API Docs:      http://localhost:8080/api/docs"
	@echo "    MongoDB:       mongodb://localhost:27017"
	@echo "    Mongo Express: http://localhost:8081"
	@echo "    Keycloak:      http://localhost:8090"
	@echo "    Event Player:  http://localhost:8085"

info: ## Show project information
	@echo "$(BLUE)Starter App - Project Information$(NC)"
	@echo ""
	@echo "$(YELLOW)Local Development URLs:$(NC)"
	@echo "  Main App:        http://localhost:8000"
	@echo "  API Docs:        http://localhost:8000/api/docs"
	@echo ""
	@echo "$(YELLOW)Docker Services URLs:$(NC)"
	@echo "  Main App:        http://localhost:8080"
	@echo "  API Docs:        http://localhost:8080/api/docs"
	@echo "  MongoDB Express: http://localhost:8081"
	@echo "  Keycloak Admin:  http://localhost:8090 (admin/admin)"
	@echo "  Event Player:    http://localhost:8085"
	@echo "  MongoDB:         mongodb://localhost:27017"
	@echo ""
	@echo "$(YELLOW)Test Users:$(NC)"
	@echo "  admin/admin123     (Admin - Full Access)"
	@echo "  manager/manager123 (Manager - Department Access)"
	@echo "  user/user123       (User - Assigned Tasks Only)"
	@echo ""
	@echo "$(YELLOW)Documentation:$(NC)"
	@echo "  README.md           - Setup and usage guide"
	@echo "  SETUP_COMPLETE.md   - Quick reference"
	@echo "  DOCKER_SERVICES.md  - Docker services overview"
