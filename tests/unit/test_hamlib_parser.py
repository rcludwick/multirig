from multirig.hamlib.parser import parse_line
from multirig.hamlib.messages import (
    SetFreq, GetFreq, SetMode, GetMode,
    SetVfo, GetVfo, SetPtt, GetPtt,
    GetLevel, GetSplitVfo, GetPowerstat,
    DumpState, DumpCaps, GetInfo,
    Model, Version, Token, SetConf, GetConf, ChkVfo
)
from multirig.hamlib.protocol import HamlibProtocol

def test_parse_set_freq():
    cmd = parse_line("F 14074000")
    assert isinstance(cmd, SetFreq)
    assert cmd.frequency == 14074000
    assert cmd.erp_prefix is None

def test_parse_with_metadata():
    cmd = parse_line("F 14074000", request_id="req123", source="tcp")
    assert isinstance(cmd, SetFreq)
    assert cmd.frequency == 14074000
    assert cmd.request_id == "req123"
    assert cmd.source == "tcp"
    assert cmd.raw_command == b"F 14074000"

def test_parse_set_freq_alias():
    cmd = parse_line("set_freq 14074000")
    assert isinstance(cmd, SetFreq)
    assert cmd.frequency == 14074000

def test_parse_get_freq():
    cmd = parse_line("f")
    assert isinstance(cmd, GetFreq)
    
def test_parse_get_freq_erp():
    cmd = parse_line("+f")
    assert isinstance(cmd, GetFreq)
    assert cmd.erp_prefix == "+"

def test_parse_set_mode():
    cmd = parse_line("M USB 2400")
    assert isinstance(cmd, SetMode)
    assert cmd.mode == "USB"
    assert cmd.passband == 2400

def test_parse_set_mode_no_passband():
    cmd = parse_line("M USB")
    assert isinstance(cmd, SetMode)
    assert cmd.mode == "USB"
    assert cmd.passband is None

def test_parse_dump_state_raw():
    cmd = parse_line(r"\dump_state")
    assert isinstance(cmd, DumpState)
    
def test_parse_dump_state():
    cmd = parse_line("dump_state")
    assert isinstance(cmd, DumpState)

def test_parse_chk_vfo_raw():
    cmd = parse_line(r"\chk_vfo")
    assert isinstance(cmd, ChkVfo)
    assert cmd.is_raw is True

def test_parse_chk_vfo_norm():
    cmd = parse_line("chk_vfo")
    assert isinstance(cmd, ChkVfo)
    assert cmd.is_raw is False

def test_invalid_command():
    assert parse_line("INVALID") is None

def test_empty_command():
    assert parse_line("") is None
    assert parse_line("   ") is None
