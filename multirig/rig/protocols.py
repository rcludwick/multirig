"""
Protocol Parsers.

This module provides parsers for interpreting network traffic content, specifically
targeting Hamlib protocol messages for semantic display.
"""

import re
from typing import Optional, Union

class HamlibParser:
    """Parses Hamlib 'rigctld' TCP protocol commands into human-readable descriptions.
    
    This parser uses regex patterns to identify common Hamlib commands and responses,
translating them into semantic strings (e.g., "SET FREQ" instead of "F ...").
    """
    
    # Regex patterns for common Hamlib commands
    PATTERNS = [
        (r"^F\s+(\d+)", "SET FREQ"),
        (r"^f", "GET FREQ"),
        (r"^M\s+(\w+)\s+(\d+)", "SET MODE"),
        (r"^m", "GET MODE"),
        (r"^L\s+(\w+)\s+([\d\.]+)", "SET LEVEL"),
        (r"^l\s+(\w+)", "GET LEVEL"),
        (r"^T\s+([01])", "SET PTT"),
        (r"^t", "GET PTT"),
        (r"^\\dump_state", "DUMP STATE"),
        (r"^\\dump_caps", "DUMP CAPS"),
        (r"^\\get_powerstat", "GET POWERSTAT"),
        (r"^\\chk_vfo", "CHECK VFO"),
        (r"^\\set_vfo\s+(\w+)", "SET VFO"),
        (r"^\\get_vfo", "GET VFO"),
        (r"^RPRT\s+0", "SUCCESS"),
        (r"^RPRT\s+-(\d+)", "ERROR")
    ]

    _COMPILED_PATTERNS = [(re.compile(p), l) for p, l in PATTERNS]

    @classmethod
    def decode(cls, data: Union[bytes, str]) -> str:
        """Decodes content into a semantic description if it matches Hamlib syntax.

        Falls back to raw string representation if no pattern matches.

        Args:
            data: The data to decode (bytes or string).

        Returns:
            A string describing the packet content (e.g., "SET FREQ: 14000000" or "RAW: ...").
        """
        if isinstance(data, bytes):
            try:
                text = data.decode("utf-8").strip()
            except UnicodeDecodeError:
                return f"<BINARY: {len(data)} bytes>"
        else:
            text = str(data).strip()

        if not text:
            return "<EMPTY>"

        # Check against known patterns
        for pattern, label in cls._COMPILED_PATTERNS:
            match = pattern.match(text)
            if match:
                args = " ".join(match.groups())
                return f"{label}: {args}" if args else label
        
        # Heuristic: If it looks like a frequency (just numbers), label it
        if text.isdigit() and len(text) > 6:
            return f"DATA: {text} Hz"

        return f"RAW: {text}"
