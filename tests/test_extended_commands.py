import pytest
from unittest.mock import AsyncMock
from multirig.rigctl_tcp import RigctlServer, RigctlServerConfig
from multirig.rig import RigClient, RigConfig

@pytest.fixture
def mock_rig():
    cfg = RigConfig(name="TestRig", connection_type="rigctld", host="1.2.3.4", port=4532)
    rig = RigClient(cfg)
    rig._backend = AsyncMock()
    rig.get_powerstat = AsyncMock(return_value=1)
    rig.chk_vfo = AsyncMock(return_value=0)
    return rig

@pytest.fixture
def server(mock_rig):
    return RigctlServer(
        get_rigs=lambda: [mock_rig],
        get_source_index=lambda: 0,
        config=RigctlServerConfig(host="127.0.0.1", port=4534)
    )

@pytest.mark.asyncio
async def test_get_powerstat(server, mock_rig):
    # Client sends: \get_powerstat
    resp = await server._handle_command_line(r"\get_powerstat")
    assert resp == b"1\n"
    mock_rig.get_powerstat.assert_called_with()

    # Client sends: +\get_powerstat (ERP)
    resp_erp = await server._handle_command_line(r"+\get_powerstat")
    expected_erp = b"get_powerstat:\nPower Status: 1\nRPRT 0\n"
    assert resp_erp == expected_erp

@pytest.mark.asyncio
async def test_chk_vfo(server, mock_rig):
    # Client sends: \chk_vfo
    resp = await server._handle_command_line(r"\chk_vfo")
    assert resp == b"0\n"
    mock_rig.chk_vfo.assert_called_with()

    # Client sends: chk_vfo (Standard command?)
    resp_std = await server._handle_command_line("chk_vfo")
    assert resp_std == b"CHKVFO 0\n"

    # Client sends: +\chk_vfo (ERP)
    resp_erp = await server._handle_command_line(r"+\chk_vfo")
    expected_erp = b"chk_vfo: 0\nRPRT 0\n"
    assert resp_erp == expected_erp

@pytest.mark.asyncio
async def test_dump_state_extended(server, mock_rig):
    mock_rig.dump_state = AsyncMock(return_value=["Line1", "Line2"])
    
    # Client sends: \dump_state
    resp = await server._handle_command_line(r"\dump_state")
    assert resp == b"Line1\nLine2\n"
    
    # Client sends: +\dump_state
    resp_erp = await server._handle_command_line(r"+\dump_state")
    expected_erp = b"dump_state:\nLine1\nLine2\nRPRT 0\n"
    assert resp_erp == expected_erp
