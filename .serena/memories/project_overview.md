# MultiRig Project Overview

## Purpose
MultiRig is a ham radio rig control application that manages multiple physical rigs (via hamlib's `rigctld` or direct serial `rigctl`). Applications like WSJT-X connect to MultiRig as if it were a standard rig, and MultiRig synchronizes frequency, mode, and other settings across multiple physical radios.

## Tech Stack
- **Backend**: Python 3.9+ with FastAPI and Uvicorn
- **Frontend**: 
  - Current: Vanilla JavaScript with Jinja2 templates (`multirig/static/`)
  - WIP: Vite + TypeScript frontend (`multirig/frontend/`)
- **Package Management**: `uv` for Python dependencies, npm for JS
- **Testing**: pytest (Python), Jest (JS), Playwright (E2E)
- **External Dependencies**:
  - Hamlib (`rigctl`, `rigctld`) for rig control
  - Netmind (in `ext/netmind`) - TCP proxy for debugging network traffic

## Key Concepts
- **Rigs**: Represent physical radios, configured via profiles
- **Profiles**: Configuration sets stored as YAML files in `multirig.config.profiles/`
- **Sync**: Main rig broadcasts changes to follower rigs
- **Band Presets**: Quick frequency presets per rig
- **Capabilities (Caps)**: Per-model feature detection from hamlib
- **Backends**: Different connection methods (managed rigctld, direct process, TCP)

## Architecture
- **multirig/rig/**: Core rig control package
  - `client.py`: RigClient abstraction over backends
  - `backend.py`: Backend interface
  - `managed.py`, `process.py`, `tcp.py`: Backend implementations
  - `server.py`: TCP server for external apps (WSJT-X, etc.)
- **multirig/hamlib/**: Hamlib protocol handling
  - Parser, formatter, and protocol definitions
- **multirig/core.py**: RigManager orchestration

## Configuration
- Main config: `multirig.config.yaml`
- Active profile marker: `multirig.config.active_profile`
- Config profiles directory: `multirig.config.profiles/`
- Environment variables:
  - `MULTIRIG_CONFIG`: Path to config file
  - `PORT`: Server port (default 8000)
  - `OPEN_BROWSER`: Set to "0" to disable auto-open
