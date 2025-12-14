from __future__ import annotations

from pathlib import Path
from typing import Optional, Literal, List, Any, Dict

import yaml
from pydantic import BaseModel, Field


class RigConfig(BaseModel):
    name: str = Field(default="Rig", description="Friendly name")
    # How to talk to the rig: 'rigctld' over TCP (default, backward compatible) or 'hamlib' via local rigctl
    connection_type: Literal["rigctld", "hamlib"] = Field(
        default="rigctld", description="Connection backend"
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


class AppConfig(BaseModel):
    # Multiple rigs instead of fixed A/B
    rigs: List[RigConfig] = Field(
        default_factory=lambda: [
            RigConfig(name="Rig 1"),
            RigConfig(name="Rig 2", port=4533),
        ]
    )
    poll_interval_ms: int = 750
    sync_enabled: bool = True
    sync_source_index: int = 0


def _migrate_config(data: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate legacy config with rig_a/rig_b to new list-based format."""
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
        "poll_interval_ms": data.get("poll_interval_ms", 750),
        "sync_enabled": data.get("sync_enabled", True),
        "sync_source_index": data.get("sync_source_index", 0),
    }
    return migrated


def load_config(path: Path) -> AppConfig:
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
        data = _migrate_config(raw)
        cfg = AppConfig.model_validate(data)
        # If migration happened (legacy keys), write back in new shape
        if "rigs" in data and ("rig_a" in raw or "rig_b" in raw):
            save_config(cfg, path)
        return cfg
    cfg = AppConfig()
    save_config(cfg, path)
    return cfg


def save_config(cfg: AppConfig, path: Path) -> None:
    path.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False))
