# MultiRig

Control and sync multiple ham radio rigs with a modern, dark‑mode / retro-LCD web UI. Choose one rig as the source and MultiRig mirrors its frequency/mode to all the others. Runs on macOS, Linux, and Raspberry Pi.

![Dashboard Preview](docs/assets/dashboard.png)

## Requirements
- Python 3.9+
- hamlib tools in PATH (for `rigctld` and/or `rigctl`)
  - macOS: `brew install hamlib`
  - Debian/Ubuntu/RPi: `sudo apt-get install hamlib` (or `hamlib-utils`)

## Development tools
- Node.js + npm (for Jest)
- `uv` (recommended when using `make` targets)

## Quick start
Run the helper script — it creates a virtualenv, installs deps, and starts the app.

```
make run
```
Then open http://localhost:8000

Environment variables for `run.sh`:
- `PYTHON` (default `python3`)
- `VENV` (default `.venv`)
- `HOST` (default `0.0.0.0`)
- `PORT` (default `8000`)
- `OPEN_BROWSER` set `0` to disable auto‑open (default `1`)
- `REINSTALL_DEPS` set `1` to force reinstall editable deps
- `RIGCTL` (optional) path to hamlib rigctl binary

## Other ways to run
- Using uv (module entry point):
  ```
  uv run -m multirig
  ```
- Using uvicorn directly:
  ```
  uv run python -m uvicorn multirig.app:create_app --factory --host 0.0.0.0 --port 8000
  ```
- Using Python:
  ```
  python main.py
  ```
- After installing the package (editable):
  ```
  pip install -e .
  multirig
  ```

## Testing

MultiRig has three test layers:

- Python unit tests (`pytest`)
- Frontend JS unit tests (`jest`)
- Browser E2E tests (`playwright`)

### Run all tests

```
make test
```

### Python unit tests

```
make test-py
```

### JS unit tests

```
make test-js
```

### Playwright E2E tests

```
make test-e2e
```

Notes:
- E2E tests run MultiRig with `MULTIRIG_TEST_MODE=1` to avoid writing `multirig.config.yaml`.

## Writing Playwright tests

E2E tests live in `tests/e2e/`.

### Config setup via configuration fixtures

Tests should use the `profile_manager` fixture to manipulate configuration profiles.

- Create a unique profile name prefixed with `test_`.
- Use `profile_manager.ensure_profile_exists(..., allow_create=True)` to create the profile.
- Load it with `profile_manager.load_profile()`.
- Delete it in `finally` block using `profile_manager.delete_profile()`.

### Why profiles?

- Profiles are a server-side snapshot of config.
- In `MULTIRIG_TEST_MODE=1` profiles are stored in-memory, so tests don’t touch the filesystem.
- Tests can reliably clean up after themselves and verify that cleanup worked.

## Configure your rigs
Open http://localhost:8000/settings and add one or more rigs. For each rig choose how it connects:

1) Managed rigctld (Serial/USB)
- **Recommended**. MultiRig spawns and manages a local `rigctld` process for you.
- In Settings, pick "Managed rigctld (Serial/USB)" and fill:
  - Model ID (`-m`) — find with `rigctl -l`
  - Device (`-r`) — e.g., `/dev/ttyUSB0` or `/dev/cu.usbserial-*`
  - Baud (`-s`) — e.g., `38400`
  - Optional serial opts and extra args

2) rigctld (TCP)
- Connect to an existing external `rigctld` process (e.g. running on another machine or started manually).
- Point WSJT‑X to the rigctld of your chosen source rig if needed; MultiRig mirrors that to the others.

3) Hamlib (Direct) - **Deprecated**
- Legacy direct subprocess control. Prefer Managed rigctld.

## Endpoints (reference)
- `GET /` — dashboard UI
- `GET /settings` — configuration UI
- `GET /api/status` — returns `{ rigs: [...], sync_enabled, sync_source_index }`
- `POST /api/sync` — body `{ enabled?, source_index? }` to toggle sync and/or set source
- `POST /api/sync/{enabled}` — legacy toggle (kept for backward compatibility)
- `GET /api/config` / `POST /api/config` — read/write config (`{ rigs: [...], poll_interval_ms, sync_* }`)
- `GET /api/config/export` / `POST /api/config/import` — export/import YAML config
- `GET /api/config/profiles` — list profile names
- `POST /api/config/profiles/{name}` — save current config as profile
- `POST /api/config/profiles/{name}/load` — load profile
- `GET /api/config/profiles/{name}/export` — export profile YAML
- `DELETE /api/config/profiles/{name}` — delete profile
- `POST /api/rig/{index}/set` — set frequency/mode/passband on a specific rig by index; legacy `a|b` aliases map to 0/1
- `WS /ws` — streaming updates for the SPA

## License

MIT License. See [LICENSE](LICENSE) for details.

## Notes
- Config is saved to `multirig.config.yaml` in the working directory (git‑ignored by default). Existing configs with `rig_a`/`rig_b` are auto‑migrated to the new multi‑rig format on load.
- Stack: FastAPI + Uvicorn, Pydantic, Jinja2, vanilla JS (SPA via WebSocket).