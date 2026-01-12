from __future__ import annotations
from typing import Optional, Literal, Union, List
from pydantic import BaseModel, Field

from .protocol import HamlibProtocol

class BaseCommand(BaseModel):
    erp_prefix: Optional[str] = None
    request_id: Optional[str] = None
    source: Optional[str] = None
    raw_command: Optional[bytes] = None

class SetFreq(BaseCommand):
    cmd: Literal[HamlibProtocol.SET_FREQ] = HamlibProtocol.SET_FREQ
    frequency: int

class GetFreq(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_FREQ] = HamlibProtocol.GET_FREQ

class SetMode(BaseCommand):
    cmd: Literal[HamlibProtocol.SET_MODE] = HamlibProtocol.SET_MODE
    mode: str
    passband: Optional[int] = None

class GetMode(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_MODE] = HamlibProtocol.GET_MODE

class SetVfo(BaseCommand):
    cmd: Literal[HamlibProtocol.SET_VFO] = HamlibProtocol.SET_VFO
    vfo: str

class GetVfo(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_VFO] = HamlibProtocol.GET_VFO

class SetPtt(BaseCommand):
    cmd: Literal[HamlibProtocol.SET_PTT] = HamlibProtocol.SET_PTT
    ptt: int

class GetPtt(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_PTT] = HamlibProtocol.GET_PTT

class GetLevel(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_LEVEL] = HamlibProtocol.GET_LEVEL
    level_name: str

class GetSplitVfo(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_SPLIT_VFO] = HamlibProtocol.GET_SPLIT_VFO

class GetPowerstat(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_POWERSTAT] = HamlibProtocol.GET_POWERSTAT

class DumpState(BaseCommand):
    cmd: Literal[HamlibProtocol.DUMP_STATE] = HamlibProtocol.DUMP_STATE

class DumpCaps(BaseCommand):
    cmd: Literal[HamlibProtocol.DUMP_CAPS] = HamlibProtocol.DUMP_CAPS

class GetInfo(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_INFO] = HamlibProtocol.GET_INFO

class Model(BaseCommand):
    cmd: Literal[HamlibProtocol.MODEL] = HamlibProtocol.MODEL

class Version(BaseCommand):
    cmd: Literal[HamlibProtocol.VERSION] = HamlibProtocol.VERSION

class Token(BaseCommand):
    cmd: Literal[HamlibProtocol.TOKEN] = HamlibProtocol.TOKEN

class SetConf(BaseCommand):
    cmd: Literal[HamlibProtocol.SET_CONF] = HamlibProtocol.SET_CONF
    token: str
    value: str

class GetConf(BaseCommand):
    cmd: Literal[HamlibProtocol.GET_CONF] = HamlibProtocol.GET_CONF
    token: str

class ChkVfo(BaseCommand):
    cmd: Literal[HamlibProtocol.CHK_VFO] = HamlibProtocol.CHK_VFO
    is_raw: bool = False

HamlibCommand = Union[
    SetFreq, GetFreq, SetMode, GetMode, 
    SetVfo, GetVfo, SetPtt, GetPtt,
    GetLevel, GetSplitVfo, GetPowerstat,
    DumpState, DumpCaps, GetInfo,
    Model, Version, Token,
    SetConf, GetConf, ChkVfo
]
