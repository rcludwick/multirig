from __future__ import annotations
from typing import Optional, List, Tuple
from .messages import (
    HamlibCommand, SetFreq, GetFreq, SetMode, GetMode,
    SetVfo, GetVfo, SetPtt, GetPtt, GetLevel, GetSplitVfo,
    GetPowerstat, DumpState, DumpCaps, GetInfo, Model, Version,
    Token, SetConf, GetConf, ChkVfo
)
from .responses import (
    BaseResponse, SuccessResponse, FreqResponse, ModeResponse,
    VfoResponse, PttResponse, LevelResponse, SplitVfoResponse,
    PowerstatResponse, DumpStateResponse, DumpCapsResponse,
    InfoResponse, ModelResponse, VersionResponse, ConfResponse,
    ChkVfoResponse
)

def _parse_rprt(line: str) -> Optional[int]:
    """Extract code from 'RPRT x' line."""
    if "RPRT" in line:
        try:
            return int(line.split("RPRT")[1].strip())
        except (IndexError, ValueError):
            pass
    return None

def parse_response(cmd: HamlibCommand, raw: str) -> BaseResponse:
    """
    Parse the raw response string based on the command that generated it.
    Handles both standard and Extended Response Protocol (ERP) formats.
    """
    lines = [L.strip() for L in raw.strip().split('\n') if L.strip()]
    if not lines:
        return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=-1)

    # Check for RPRT at end
    last_line = lines[-1]
    rprt_code = _parse_rprt(last_line)
    
    result_code = rprt_code if rprt_code is not None else 0

    # Dispatch based on command type for expected return structures
    
    # SET COMMANDS (Expect only RPRT)
    if isinstance(cmd, (SetFreq, SetMode, SetVfo, SetPtt, SetConf)):
        # For set commands, result code is the only payload
        return SuccessResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=result_code)

    # Common error check for GET commands
    if result_code != 0:
        return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=result_code)

    # GET FREQ
    if isinstance(cmd, GetFreq):
        val_str = lines[0]
        if cmd.erp_prefix and ":" in val_str:
            parts = val_str.split("Frequency:")
            if len(parts) > 1:
                val_str = parts[1]
            else:
                val_str = val_str.split(":")[-1]
        
        try:
            hz = int(float(val_str.strip()))
            return FreqResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, frequency=hz, result=result_code)
        except ValueError:
            return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=-1)

    # GET MODE
    if isinstance(cmd, GetMode):
        mode = lines[0]
        passband = 0
        if len(lines) > 1 and "RPRT" not in lines[1]:
             try: passband = int(lines[1])
             except: pass
        
        return ModeResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, mode=mode, passband=passband, result=result_code)

    # GET VFO
    if isinstance(cmd, GetVfo):
        return VfoResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, vfo=lines[0], result=result_code)
    
    # GET PTT
    if isinstance(cmd, GetPtt):
        try:
            return PttResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, ptt=int(lines[0]), result=result_code)
        except:
             return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=-1)

    # CHECK VFO
    if isinstance(cmd, ChkVfo):
        val = lines[0]
        if "CHKVFO" in val:
            val = val.replace("CHKVFO", "").strip()
        try:
            return ChkVfoResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, status=int(val), result=result_code)
        except:
            return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=-1)

    # DUMP STATE
    if isinstance(cmd, DumpState):
        data_lines = [L for L in lines if "RPRT" not in L and "dump_state:" not in L]
        return DumpStateResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, lines=data_lines, result=result_code)

    # Default fallback
    return BaseResponse(cmd=cmd.cmd, request_id=cmd.request_id, source=cmd.source, destination=cmd.source, raw_response=raw, result=result_code)
