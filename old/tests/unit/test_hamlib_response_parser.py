from multirig.hamlib.response_parser import parse_response
from multirig.hamlib.messages import SetFreq, GetFreq, SetMode, GetMode, GetPtt, DumpState
from multirig.hamlib.responses import (
    SuccessResponse, FreqResponse, ModeResponse, PttResponse, DumpStateResponse
)


def test_propagate_metadata():
    cmd = SetFreq(frequency=14074000, request_id="req1", source="web")
    raw = "RPRT 0\n"
    resp = parse_response(cmd, raw)
    assert resp.request_id == "req1"
    assert resp.source == "web"
    assert resp.destination == "web"
    assert resp.cmd == "F"
    assert resp.raw_response == raw

def test_parse_set_freq_success():
    cmd = SetFreq(frequency=14074000)
    resp = parse_response(cmd, "RPRT 0\n")
    assert isinstance(resp, SuccessResponse)
    assert resp.result == 0

def test_parse_set_freq_error():
    cmd = SetFreq(frequency=14074000)
    resp = parse_response(cmd, "RPRT -11\n")
    assert isinstance(resp, SuccessResponse) # Still returns base success type but with error code
    assert resp.result == -11

def test_parse_get_freq_standard():
    cmd = GetFreq()
    resp = parse_response(cmd, "14074000\n")
    assert isinstance(resp, FreqResponse)
    assert resp.frequency == 14074000
    assert resp.result == 0

def test_parse_get_freq_erp():
    cmd = GetFreq(erp_prefix="+")
    # Our server sends "get_freq: Frequency: {hz}"
    raw = "get_freq: Frequency: 14074000\nRPRT 0\n"
    resp = parse_response(cmd, raw)
    assert isinstance(resp, FreqResponse)
    assert resp.frequency == 14074000
    assert resp.result == 0

def test_parse_get_mode_standard():
    cmd = GetMode()
    resp = parse_response(cmd, "USB\n2400\n")
    assert isinstance(resp, ModeResponse)
    assert resp.mode == "USB"
    assert resp.passband == 2400
    assert resp.result == 0

def test_parse_get_ptt_standard():
    cmd = GetPtt()
    resp = parse_response(cmd, "1\n")
    assert isinstance(resp, PttResponse)
    assert resp.ptt == 1
    assert resp.result == 0

def test_parse_dump_state():
    cmd = DumpState()
    raw = "0\n1\n2\n3\nRPRT 0\n"
    resp = parse_response(cmd, raw)
    assert isinstance(resp, DumpStateResponse)
    assert len(resp.lines) == 4
    assert resp.lines[0] == "0"
    assert resp.result == 0

def test_parse_empty_response():
    cmd = GetFreq()
    resp = parse_response(cmd, "")
    assert resp.result != 0
