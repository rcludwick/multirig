from __future__ import annotations
from typing import Optional, List, Union
from pydantic import BaseModel

class BaseResponse(BaseModel):
    cmd: str
    request_id: Optional[str] = None
    source: Optional[str] = None
    destination: Optional[str] = None
    raw_response: Optional[str] = None
    result: int = 0  # RPRT code, 0=Success, non-zero=Error

class SuccessResponse(BaseResponse):
    """Generic success response (RPRT 0)"""
    pass

class FreqResponse(BaseResponse):
    frequency: int

class ModeResponse(BaseResponse):
    mode: str
    passband: int

class VfoResponse(BaseResponse):
    vfo: str

class PttResponse(BaseResponse):
    ptt: int

class LevelResponse(BaseResponse):
    level_name: str
    value: float

class SplitVfoResponse(BaseResponse):
    split: int
    tx_vfo: str

class PowerstatResponse(BaseResponse):
    status: int

class DumpStateResponse(BaseResponse):
    lines: List[str]

class DumpCapsResponse(BaseResponse):
    lines: List[str]

class InfoResponse(BaseResponse):
    info: str

class ModelResponse(BaseResponse):
    model: str

class VersionResponse(BaseResponse):
    version: str

class ConfResponse(BaseResponse):
    token: str
    value: str

class ChkVfoResponse(BaseResponse):
    status: int

HamlibResponse = Union[
    SuccessResponse, FreqResponse, ModeResponse, 
    VfoResponse, PttResponse, LevelResponse, 
    SplitVfoResponse, PowerstatResponse,
    DumpStateResponse, DumpCapsResponse,
    InfoResponse, ModelResponse, VersionResponse,
    ConfResponse, ChkVfoResponse
]
