# Project Description
This is the **MultiRig** project. It controls multiple hamlib rigs (via `rigctld` or direct serial `rigctl`). Components such as WSJT-X connect to MultiRig as if it were a standard rig, and MultiRig then manages and synchronizes multiple physical rigs.

## Architecture
- **Backend**: Python (FastAPI, Uvicorn).
    - The project uses `uv` for Python dependency management.
- **Frontend**: JavaScript (Vanilla JS, Jinja2 templates for initial rendering).
- **External Components**:
    - **Hamlib**: Submodule in `ext/hamlib` for rig control protocols.
    - **Netmind**: Located in `ext/netmind`. A TCP proxy and web interface used for debugging and validating network traffic during tests. It also acts as an MCP server.

## Codebase Structure
- `multirig/`: Main application source code.
    - `app.py`: FastAPI application entry point.
    - `rig.py`: Rig control logic.
    - `static/`: Frontend assets.
- `ext/`: External dependencies (Hamlib, Netmind).
- `Makefile`: Build and test orchestration.

## Rules

### 1. Testing Requirements
All changes must be verified with the appropriate test suite.
- **UI Changes**: MUST have a **Playwright** test.
    - Run: `make test-e2e`
    - Location: `e2e-tests/`
- **Python Changes**: MUST have a **Pytest** style test.
    - Run: `make test-py`
    - Location: `tests/`
- **JavaScript Changes**: MUST have a **Jest** test.
    - Run: `make test-js`
    - Location: `js-tests/`
- **Testing**: For network protocol verification use the `Netmind` proxy if needed.
- **Configuration**: Configuration profiles are used extensively in E2E tests to avoid polluting the global config.
- **General**: All changes must be verified with the appropriate test suite.

### 2. Style Guidelines
- **General**: Follow PEP 8 for Python, and standard modern JS practices.
- **General**: Document all non-trivial code with comments.  Assume the reader is a peer developer with a general understanding of software development.
- **Python**: Use **Google Style Docstrings** for all functions and classes.
- **JavaScript**: Use **JSDoc** for all functions and classes.

### 3. Build System
- Use the `Makefile` for all build and test operations.
    - `make all`: Build everything.
    - `make run`: Run the server.
    - `make test`: Run all tests.

## Important Context for AI Agents
- **Python**: Python code should be pythonic, and not use any golang, javascript, java, or c++ patterns.  Avoid using callables when initializing classes.
- **Python**: Prefer to use raw strings for rigctl commands (e.g. `r"\get_powerstat"`).
- **Config Persistence**: New rig settings must be added to the `RigConfig` model in `config.py` to be persistent. Frontend-only `localStorage` should be avoided for core rig settings.
- **Data Flow**: `RigClient.safe_status` in `rig.py` is the source of truth for the frontend dashboard. Ensure new config fields are exposed there.
- **UI/CSS**: Global styles (fonts, vars) belong in `style.css`.
- **UI/CSS**: Use `box-sizing: border-box` on elements with padding to prevent overflow in constrained containers (like previews).
- **UI/CSS**: Use CSS Grid for consistent form field alignment, matching the project's existing label layout (`180px 1fr`).
- **Documentation**: Update `docs/design.md` with any relevant changes to the architecture or design.  Also update README.md with any relevant changes to the codebase.