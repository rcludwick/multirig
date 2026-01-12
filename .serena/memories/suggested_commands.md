# Suggested Commands

## Setup & Build
```bash
make all              # Full setup: install deps + generate rig list + build frontend
make install          # Install Python dependencies only
make venv             # Create virtualenv
```

## Running
```bash
make run              # Start server (builds frontend first)
./run.sh              # Direct server start (no rebuild)
```

## Frontend (React/Vite)
```bash
make frontend-install # Install frontend npm dependencies
make frontend-build   # Build React frontend (outputs to static/)
make frontend-dev     # Run frontend dev server with hot reload
```

## Testing
```bash
make test             # Run ALL tests (python + js + e2e)
make test-py          # Python unit tests only
make test-js          # Jest frontend tests only
make test-e2e         # Playwright E2E tests only
```

## Coverage
```bash
make coverage         # Full coverage report
make coverage-py      # Python coverage only
make coverage-js      # JS coverage only
```

## Static Assets
```bash
make minify-static    # Minify CSS/JS (legacy)
make build-app-js     # Rebuild app.min.js
make generate-rig-list # Regenerate rig_models.json from rigctl
```

## Utilities
```bash
make clean            # Remove build artifacts
make help             # Show all targets
```

## Direct pytest Commands
```bash
uv run pytest tests/                           # All Python tests
uv run pytest tests/e2e/                       # E2E tests only
uv run pytest tests/e2e/test_foo.py -v         # Single test file
uv run pytest tests/e2e/test_foo.py::test_bar  # Single test
uv run pytest --headed tests/e2e/              # E2E with visible browser
uv run pytest tests/unit/                      # Hamlib unit tests
```

## System Commands (macOS/Darwin)
- `rigctl` / `rigctld` - Hamlib rig control utilities
- `pkill rigctld` - Kill stale rigctld processes
- `lsof -i :8000` - Check what's using a port
