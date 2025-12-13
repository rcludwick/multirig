from __future__ import annotations

from pathlib import Path
from typing import Optional, Literal

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
    rig_a: RigConfig = Field(default_factory=lambda: RigConfig(name="A"))
    rig_b: RigConfig = Field(
        default_factory=lambda: RigConfig(name="B", port=4533)
    )
    poll_interval_ms: int = 750


def load_config(path: Path) -> AppConfig:
    if path.exists():
        data = yaml.safe_load(path.read_text()) or {}
        return AppConfig.model_validate(data)
    cfg = AppConfig()
    save_config(cfg, path)
    return cfg


def save_config(cfg: AppConfig, path: Path) -> None:
    path.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False))
