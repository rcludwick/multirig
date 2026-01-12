# Codebase Structure

## Main Application (`multirig/`)
```
multirig/
├── app.py              # FastAPI application entry point
├── routes.py           # API route handlers
├── router.py           # URL router configuration
├── core.py             # Core application logic, RigManager
├── config.py           # Configuration models (RigConfig, etc.)
├── profiles.py         # Profile management
├── service.py          # Background service/polling
├── serial_executor.py  # Serial port execution
├── debug_log.py        # Debug logging utilities
├── __main__.py         # CLI entry point
│
├── rig/                # Rig control package
│   ├── __init__.py     # Package exports
│   ├── client.py       # RigClient - main rig abstraction
│   ├── server.py       # TCP server for external apps
│   ├── backend.py      # Backend abstraction layer
│   ├── managed.py      # Managed rigctld process backend
│   ├── process.py      # Direct rigctl process backend
│   ├── tcp.py          # TCP client for rigctld connections
│   ├── common.py       # Shared utilities
│   └── protocols.py    # Hamlib protocol handling
│
├── hamlib/             # Hamlib utilities package
│   ├── __init__.py     # Package exports
│   ├── formatter.py    # Response formatting
│   ├── parser.py       # Command/response parsing
│   ├── protocol.py     # Protocol definitions
│   ├── responses.py    # Response types
│   ├── messages.py     # Message types
│   └── response_parser.py  # Response parsing logic
│
├── frontend/           # Vite/TypeScript frontend (WIP)
│   ├── src/            # TypeScript source
│   ├── public/         # Static assets
│   ├── vite.config.ts  # Vite configuration
│   ├── tsconfig.json   # TypeScript config
│   └── package.json    # npm dependencies
│
├── static/             # Current frontend assets
│   ├── app.js          # Main frontend JavaScript
│   ├── app.min.js      # Minified JS
│   ├── settings.js     # Settings page JavaScript
│   ├── settings.min.js # Minified settings JS
│   ├── style.css       # Main styles
│   ├── style.min.css   # Minified CSS
│   ├── index.html      # SPA entry point
│   ├── rig_models.json # Generated rig capabilities
│   ├── fonts/          # Web fonts
│   └── assets/         # Additional static assets
│
└── templates/          # Jinja2 templates
    └── index.html      # Main page template
```

## Tests
```
tests/
├── __init__.py
├── test_*.py           # Python unit tests (app, config, rig, etc.)
├── unit/               # Hamlib-specific unit tests
│   ├── test_hamlib_parser.py
│   └── test_hamlib_response_parser.py
└── e2e/
    ├── conftest.py     # E2E fixtures (test_env, profile_manager)
    ├── utils.py        # ProfileManager helper class
    └── test_*.py       # Playwright E2E tests

js-tests/               # Jest frontend tests
```

## External Dependencies
```
ext/
├── hamlib/             # Hamlib binaries/source
└── netmind/            # TCP proxy for debugging (separate uv project)
```

## Key Files
- `RigClient.safe_status` (rig/client.py) - Frontend data source
- `RigConfig` (config.py) - Persistent rig configuration model
- `loadRigModels()` (static/app.js) - Frontend model loading
- `test_env` fixture (tests/e2e/conftest.py) - E2E server startup
