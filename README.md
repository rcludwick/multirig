# MultiRig

Control and sync two ham radio rigs with a modern, dark‑mode web UI. MultiRig mirrors Rig A → Rig B so frequency/mode changes on A are applied to B. Runs on macOS, Linux, and Raspberry Pi.

## Requirements
- Python 3.9+
- hamlib tools in PATH (for `rigctld` and/or `rigctl`)
  - macOS: `brew install hamlib`
  - Debian/Ubuntu/RPi: `sudo apt-get install hamlib` (or `hamlib-utils`)

## Quick start (recommended)
Run the helper script — it creates a virtualenv, installs deps, and starts the app.

```
bash run.sh
```
Then open http://localhost:8000

Environment variables for `run.sh`:
- `PYTHON` (default `python3`)
- `VENV` (default `.venv`)
- `HOST` (default `0.0.0.0`)
- `PORT` (default `8000`)
- `OPEN_BROWSER` set `0` to disable auto‑open (default `1`)
- `REINSTALL_DEPS` set `1` to force reinstall editable deps

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

## Configure your rigs
Open http://localhost:8000/settings and choose how each rig connects:

1) rigctld (TCP)
- Start one `rigctld` per rig with distinct ports, e.g.:
  ```
  rigctld -m <MODEL_ID> -r /dev/ttyUSB0 -s 38400 -t 4532
  rigctld -m <MODEL_ID> -r /dev/ttyUSB1 -s 38400 -t 4533
  ```
- Point WSJT‑X to the Rig A rigctld (host/port); MultiRig mirrors A → B.

2) hamlib (direct rigctl)
- No rigctld needed; MultiRig talks to a persistent `rigctl` subprocess.
- In Settings, pick "hamlib (direct rigctl)" and fill:
  - Model ID (`-m`) — find with `rigctl -l`
  - Device (`-r`) — e.g., `/dev/ttyUSB0` or `/dev/cu.usbserial-*`
  - Baud (`-s`) — e.g., `38400`
  - Optional serial opts and extra args
- On Linux/RPi, ensure access to `/dev/ttyUSB*` (often via `dialout` group).

You can also set the sync poll interval (ms) on the Settings page.

## Endpoints (reference)
- `GET /` — dashboard UI
- `GET /settings` — configuration UI
- `GET /api/status` — status of both rigs + sync flag
- `POST /api/sync/{enabled}` — toggle sync A→B
- `GET /api/config` / `POST /api/config` — read/write config
- `POST /api/rig/{a|b}/set` — set frequency/mode/passband on a rig
- `WS /ws` — streaming updates for the SPA

## Notes
- Config is saved to `multirig.config.yaml` in the working directory (git‑ignored by default).
- Stack: FastAPI + Uvicorn, Pydantic, Jinja2, vanilla JS (SPA via WebSocket).