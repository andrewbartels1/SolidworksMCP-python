# SolidWorks MCP Server - Simplified Makefile

.PHONY: help install test test-context-budget test-full test-clean docs build run clean lint format

# Default target
.DEFAULT_GOAL := help

# Detect conda command
CONDA_CMD := $(shell command -v micromamba 2>/dev/null || command -v mamba 2>/dev/null || command -v conda 2>/dev/null || echo "")

# Colors
BLUE := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
NC := \033[0m

help: ## Show available commands
	@echo "$(BLUE)SolidWorks MCP Server$(NC)"
	@echo "==================="
	@echo ""
	@echo "$(GREEN)Core Commands:$(NC)"
	@echo "  $(YELLOW)install$(NC)     Install dependencies and setup environment"
	@echo "  $(YELLOW)test$(NC)        Run test suite with coverage"
	@echo "  $(YELLOW)test-context-budget$(NC)  Run smoke response-size guard test"
	@echo "  $(YELLOW)test-full$(NC)   Run full suite including real SolidWorks integration tests"
	@echo "  $(YELLOW)test-clean$(NC)  Remove generated integration test artifacts"
	@echo "  $(YELLOW)docs$(NC)        Serve documentation locally"
	@echo "  $(YELLOW)build$(NC)       Build package for distribution"
	@echo "  $(YELLOW)run$(NC)         Start the MCP server"
	@echo "  $(YELLOW)clean$(NC)       Clean build artifacts"
	@echo "  $(YELLOW)lint$(NC)        Run code linting"
	@echo "  $(YELLOW)format$(NC)      Format code"
	@echo ""

install: ## Install dependencies and setup environment
	@echo "$(BLUE)Installing SolidWorks MCP Server...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	zsh -i install.sh

test: ## Run test suite with coverage
	@echo "$(BLUE)Running tests...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	PY_KEY_VALUE_DISABLE_BEARTYPE=true $(CONDA_CMD) run -n solidworks_mcp python -m pytest tests/ \
		-m "not solidworks_only" \
		--cov=src/solidworks_mcp \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml \
		--durations=10 \
		-v

test-context-budget: ## Run smoke response-size guard test (CI-friendly)
	@echo "$(BLUE)Running smoke response-size guard test...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	PY_KEY_VALUE_DISABLE_BEARTYPE=true $(CONDA_CMD) run -n solidworks_mcp python -m pytest tests/test_all_endpoints_harness.py \
		-k "test_smoke_responses_within_context_budget" \
		--no-cov \
		-q

test-full: ## Run full suite including real SolidWorks integration tests (Windows + SolidWorks)
	@echo "$(BLUE)Running full test suite (including real SolidWorks integration)...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	PY_KEY_VALUE_DISABLE_BEARTYPE=true SOLIDWORKS_MCP_RUN_REAL_INTEGRATION=true $(CONDA_CMD) run -n solidworks_mcp python -m pytest tests/ \
		--cov=src/solidworks_mcp \
		--cov-report=term-missing \
		--cov-report=html:htmlcov \
		--cov-report=xml:coverage.xml \
		--durations=10 \
		-v
	@$(MAKE) test-clean

test-clean: ## Remove generated SolidWorks integration artifacts
	@echo "$(BLUE)Cleaning generated integration artifacts...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp python tests/scripts/cleanup_generated_integration_artifacts.py

docs: ## Serve documentation locally
	@echo "$(BLUE)Starting documentation server...$(NC)"
	@echo "$(YELLOW)Available at: http://localhost:8000$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp mkdocs serve --dev-addr=localhost:8000

build: ## Build package for distribution
	@echo "$(BLUE)Building package...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp python -m build

run: ## Start the MCP server
	@echo "$(BLUE)Starting MCP server...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp python -m solidworks_mcp.server

clean: ## Clean build artifacts
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf build/ dist/ *.egg-info/ src/*.egg-info/
	rm -rf htmlcov/ .coverage coverage.xml
	rm -rf .pytest_cache/ .mypy_cache/
	rm -rf site/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

lint: ## Run code linting
	@echo "$(BLUE)Running linting...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp ruff check src/ tests/

format: ## Format code
	@echo "$(BLUE)Formatting code...$(NC)"
	@if [ -z "$(CONDA_CMD)" ]; then \
		echo "$(RED)Error: No conda/mamba/micromamba found$(NC)"; \
		exit 1; \
	fi
	$(CONDA_CMD) run -n solidworks_mcp ruff format src/ tests/