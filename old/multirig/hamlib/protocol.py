from __future__ import annotations
from enum import Enum

class HamlibProtocol(str, Enum):
    """
    Standard command strings for Hamlib protocol.
    """
    SET_FREQ         = "F"
    GET_FREQ         = "f"
    SET_MODE         = "M"
    GET_MODE         = "m"
    SET_VFO          = "V"
    GET_VFO          = "v"
    SET_PTT          = "T"
    GET_PTT          = "t"
    GET_LEVEL        = "l"
    GET_SPLIT_VFO    = "s"
    GET_POWERSTAT    = "get_powerstat"
    DUMP_STATE       = "dump_state"
    DUMP_CAPS        = "dump_caps"
    GET_INFO         = "get_info"
    MODEL            = "model"
    VERSION          = "version"
    TOKEN            = "token"
    SET_CONF         = "set_conf"
    GET_CONF         = "get_conf"
    CHK_VFO          = "chk_vfo"

    # Aliases
    SET_FREQ_LONG    = "set_freq"
    GET_FREQ_LONG    = "get_freq"
    SET_MODE_LONG    = "set_mode"
    GET_MODE_LONG    = "get_mode"
    SET_VFO_LONG     = "set_vfo"
    GET_VFO_LONG     = "get_vfo"
    SET_PTT_LONG     = "set_ptt"
    GET_PTT_LONG     = "get_ptt"
    GET_LEVEL_LONG   = "get_level"
    GET_SPLIT_VFO_LONG = "get_split_vfo"

    @classmethod
    def normalize(cls, cmd: str) -> str:
        """Map long aliases to short codes where applicable."""
        mapping = {
            "set_freq": "F",
            "get_freq": "f",
            "set_mode": "M",
            "get_mode": "m",
            "set_vfo": "V",
            "get_vfo": "v",
            "set_ptt": "T",
            "get_ptt": "t",
            "get_level": "l",
            "get_split_vfo": "s",
        }
        return mapping.get(cmd, cmd)
