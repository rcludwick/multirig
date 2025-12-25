# MultiRig Makefile

# Configurable variables (can be overridden: make VAR=value)
UV            ?= uv
PYTHON        ?= python3
VENV_DIR      ?= .venv
# System rigctl (assumed to be in PATH or specify absolute path)
RIGCTL        ?= rigctl

# Derived
UV_PY         := $(VENV_DIR)/bin/python
VENV_ABS      := $(abspath $(VENV_DIR))
UV_PY_ABS     := $(abspath $(UV_PY))

.DEFAULT_GOAL := all

.PHONY: help all venv check-prereqs run generate-rig-list build-app-js minify-static test test-py test-js test-e2e install coverage coverage-py coverage-js clean

help:
	@echo "Targets:"
	@echo "  make all                       # Setup venv and generate rig list"
	@echo "  make venv                      # Create .venv using uv"
	@echo "  make install                   # Install dependencies"
	@echo "  make generate-rig-list         # Generate multirig/static/rig_models.json from system rigctl"
	@echo "  make run                       # Run the server (via run.sh)"
	@echo "  make minify-static             # Minify static assets (*.min.js, *.min.css)"
	@echo "  make test                      # Run all tests (python + js + e2e)"
	@echo "  make test-py                   # Run pytest unit tests"
	@echo "  make test-js                   # Run Jest unit tests for frontend JS"
	@echo "  make test-e2e                  # Run Playwright E2E tests"
	@echo "  make coverage                  # Run coverage for python + js"
	@echo "  make build-app-js              # Rebuild multirig/static/app.min.js"
	@echo "  make clean                     # Clean artifacts"

all: install generate-rig-list

# Verify common prerequisites
check-prereqs:
	@ok=1; \
	if ! command -v $(UV) >/dev/null 2>&1; then \
		echo "[Missing] uv not found. Install it: pip3 install --user uv (or curl -LsSf https://astral.sh/uv/install.sh | sh)"; \
		ok=0; \
	fi; \
	if ! command -v $(RIGCTL) >/dev/null 2>&1; then \
		echo "[Missing] rigctl not found in PATH."; \
		echo "          On macOS: brew install hamlib"; \
		echo "          On Linux: sudo apt install libhamlib-utils"; \
		ok=0; \
	fi; \
	if [ $$ok -eq 0 ]; then exit 1; fi; \
	echo "[OK] Prerequisites present"

# Create virtualenv managed by uv
venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		$(UV) venv "$(VENV_DIR)"; \
	fi

install: check-prereqs venv
	@echo "[Info] Installing dependencies"
	@"$(UV)" pip install --python "$(UV_PY)" -e .

# Generate rig models list from rigctl --list
generate-rig-list: install
	@echo "[Info] Generating rig models list from $(RIGCTL)"
	@$(PYTHON) scripts/generate_rig_list.py "$(RIGCTL)" "multirig/static/rig_models.json"

minify-static: install
	@echo "[Info] Minifying static assets"
	@"$(UV_PY)" scripts/minify.py

# Run the server
run: install minify-static
	@echo "[Info] Starting server via run.sh"
	@./run.sh

test: test-py test-js test-e2e

test-py: venv
	@echo "[Info] Installing dev dependencies"
	@"$(UV)" pip install --python "$(UV_PY)" -e ".[dev]"
	@echo "[Info] Running pytest"
	@PYTHONTRACEMALLOC=1 "$(UV_PY)" -m pytest -n auto --ignore=tests/e2e

coverage: coverage-py coverage-js

coverage-py: venv
	@echo "[Info] Installing dev dependencies"
	@"$(UV)" pip install --python "$(UV_PY)" -e ".[dev]"
	@echo "[Info] Running pytest with coverage"
	@PYTHONTRACEMALLOC=1 "$(UV_PY)" -m pytest --cov=multirig --cov-report=term-missing --cov-report=html --cov-report=xml --ignore=tests/e2e

test-js:
	@echo "[Info] Installing JS dependencies"
	@npm install
	@echo "[Info] Running Jest"
	@npm test

coverage-js:
	@echo "[Info] Installing JS dependencies"
	@npm install
	@echo "[Info] Running Jest with coverage"
	@npm test -- --coverage

build-app-js:
	@echo "[Info] Installing JS dependencies"
	@npm install
	@echo "[Info] Building multirig/static/app.min.js"
	@npx terser multirig/static/app.js -c -m --ecma 2020 -o multirig/static/app.min.js

test-e2e:
	@echo "[Info] Installing Playwright browsers"
	@npx playwright install --with-deps chromium
	@echo "[Info] Running Python Playwright E2E tests"
	@PYTHONTRACEMALLOC=1 "$(UV_PY)" -m pytest tests/e2e

clean:
	@echo "Cleaning artifacts"
	@rm -f "multirig/static/rig_models.json"
	@rm -rf coverage .coverage htmlcov
