from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal, List, Any, Dict

import yaml
from pydantic import BaseModel, Field, model_validator


def _normalize_band_label(label: str) -> str:
    return (label or "").strip().lower()


_BAND_DEFINITIONS: List[Dict[str, Any]] = [
    {"label": "160m", "lo": 1800000, "hi": 2000000, "default_hz": 1900000},
    {"label": "80m", "lo": 3500000, "hi": 4000000, "default_hz": 3573000},
    {"label": "60m", "lo": 5330000, "hi": 5406000, "default_hz": 5357000},
    {"label": "40m", "lo": 7000000, "hi": 7300000, "default_hz": 7074000},
    {"label": "30m", "lo": 10100000, "hi": 10150000, "default_hz": 10136000},
    {"label": "20m", "lo": 14000000, "hi": 14350000, "default_hz": 14074000},
    {"label": "17m", "lo": 18068000, "hi": 18168000, "default_hz": 18100000},
    {"label": "15m", "lo": 21000000, "hi": 21450000, "default_hz": 21074000},
    {"label": "12m", "lo": 24890000, "hi": 24990000, "default_hz": 24915000},
    {"label": "10m", "lo": 28000000, "hi": 29700000, "default_hz": 28074000},
    {"label": "6m", "lo": 50000000, "hi": 54000000, "default_hz": 50125000},
    {"label": "2m", "lo": 144000000, "hi": 148000000, "default_hz": 145000000},
    {"label": "1.25m", "lo": 222000000, "hi": 225000000, "default_hz": 223500000},
    {"label": "70cm", "lo": 420000000, "hi": 450000000, "default_hz": 432100000},
    {"label": "33cm", "lo": 902000000, "hi": 928000000, "default_hz": 903000000},
    {"label": "23cm", "lo": 1240000000, "hi": 1300000000, "default_hz": 1296000000},
]

_BAND_DEFINITIONS_BY_KEY: Dict[str, Dict[str, Any]] = {
    _normalize_band_label(d["label"]): d for d in _BAND_DEFINITIONS
}


class BandPreset(BaseModel):
    """A quick-select band preset and its allowed frequency range."""

    label: str
    frequency_hz: int
    enabled: bool = True
    lower_hz: Optional[int] = None
    upper_hz: Optional[int] = None

    @model_validator(mode="after")
    def _fill_limits(self):
        if self.lower_hz is not None and self.upper_hz is not None:
            return self
        limits = _band_limits(self.label)
        if limits is None:
            return self
        lo, hi = limits
        if self.lower_hz is None:
            self.lower_hz = lo
        if self.upper_hz is None:
            self.upper_hz = hi
        return self


def _band_limits(label: str) -> Optional[tuple[int, int]]:
    """Return default band limits for a known amateur band label.

    Args:
        label: Band label (e.g. "20m", "2m", "70cm").

    Returns:
        Tuple of (lower_hz, upper_hz), or None if unknown.
    """
    key = _normalize_band_label(label)
    d = _BAND_DEFINITIONS_BY_KEY.get(key)
    if not d:
        return None
    return int(d["lo"]), int(d["hi"])


def _all_band_definitions() -> List[Dict[str, Any]]:
    """Return all known amateur radio band definitions."""
    return [{**d} for d in _BAND_DEFINITIONS]


def detect_bands_from_ranges(freq_ranges: List[tuple[int, int]]) -> List[BandPreset]:
    """Detect which amateur radio bands are supported based on frequency ranges.
    
    Args:
        freq_ranges: List of (min_hz, max_hz) tuples representing rig's frequency coverage
        
    Returns:
        List of BandPreset objects for bands that overlap with the rig's ranges
    """
    if not freq_ranges:
        return _default_band_presets()
    
    band_defs = _all_band_definitions()
    detected_presets = []
    
    for band_def in band_defs:
        band_lo = band_def["lo"]
        band_hi = band_def["hi"]
        
        # Check if this band overlaps with any of the rig's frequency ranges
        for rig_lo, rig_hi in freq_ranges:
            # Check for overlap: band overlaps if it's not completely outside the rig range
            if not (band_hi < rig_lo or band_lo > rig_hi):
                detected_presets.append(
                    BandPreset(
                        label=band_def["label"],
                        frequency_hz=band_def["default_hz"],
                        enabled=True,
                    )
                )
                break  # Found overlap, no need to check other ranges for this band
    
    return detected_presets if detected_presets else _default_band_presets()


def parse_dump_state_ranges(dump_state_lines: List[str]) -> List[tuple[int, int]]:
    """Parse dump_state output to extract frequency ranges.
    
    Args:
        dump_state_lines: Lines from dump_state command output
        
    Returns:
        List of (min_hz, max_hz) tuples
    """
    ranges = []
    
    # Lines 3 and 4 (0-indexed: 2 and 3) contain RX and TX frequency ranges
    # Format: "min_freq max_freq modes ..."
    for line_idx in [2, 3]:
        if line_idx >= len(dump_state_lines):
            continue
        
        line = dump_state_lines[line_idx].strip()
        parts = line.split()
        
        if len(parts) >= 2:
            try:
                min_hz = int(float(parts[0]))
                max_hz = int(float(parts[1]))
                if min_hz > 0 and max_hz > min_hz:
                    ranges.append((min_hz, max_hz))
            except (ValueError, IndexError):
                continue
    
    return ranges


def _default_band_presets() -> List[BandPreset]:
    """Return the default set of enabled band presets."""
    return [
        BandPreset(label=d["label"], frequency_hz=int(d["default_hz"]), enabled=True)
        for d in _BAND_DEFINITIONS
    ]


class RigConfig(BaseModel):
    """Configuration for a single rig and its connection backend."""

    name: str = Field(default="Rig", description="Friendly name")
    enabled: bool = Field(default=True, description="Enable this rig for rigctl fanout")
    poll_interval_ms: int = Field(
        default=1000,
        description="Minimum time between status polls for this rig (reduces traffic to the physical device)",
    )
    # How to talk to the rig: 'rigctld' over TCP (default, backward compatible) or 'hamlib' via local rigctl
    connection_type: Literal["rigctld", "hamlib"] = Field(
        default="hamlib", description="Connection backend"
    )

    # rigctld (TCP) settings
    host: str = Field(default="127.0.0.1", description="rigctld host")
    port: int = Field(default=4532, description="rigctld TCP port")
    # Optional: command to launch rigctld if desired (not used initially)
    rigctld_cmd: Optional[str] = None

    # hamlib direct (rigctl) settings
    model_id: Optional[int] = Field(default=None, description="hamlib model id (-m)")
    device: Optional[str] = Field(default=None, description="serial device (-r)")
    baud: Optional[int] = Field(default=38400, description="baud rate (-s)")
    serial_opts: Optional[str] = Field(default=None, description="e.g., N8 RTSCTS")
    extra_args: Optional[str] = Field(default=None, description="extra rigctl args")

    allow_out_of_band: bool = Field(
        default=False,
        description="Allow setting frequencies outside enabled band preset ranges",
    )
    follow_main: bool = Field(
        default=True,
        description="If true, this rig follows the main rig (mirrors freq/mode). If false, manual only.",
    )
    band_presets: List[BandPreset] = Field(default_factory=_default_band_presets)
    color: str = Field(default="#a4c356", description="Primary color for the rig UI")


class AppConfig(BaseModel):
    """Top-level application configuration.

    Notes:
        `test_mode` is derived from the `MULTIRIG_TEST_MODE` environment variable
        and is excluded from serialization.
    """

    # Multiple rigs instead of fixed A/B
    rigs: List[RigConfig] = Field(
        default_factory=lambda: [
            RigConfig(name="Rig 1"),
            RigConfig(name="Rig 2", port=4533),
        ]
    )
    rigctl_listen_host: str = Field(default="127.0.0.1", description="Rigctl TCP listener bind host")
    rigctl_listen_port: int = Field(default=4534, description="Rigctl TCP listener port")
    rigctl_to_main_enabled: bool = True
    poll_interval_ms: int = 1000
    sync_enabled: bool = True
    sync_source_index: int = 0
    test_mode: bool = Field(default=False, exclude=True, description="If true, config changes are not saved to disk")


def _migrate_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy config with `rig_a`/`rig_b` to the list-based format.

    Args:
        data: Raw config mapping parsed from YAML.

    Returns:
        Mapping in the new schema shape.
    """
    if "rigs" in data:
        return data
    rigs: List[Dict[str, Any]] = []
    if "rig_a" in data:
        rigs.append(data.get("rig_a") or {})
    if "rig_b" in data:
        rigs.append(data.get("rig_b") or {})
    if not rigs:
        # No rigs present; create defaults
        rigs = [RigConfig(name="Rig 1").model_dump(), RigConfig(name="Rig 2", port=4533).model_dump()]
    # Carry over poll interval if present
    migrated: Dict[str, Any] = {
        "rigs": rigs,
        "rigctl_listen_host": data.get("rigctl_listen_host", "127.0.0.1"),
        "rigctl_listen_port": data.get("rigctl_listen_port", 4534),
        "rigctl_to_main_enabled": data.get("rigctl_to_main_enabled", True),
        "poll_interval_ms": data.get("poll_interval_ms", 1000),
        "sync_enabled": data.get("sync_enabled", True),
        "sync_source_index": data.get("sync_source_index", 0),
    }
    return migrated


def load_config(path: Path) -> AppConfig:
    """Load configuration from disk and apply schema migration.

    The `test_mode` flag is derived from the `MULTIRIG_TEST_MODE` environment
    variable.

    Args:
        path: Path to the main YAML config.

    Returns:
        A validated `AppConfig` instance.
    """
    test_mode = os.getenv("MULTIRIG_TEST_MODE") == "1"
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
        data = _migrate_config(raw)
        cfg = AppConfig.model_validate(data)
        cfg.test_mode = test_mode
        # If migration happened (legacy keys), write back in new shape
        if "rigs" in data and ("rig_a" in raw or "rig_b" in raw):
            save_config(cfg, path)
        return cfg
    cfg = AppConfig()
    cfg.test_mode = test_mode
    save_config(cfg, path)
    return cfg


def save_config(cfg: AppConfig, path: Path) -> None:
    """Persist configuration to disk.

    In `test_mode`, this is a no-op.

    Args:
        cfg: Configuration to save.
        path: Path to write YAML to.
    """
    if cfg.test_mode:
        return
    path.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False))
