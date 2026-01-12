"""
Hamlib protocol handling package.

Provides pydantic models for commands and responses, plus parsers and formatters
for converting between raw hamlib protocol and structured data.
"""
from .protocol import HamlibProtocol
from .messages import (
    HamlibCommand, BaseCommand,
    SetFreq, GetFreq, SetMode, GetMode,
    SetVfo, GetVfo, SetPtt, GetPtt,
    GetLevel, GetSplitVfo, GetPowerstat,
    DumpState, DumpCaps, GetInfo,
    Model, Version, Token, SetConf, GetConf, ChkVfo
)
from .responses import (
    HamlibResponse, BaseResponse, SuccessResponse,
    FreqResponse, ModeResponse, VfoResponse, PttResponse,
    LevelResponse, SplitVfoResponse, PowerstatResponse,
    DumpStateResponse, DumpCapsResponse, InfoResponse,
    ModelResponse, VersionResponse, ConfResponse, ChkVfoResponse
)
from .parser import parse_line
from .response_parser import parse_response
from .formatter import format_response

__all__ = [
    # Protocol
    "HamlibProtocol",
    # Commands
    "HamlibCommand", "BaseCommand",
    "SetFreq", "GetFreq", "SetMode", "GetMode",
    "SetVfo", "GetVfo", "SetPtt", "GetPtt",
    "GetLevel", "GetSplitVfo", "GetPowerstat",
    "DumpState", "DumpCaps", "GetInfo",
    "Model", "Version", "Token", "SetConf", "GetConf", "ChkVfo",
    # Responses
    "HamlibResponse", "BaseResponse", "SuccessResponse",
    "FreqResponse", "ModeResponse", "VfoResponse", "PttResponse",
    "LevelResponse", "SplitVfoResponse", "PowerstatResponse",
    "DumpStateResponse", "DumpCapsResponse", "InfoResponse",
    "ModelResponse", "VersionResponse", "ConfResponse", "ChkVfoResponse",
    # Functions
    "parse_line", "parse_response", "format_response",
]
