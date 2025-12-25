from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

def _parse_bool_flag(v: str) -> bool:
    """Parse a boolean flag from dump_caps output.
    
    Args:
        v: Flag character ('Y', 'E', 'N', etc.).
    
    Returns:
        True if flag is 'Y' or 'E', False otherwise.
    """
    s = (v or "").strip().upper()
    return s in {"Y", "E"}


def _parse_mode_list(rest: str) -> list[str]:
    """Parse mode list from dump_caps output.
    
    Args:
        rest: Mode list string (e.g., "USB LSB CW AM FM").
    
    Returns:
        List of unique mode strings, deduplicated and cleaned.
    """
    rest = (rest or "").strip()
    if not rest or rest.startswith("None"):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for tok in rest.split():
        t = tok.strip().rstrip(",;:")
        t = t.rstrip(".")
        if not t or t == "None":
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def parse_dump_caps(text: str) -> tuple[dict[str, bool], list[str]]:
    """Parse rig capabilities from dump_caps output.
    
    Args:
        text: Output from 'dump_caps' rigctl command.
    
    Returns:
        Tuple of (capabilities dict, modes list). Capabilities dict has keys like
        'freq_get', 'freq_set', 'mode_get', 'mode_set', 'vfo_get', 'vfo_set',
        'ptt_get', 'ptt_set' with boolean values.
    """
    caps: dict[str, bool] = {}
    modes: list[str] = []
    modes_seen: set[str] = set()
    
    cap_map = {
        "Can set Frequency": "freq_set",
        "Can get Frequency": "freq_get",
        "Can set Mode": "mode_set",
        "Can get Mode": "mode_get",
        "Can set VFO": "vfo_set",
        "Can get VFO": "vfo_get",
        "Can set PTT": "ptt_set",
        "Can get PTT": "ptt_get",
    }

    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("Mode list:"):
            _, rest = s.split(":", 1)
            for m in _parse_mode_list(rest):
                if m not in modes_seen:
                    modes_seen.add(m)
                    modes.append(m)
            continue

        if ":" not in s:
            continue
            
        key, rest = s.split(":", 1)
        key = key.strip()
        
        if key in cap_map:
            caps[cap_map[key]] = _parse_bool_flag(rest.strip()[:1])

    return caps, modes


class RigctlError(Exception):
    """Exception raised when a rigctl command returns an error code."""
    def __init__(self, code: int, message: str = ""):
        self.code = code
        self.message = message
        super().__init__(f"RPRT {code}: {message}" if message else f"RPRT {code}")


@dataclass
class RigStatus:
    connected: bool
    frequency_hz: Optional[int] = None
    mode: Optional[str] = None
    passband: Optional[int] = None
    error: Optional[str] = None
