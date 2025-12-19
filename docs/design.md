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

## Dashboard notes (original)

For each radio in the config, we need to add those radios in the dashboard.

The dashboard should show the rig name, the current frequency, and the current mode along with the capabilities of the
rig as badges similar to the config page.

Each radio should have a sync button that will sync the frequency, mode, etc to the rig.

Each radio should have a debug window that is hidden by default but will show the rigctl commands being sent and
received by the radio.

The dashboard should show the tcp address and port of the listening rigctl server. This should also have a debug section
that is hidden by default but shows the packets being sent and received by the rigctl server.

Each radio should have a sync all button that will sync the frequency, mode, etc to all radios. This is because an amp
may be connected to a primary radio, but still needs cat control through rigctl.

If PTT is supported, the radio should highlight itself when PTT is active.

For radios that support multiple VFOS the dashboard should show a VFO selector to switch between the VFOs.

For radios that support multiple VFOS, both freuencies should be shown in the dashboard.

For radios that support multiple modes the dashboard should show a mode selector to switch between the modes.

The dashboard should show a list of rigs that are connected to the rigctl server, using red and green lights if they are connected or not. If they become disconnected or start erroring, they should have a red light.

Each radio should have an enable/disable button. This will enable or disable the rigctl server for that radio.

The dashboard should have a global enable/disable button that will enable or disable all rigctl servers. This will be useful if you want to disable all rigs at once.

The dashboard should show which band the rig is on. This will be useful for quickly identifying which rig is on which band.

The config should have a list of bands the rig can be on.

The dashboard should be able to quickly switch between bands.

All of the ham radio bands should be available in the config.

The radio should show which band it is on up through UHF for now.

The frequency should be shown in a digital like nature similar to what a radio might look like. I would like to see it in Mhz with a decimal point and 6 digits after the decimal point. It should look like 146.520000 MHz. For the very low frequency bands switch to kHz.

The mode should be shown in a digital like nature similar to what a radio might look like.

The style for the radio view should look like a backlit LCD display. The background should be a yellowish/green color and the text should be black.

To support the LCD style, we should use a monospace font, maybe one that is similar to a LCD display or dot matrix display.

There should be a queueing system for rigctl commands. Each radio will get its own queue. Each radio will need its own async task to process the queue and to receive rigctl responses.

The server should query the rigs at a regular interval to get the current frequency, mode, etc. This will be used to update the dashboard.

if the rig is not powered on, the LCD display should look like a dark LCD screen that's turned off.
