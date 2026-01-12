"""
Configuration models for MultiRig with Zenoh.

This module defines the configuration structure for the application, including:
- Rig configurations with connection settings and band limits
- Band presets for quick frequency selection
- Application-level settings
- Profile management for different operating scenarios
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal, List, Any, Dict

import yaml
from pydantic import BaseModel, Field, model_validator


def _normalize_band_label(label: str) -> str:
    """Normalize a band label to lowercase for comparison."""
    return (label or "").strip().lower()


# Amateur radio band definitions (ITU Region 2 / US)
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


def _band_limits(label: str) -> Optional[tuple[int, int]]:
    """Get the default band limits for a known amateur band label.

    Args:
        label: Band label (e.g. "20m", "2m", "70cm")

    Returns:
        Tuple of (lower_hz, upper_hz), or None if unknown
    """
    key = _normalize_band_label(label)
    d = _BAND_DEFINITIONS_BY_KEY.get(key)
    if not d:
        return None
    return int(d["lo"]), int(d["hi"])


def _all_band_definitions() -> List[Dict[str, Any]]:
    """Return all known amateur radio band definitions."""
    return [{**d} for d in _BAND_DEFINITIONS]


def _default_band_presets() -> List[BandPreset]:
    """Return the default set of enabled band presets."""
    return [
        BandPreset(label=d["label"], frequency_hz=int(d["default_hz"]), enabled=True)
        for d in _BAND_DEFINITIONS
    ]


class BandPreset(BaseModel):
    """A quick-select band preset and its allowed frequency range.
    
    Band presets provide:
    1. Quick frequency selection buttons in the UI
    2. Optional frequency range validation (band limits)
    
    The lower_hz and upper_hz fields define the allowed range for this band.
    If not specified, they are auto-filled from standard band definitions.
    """

    label: str
    frequency_hz: int
    enabled: bool = True
    lower_hz: Optional[int] = None
    upper_hz: Optional[int] = None

    @model_validator(mode="after")
    def _fill_limits(self):
        """Auto-fill band limits from standard definitions if not specified."""
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


class RigConfig(BaseModel):
    """Configuration for a single rig.
    
    Supports two connection types:
    1. rigctld: Connect to existing rigctld TCP server
    2. managed: Spawn and manage rigctld subprocess
    """

    # Identity
    rig_id: str = Field(description="Unique identifier for this rig")
    name: str = Field(default="Rig", description="Friendly name")
    enabled: bool = Field(default=True, description="Enable this rig")
    
    # Connection settings
    connection_type: Literal["rigctld", "managed"] = Field(
        default="rigctld", description="Connection backend"
    )
    
    # rigctld (TCP) settings
    host: str = Field(default="127.0.0.1", description="rigctld host")
    port: int = Field(default=4532, description="rigctld TCP port")
    
    # managed settings (spawns rigctld subprocess)
    model_id: Optional[int] = Field(default=None, description="hamlib model id (-m)")
    device: Optional[str] = Field(default=None, description="serial device (-r)")
    baud: Optional[int] = Field(default=38400, description="baud rate (-s)")
    serial_opts: Optional[str] = Field(default=None, description="e.g., N8 RTSCTS")
    extra_args: Optional[str] = Field(default=None, description="extra rigctl args")
    
    # Behavior
    poll_interval_ms: int = Field(
        default=1000,
        description="Minimum time between status polls (milliseconds)",
    )
    
    # Safety
    allow_out_of_band: bool = Field(
        default=False,
        description="Allow setting frequencies outside enabled band preset ranges",
    )
    band_presets: List[BandPreset] = Field(default_factory=_default_band_presets)
    
    # UI
    color: str = Field(default="#a4c356", description="Primary color for the rig UI")
    inverted: bool = Field(default=False, description="Invert LCD colors (dark mode)")


class SyncConfig(BaseModel):
    """Sync engine configuration."""
    
    enabled: bool = Field(default=False, description="Enable rig synchronization")
    source_rig_id: Optional[str] = Field(default=None, description="Source rig ID")
    follower_rig_ids: List[str] = Field(default_factory=list, description="Follower rig IDs")
    
    # What to sync
    sync_frequency: bool = Field(default=True, description="Sync frequency changes")
    sync_mode: bool = Field(default=True, description="Sync mode changes")
    sync_ptt: bool = Field(default=False, description="Sync PTT changes")


class RigctlServerConfig(BaseModel):
    """External rigctl server configuration (for WSJT-X, etc.)."""
    
    enabled: bool = Field(default=True, description="Enable rigctl server")
    host: str = Field(default="127.0.0.1", description="Bind host")
    port: int = Field(default=4534, description="Bind port")
    target_rig_id: str = Field(default="rig1", description="Which rig to control")


class AppConfig(BaseModel):
    """Top-level application configuration.
    
    This is the root configuration object that gets serialized to/from YAML.
    """

    # Rigs
    rigs: List[RigConfig] = Field(
        default_factory=lambda: [
            RigConfig(rig_id="rig1", name="Rig 1"),
        ]
    )
    
    # Sync engine
    sync: SyncConfig = Field(default_factory=SyncConfig)
    
    # Rigctl server for external apps
    rigctl_server: RigctlServerConfig = Field(default_factory=RigctlServerConfig)
    
    # API Gateway
    api_host: str = Field(default="0.0.0.0", description="API bind host")
    api_port: int = Field(default=8000, description="API port")
    
    # Test mode (excludes this from serialization)
    test_mode: bool = Field(
        default=False, 
        exclude=True, 
        description="If true, config changes are not saved to disk"
    )


# ===== Profile Management =====

class Profile(BaseModel):
    """A named configuration profile."""
    
    name: str = Field(description="Profile name")
    description: str = Field(default="", description="Profile description")
    config: AppConfig = Field(description="Configuration for this profile")


def get_config_dir() -> Path:
    """Get the configuration directory path.
    
    Returns:
        Path to config directory (~/.multirig by default)
    """
    config_dir = os.getenv("MULTIRIG_CONFIG_DIR")
    if config_dir:
        return Path(config_dir)
    return Path.home() / ".multirig"


def get_config_path(profile_name: str = "default") -> Path:
    """Get the path to a configuration file.
    
    Args:
        profile_name: Name of the profile
        
    Returns:
        Path to the config file
    """
    return get_config_dir() / f"{profile_name}.yaml"


def load_config(profile_name: str = "default") -> AppConfig:
    """Load configuration from a profile.
    
    Args:
        profile_name: Name of the profile to load
        
    Returns:
        Loaded configuration, or default if file doesn't exist
    """
    config_path = get_config_path(profile_name)
    
    if not config_path.exists():
        return AppConfig()
    
    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
            return AppConfig(**data)
    except Exception as e:
        print(f"Error loading config from {config_path}: {e}")
        return AppConfig()


def save_config(config: AppConfig, profile_name: str = "default"):
    """Save configuration to a profile.
    
    Args:
        config: Configuration to save
        profile_name: Name of the profile
    """
    if config.test_mode:
        return  # Don't save in test mode
    
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    
    config_path = get_config_path(profile_name)
    
    try:
        with open(config_path, 'w') as f:
            # Serialize to dict then to YAML
            data = config.model_dump(exclude={"test_mode"})
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"Error saving config to {config_path}: {e}")


def list_profiles() -> List[str]:
    """List available configuration profiles.
    
    Returns:
        List of profile names
    """
    config_dir = get_config_dir()
    if not config_dir.exists():
        return []
    
    profiles = []
    for path in config_dir.glob("*.yaml"):
        profiles.append(path.stem)
    
    return sorted(profiles)


def delete_profile(profile_name: str):
    """Delete a configuration profile.
    
    Args:
        profile_name: Name of the profile to delete
    """
    if profile_name == "default":
        raise ValueError("Cannot delete default profile")
    
    config_path = get_config_path(profile_name)
    if config_path.exists():
        config_path.unlink()


def detect_bands_from_ranges(freq_ranges: List[tuple[int, int]]) -> List[BandPreset]:
    """Detect which amateur radio bands are supported based on frequency ranges.
    
    This is useful when a rig reports its frequency coverage via dump_state.
    
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
    
    # Lines 4 and 5 (0-indexed: 3 and 4) contain RX and TX frequency ranges
    # Format: "min_freq max_freq modes ..."
    # Line 0: protocol version
    # Line 1: model
    # Line 2: ITU region
    # Line 3: RX range
    # Line 4: TX range
    for line_idx in [3, 4]:
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
