# Makefile for Delta Exchange Trading Platform

.PHONY: help install install-dev setup lint format type-check test test-cov clean run-quickstart

help:
	@echo "Delta Exchange Trading Platform - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          Install production dependencies"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make setup            Complete setup (venv, deps, pre-commit)"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run all linters (flake8, bandit)"
	@echo "  make format           Format code (black, isort)"
	@echo "  make type-check       Run type checking (mypy)"
	@echo "  make pre-commit       Run pre-commit hooks on all files"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run tests"
	@echo "  make test-cov         Run tests with coverage report"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean            Clean build artifacts and cache"
	@echo "  make run-quickstart   Run quickstart example"

install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements.txt
	pip install pre-commit

setup:
	python3.9 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -r requirements.txt
	. venv/bin/activate && pre-commit install
	cp config/.env.example config/.env
	@echo ""
	@echo "✓ Setup complete!"
	@echo "  1. Edit config/.env with your API credentials"
	@echo "  2. Activate venv: source venv/bin/activate"
	@echo "  3. Run quickstart: make run-quickstart"

lint:
	@echo "Running flake8..."
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --max-line-length=100 --statistics
	@echo ""
	@echo "Running bandit..."
	bandit -r . -c pyproject.toml

format:
	@echo "Running black..."
	black . --line-length=100
	@echo ""
	@echo "Running isort..."
	isort . --profile=black --line-length=100

type-check:
	@echo "Running mypy..."
	mypy . --ignore-missing-imports

pre-commit:
	pre-commit run --all-files

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=. --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "Coverage report generated in htmlcov/index.html"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf build/ dist/ htmlcov/ .coverage

run-quickstart:
	python3.9 quickstart.py
