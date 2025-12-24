# MultiRig design

This document describes the internal design of MultiRig with an emphasis on:

- The configuration model (`AppConfig` and friends)
- How configuration is loaded/applied at runtime
- Configuration profile management (save/load/delete/export)
- How Playwright E2E tests use configuration profiles to isolate test setups

For the rigctl protocol implementation, also see `docs/rigctld_tcp_protocol.md`.

## Configuration model

### Schema

The main configuration schema is defined in `multirig/config.py`.

- `AppConfig`
  - `rigs: List[RigConfig]`
  - `rigctl_listen_host` / `rigctl_listen_port` (MultiRig's built-in rigctl TCP listener)
  - `rigctl_to_main_enabled`
  - `poll_interval_ms`
  - `sync_enabled`
  - `sync_source_index`
  - `test_mode` (derived from env, excluded from serialization)

- `RigConfig`
  - Connection backend: `connection_type` is either:
    - `rigctld` (connect to an external `rigctld` instance over TCP), or
    - `hamlib` (drive rig control via a local `rigctl` process / bindings)
  - `enabled`, `follow_main`, `allow_out_of_band`
  - `band_presets: List[BandPreset]`

- `BandPreset`
  - `label` (e.g. `20m`, `40m`)
  - `frequency_hz` (default frequency to jump to)
  - `enabled`
  - `lower_hz` / `upper_hz` (limits used for validation)

### Migration

Older configs used `rig_a` / `rig_b`. To keep backwards compatibility:

- `multirig/config.py::_migrate_config()` converts the legacy shape into `rigs: [...]`.
- `load_config()` applies the migration during startup and may write back an updated config.

## Configuration lifecycle

### Load on startup

Startup occurs in `multirig/app.py:create_app()`:

1. Determine config path:
   - `MULTIRIG_CONFIG` if set
   - otherwise `./multirig.config.yaml`
2. Load config via `load_config()`.
3. Build `RigClient` instances from `cfg.rigs`.
4. Create the sync service (`SyncService`) and the built-in rigctl TCP listener (`RigctlTcpServer`).

### Apply at runtime

The authoritative runtime update path is `multirig/app.py::_apply_config(cfg)`.

When a new config is applied:

- `test_mode` is preserved from the currently loaded config.
- `save_config()` persists to disk only when not in `test_mode`.
- Existing rig backends are closed.
- New `RigClient` instances are created.
- The sync service's rig references/settings are updated.
- The rigctl TCP server is restarted to reflect listener host/port changes.

### Test mode

Test mode is enabled by setting:

- `MULTIRIG_TEST_MODE=1`

Behavioral differences:

- `save_config()` becomes a no-op (no filesystem mutations).
- Configuration profiles are stored in-memory (see below).

This is specifically used by Playwright E2E tests so that test runs are isolated and do not modify developer config.

## Configuration profiles

Configuration profiles are named snapshots of an `AppConfig` payload.

### Naming

Profiles are validated by `_is_valid_profile_name(name)`:

- Allowed characters: `[A-Za-z0-9_.-]`
- Length: 1..100

This ensures profiles are safe to use as filenames.

### Storage

Profiles have two storage modes:

#### Non-test mode (persistent)

Profiles are stored next to the main config file in a sibling directory:

- `multirig.config.profiles/`
- Files are saved as `<name>.yaml`

The directory is resolved relative to the active config path:

- `app.state.config_path.parent / "multirig.config.profiles"`

#### Test mode (in-memory)

When `test_mode` is enabled, profiles are stored in-memory:

- `app.state.config_profiles: Dict[str, Dict[str, Any]]`

This allows tests to create and delete profiles without filesystem side effects.

### HTTP API

Profile management endpoints are implemented in `multirig/app.py`:

- `GET /api/config/profiles`
  - Returns `{ status: "ok", profiles: [name, ...] }`

- `POST /api/config/profiles/{name}`
  - Saves the *current* applied config into the named profile

- `POST /api/config/profiles/{name}/load`
  - Loads profile payload
  - Migrates schema (`_migrate_config`)
  - Validates `AppConfig`
  - Applies via `_apply_config`

- `GET /api/config/profiles/{name}/export`
  - Exports profile payload as YAML

- `DELETE /api/config/profiles/{name}`
  - Deletes profile

There are also convenience endpoints for whole-config import/export:

- `GET /api/config/export`
- `POST /api/config/import`

## Settings UI integration

The Settings page includes profile management controls:

- Template: `multirig/templates/settings.html`
- UI logic: `multirig/static/settings.js`

The UI supports:

- Listing profiles
- Saving current config as a profile
- Loading a selected profile
- Deleting a selected profile
- Exporting the current config as YAML
- Importing a YAML config

## Playwright E2E testing design

### Why profiles are used

Playwright tests need to set up MultiRig with different configurations (number of rigs, band presets, sync settings) while:

- avoiding test-to-test coupling
- avoiding filesystem writes
- ensuring setup/teardown is reliable

Profiles provide a server-side abstraction that tests can create, load, and delete.

### Test mode

Playwright runs the server with:

- `MULTIRIG_TEST_MODE=1`

This ensures:

- config writes do not touch `multirig.config.yaml`
- profiles are stored in-memory and can be freely created/deleted

### Helper module

Playwright helper functions live in `e2e-tests/profile_helpers.js`:

- `listProfiles(request)`
- `ensureProfileExists(request, name, { allowCreate, configYaml })`
- `loadProfile(request, name)`
- `deleteProfile(request, name)`

`ensureProfileExists` is intentionally defensive:

- It checks profiles via `GET /api/config/profiles`
- If missing and creation is allowed:
  - It prefers applying config via `POST /api/config` (JSON)
  - Falls back to `POST /api/config/import` (YAML)
  - Persists via `POST /api/config/profiles/{name}`

### Test conventions

- All profiles created by tests should be prefixed with `test_`.
- Tests should delete profiles during teardown.
- Tests assert that after deletion the profile cannot be loaded (negative assertion).

## Dashboard UI Design

The MultiRig dashboard provides a unified interface for monitoring and controlling multiple transceivers simultaneously. It is designed with a responsive grid layout to accommodate varying numbers of connected rigs.

### 1. Top Bar & Global Controls

The top control bar manages the central coordination logic of MultiRig:

- **Rigctl Listener Status**: Displays connection state to the exposed TCP rigctl server.
- **Main Rig Selection**: Dropdown to designate which connected rig acts as the "Main" rig (source of truth for syncing).
- **Sync Toggles**:
    - **TCP → MAIN**: When enabled, commands received via the TCP listener are forwarded to the Main Rig.
    - **MAIN → FOLLOWERS**: When enabled, frequency/mode changes on the Main Rig are automatically replicated to all enabled Follower rigs.
    - **ALL RIGS**: Global master switch to enable/disable communication with all rigs instantly.
- **TCP Traffic Debug**: A collapsible console showing real-time `rigctl` command/response traffic on the TCP listener port.

### 2. Rig Cards

Each configured radio is represented by a "Rig Card" in the main grid.

#### Visual Style
The interface uses a high-contrast "Retro LCD" aesthetic (yellow/green backlight with black segment text) to mimic physical radio displays. This ensures high legibility and provides immediate visual feedback of rig status. A "Dark Mode" (Inverted LCD) preference is persisted in local storage.

#### Card Components

- **Header**:
    - **Rig Name**: As defined in the configuration profile.
    - **Status LED**: Green (Connected/Idle), Red (Error/Disconnected), Yellow (Polling).
    - **Enable Toggle**: Individual switch to enable/disable polling and control for this specific rig.

- **LCD Display**:
    - **Frequency**: Large 7-segment display formatted in MHz (e.g., `14.074.000`) or kHz for VLF.
    - **Mode/Passband**: Current operating mode (USB, LSB, CW, etc.) and passband width.
    - **VFO/PTT**: Indicators for current VFO (A/B), Split status, and TX/RX state (PTT triggers visual highlight).

- **Controls**:
    - **Band Selector**: Quick-access buttons for configured amateur bands (e.g., 20m, 40m).
    - **Mode Selector**: Dropdown to change operating mode.
    - **VFO Controls**: Buttons to swap VFO A/B (if supported).
    - **Follow Main**: Per-rig toggle to opt-out of global syncing (e.g., to operate this rig independently while others follow).

- **Debug Console**:
    - Each card includes a hidden-by-default console showing the raw `rigctl` traffic specific to that rig backend.

### 3. Responsiveness

The dashboard uses a flexible grid system:
- **Desktop**: Multiple columns.
- **Mobile**: Single column stack for phone usage.
