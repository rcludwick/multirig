from __future__ import annotations
from typing import Optional, List
from .protocol import HamlibProtocol
from .messages import (
    HamlibCommand, SetFreq, GetFreq, SetMode, GetMode,
    SetVfo, GetVfo, SetPtt, GetPtt, GetLevel, GetSplitVfo,
    GetPowerstat, DumpState, DumpCaps, GetInfo, Model, Version,
    Token, SetConf, GetConf, ChkVfo
)

def _is_erp_prefix(ch: str) -> bool:
    if not ch: return False
    if ch.isalnum() or ch.isspace(): return False
    if ch in r"\?_": return False
    return True

def parse_line(line: str, request_id: Optional[str] = None, source: Optional[str] = None) -> Optional[HamlibCommand]:
    """
    Parse a raw line from the rigctl protocol into a structured HamlibCommand.
    """
    erp_prefix: Optional[str] = None
    cmdline = line.lstrip()
    
    if not cmdline:
        return None

    # Check for Extended Response Protocol prefix
    if cmdline and _is_erp_prefix(cmdline[0]):
        erp_prefix = cmdline[0]
        cmdline = cmdline[1:].lstrip()

    if not cmdline:
        return None

    parts = cmdline.split()
    cmd = parts[0]
    args = parts[1:]

    # Handle raw command prefix '\' (e.g. \dump_state)
    is_raw = cmd.startswith("\\")
    if is_raw:
        cmd_key = cmd[1:]
    else:
        cmd_key = cmd

    # Normalize aliases (e.g. set_freq -> F)
    norm_cmd = HamlibProtocol.normalize(cmd_key)

    # Dispatch based on normalized command
    if norm_cmd == HamlibProtocol.SET_FREQ:
        if not args: return None
        return SetFreq(frequency=int(float(args[0])), erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_FREQ:
        return GetFreq(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.SET_MODE:
        if not args: return None
        mode = args[0]
        passband = int(float(args[1])) if len(args) > 1 else None
        return SetMode(mode=mode, passband=passband, erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_MODE:
        return GetMode(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.SET_VFO:
        if not args: return None
        return SetVfo(vfo=args[0], erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_VFO:
        return GetVfo(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.SET_PTT:
        if not args: return None
        return SetPtt(ptt=int(args[0]), erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_PTT:
        return GetPtt(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_LEVEL:
        if not args: return None
        return GetLevel(level_name=args[0], erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
    
    elif norm_cmd == HamlibProtocol.GET_SPLIT_VFO:
        return GetSplitVfo(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
        
    elif norm_cmd == HamlibProtocol.GET_POWERSTAT:
        return GetPowerstat(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.DUMP_STATE:
        return DumpState(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.DUMP_CAPS:
        return DumpCaps(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.GET_INFO:
        return GetInfo(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
    
    elif norm_cmd == HamlibProtocol.MODEL:
        return Model(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
        
    elif norm_cmd == HamlibProtocol.VERSION:
        return Version(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
        
    elif norm_cmd == HamlibProtocol.TOKEN:
        return Token(erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.SET_CONF:
        if len(args) < 2: return None
        return SetConf(token=args[0], value=args[1], erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())
        
    elif norm_cmd == HamlibProtocol.GET_CONF:
        if not args: return None
        return GetConf(token=args[0], erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    elif norm_cmd == HamlibProtocol.CHK_VFO:
        # Special case: chk_vfo usually called with leading backslash?
        # Our server treats it specially if is_raw is set.
        return ChkVfo(is_raw=is_raw, erp_prefix=erp_prefix, request_id=request_id, source=source, raw_command=line.encode())

    return None
