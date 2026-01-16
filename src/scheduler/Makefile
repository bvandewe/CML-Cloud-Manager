.PHONY: help install run test lint format clean

# Default target
.DEFAULT_GOAL := help

# ==============================================================================
# VARIABLES
# ==============================================================================

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Application settings
SERVICE_NAME := scheduler

# ==============================================================================
# HELP
# ==============================================================================

##@ General

help: ## Display this help message
	@echo "$(BLUE)Scheduler Service - Development Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

# ==============================================================================
# INSTALLATION
# ==============================================================================

##@ Installation

install: ## Install Python dependencies with Poetry
	@echo "$(BLUE)Installing Python dependencies...$(NC)"
	poetry install
	@echo "$(GREEN)Dependencies installed!$(NC)"

# ==============================================================================
# DEVELOPMENT
# ==============================================================================

##@ Development

run: ## Run the scheduler service locally
	@echo "$(BLUE)Starting Scheduler Service...$(NC)"
	PYTHONPATH=. poetry run python main.py

# ==============================================================================
# TESTING
# ==============================================================================

##@ Testing

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	PYTHONPATH=. poetry run pytest tests/ -v

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	PYTHONPATH=. poetry run pytest tests/ -v -m unit

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	PYTHONPATH=. poetry run pytest tests/ -v --cov=. --cov-report=html --cov-report=term

# ==============================================================================
# CODE QUALITY
# ==============================================================================

##@ Code Quality

lint: ## Run linting with Ruff
	@echo "$(BLUE)Running linting...$(NC)"
	poetry run ruff check .

format: ## Format code with Black and isort
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black .
	poetry run ruff check . --fix

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checking...$(NC)"
	poetry run mypy .

# ==============================================================================
# CLEANUP
# ==============================================================================

##@ Cleanup

clean: ## Clean build artifacts and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	rm -rf __pycache__ .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(NC)"
