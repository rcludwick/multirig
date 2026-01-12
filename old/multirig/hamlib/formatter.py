"""
Format HamlibResponse objects back to hamlib protocol bytes.
"""
from __future__ import annotations
from typing import Optional, Sequence

from .responses import (
    HamlibResponse, BaseResponse, SuccessResponse, FreqResponse,
    ModeResponse, VfoResponse, PttResponse, LevelResponse,
    SplitVfoResponse, PowerstatResponse, ChkVfoResponse,
    DumpStateResponse, DumpCapsResponse, InfoResponse,
    ModelResponse, VersionResponse, ConfResponse
)


def _sep_for_erp(prefix: str) -> str:
    """Get separator for Extended Response Protocol."""
    return "\n" if prefix == "+" else prefix


def _records_to_bytes(records: Sequence[str], sep: str) -> bytes:
    """Join records with separator and encode."""
    if sep == "\n":
        return ("\n".join(records) + "\n").encode()
    return (sep.join(records) + sep).encode()


def format_response(
    resp: HamlibResponse,
    erp_prefix: Optional[str] = None,
) -> bytes:
    """Format a HamlibResponse to hamlib protocol bytes.
    
    Args:
        resp: The response to format.
        erp_prefix: Extended Response Protocol prefix (e.g., '+', ';').
        
    Returns:
        Bytes to send back to the client.
    """
    # Error responses
    if resp.result != 0:
        if erp_prefix:
            return f"{erp_prefix}RPRT {resp.result}\n".encode()
        return f"RPRT {resp.result}\n".encode()
    
    # Success response (for SET commands)
    if isinstance(resp, SuccessResponse):
        if erp_prefix:
            return f"{erp_prefix}RPRT {resp.result}\n".encode()
        return f"RPRT {resp.result}\n".encode()
    
    # Frequency response
    if isinstance(resp, FreqResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_freq:", f"Frequency: {resp.frequency}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.frequency}\n".encode()
    
    # Mode response
    if isinstance(resp, ModeResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_mode:", f"Mode: {resp.mode}", f"Passband: {resp.passband}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.mode}\n{resp.passband}\n".encode()
    
    # VFO response
    if isinstance(resp, VfoResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_vfo:", f"VFO: {resp.vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.vfo}\n".encode()
    
    # PTT response
    if isinstance(resp, PttResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_ptt:", f"PTT: {resp.ptt}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.ptt}\n".encode()
    
    # Level response
    if isinstance(resp, LevelResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_level:", f"Level {resp.level_name}: {resp.value}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.value}\n".encode()
    
    # Split VFO response
    if isinstance(resp, SplitVfoResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_split_vfo:", f"Split: {resp.split}", f"TX VFO: {resp.tx_vfo}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.split}\n{resp.tx_vfo}\n".encode()
    
    # Power status response
    if isinstance(resp, PowerstatResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_powerstat:", f"Power Status: {resp.status}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.status}\n".encode()
    
    # ChkVfo response
    if isinstance(resp, ChkVfoResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = [f"chk_vfo: {resp.status}", "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"CHKVFO {resp.status}\n".encode()
    
    # Dump state response
    if isinstance(resp, DumpStateResponse):
        content = "\n".join(resp.lines) + "\n"
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_state:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)
        return content.encode()
    
    # Dump caps response
    if isinstance(resp, DumpCapsResponse):
        content = "\n".join(resp.lines) + "\n"
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["dump_caps:", content.strip(), "RPRT 0"]
            return _records_to_bytes(records, sep)
        return content.encode()
    
    # Info response
    if isinstance(resp, InfoResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_info:", resp.info, "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.info}\nRPRT 0\n".encode()
    
    # Model response
    if isinstance(resp, ModelResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["model:", resp.model, "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.model}\nRPRT 0\n".encode()
    
    # Version response
    if isinstance(resp, VersionResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["version:", resp.version, "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.version}\nRPRT 0\n".encode()
    
    # Conf response
    if isinstance(resp, ConfResponse):
        if erp_prefix:
            sep = _sep_for_erp(erp_prefix)
            records = ["get_conf:", resp.value, "RPRT 0"]
            return _records_to_bytes(records, sep)
        return f"{resp.value}\nRPRT 0\n".encode()
    
    # Fallback for BaseResponse
    if erp_prefix:
        return f"{erp_prefix}RPRT {resp.result}\n".encode()
    return f"RPRT {resp.result}\n".encode()
