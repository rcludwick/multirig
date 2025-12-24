import pytest
from unittest.mock import MagicMock, AsyncMock
from multirig.rigctl_tcp import RigctlServer, RigctlServerConfig
from multirig.rig import RigClient, RigConfig

@pytest.fixture
def mock_rig():
    cfg = RigConfig(name="TestRig", connection_type="rigctld", host="1.2.3.4", port=4532)
    rig = RigClient(cfg)
    # Mock the backend
    rig._backend = AsyncMock()
    rig._backend.close = AsyncMock()
    return rig

@pytest.fixture
def server(mock_rig):
    rigs = [mock_rig]
    
    class TestRigctlServer(RigctlServer):
        def get_rigs(self):
            return rigs
        def get_source_index(self):
            return 0
            
    srv = TestRigctlServer(
        config=RigctlServerConfig(host="127.0.0.1", port=4534)
    )
    return srv

@pytest.mark.asyncio
async def test_dump_caps_forwarding(server, mock_rig):
    # Setup mock response
    caps_data = "Model Name: Test Rig\nHas PTT: Yes\n"
    mock_rig._backend.dump_caps.return_value = caps_data.splitlines()

    # Test standard command
    resp = await server._handle_command_line("dump_caps")
    assert resp == b"Model Name: Test Rig\nHas PTT: Yes\n"
    mock_rig._backend.dump_caps.assert_called()

    # Test extended command (ERP)
    mock_rig._backend.dump_caps.reset_mock()
    resp_erp = await server._handle_command_line("+dump_caps")
    # Extended response format: dump_caps:\n<lines>\nRPRT 0\n
    expected_erp = b"dump_caps:\nModel Name: Test Rig\nHas PTT: Yes\nRPRT 0\n"
    assert resp_erp == expected_erp

@pytest.mark.asyncio
async def test_chk_vfo_forwarding(server, mock_rig):
    # Setup mock response "0" (meaning new VFO is same as old, usually)
    mock_rig._backend.chk_vfo.return_value = "0"
    
    # Test standard command
    resp = await server._handle_command_line("chk_vfo")
    assert resp == b"CHKVFO 0\n"
    mock_rig._backend.chk_vfo.assert_called()

    # Test raw command (backshlash prefix)
    mock_rig._backend.chk_vfo.reset_mock()
    resp_raw = await server._handle_command_line("\\chk_vfo")
    # Raw response: 0\n
    expected_raw = b"0\n"
    assert resp_raw == expected_raw

    # Test extended command (ERP)
    mock_rig._backend.chk_vfo.reset_mock()
    resp_erp = await server._handle_command_line("+chk_vfo")
    # Extended response: chk_vfo: 0\nRPRT 0\n
    expected_erp = b"chk_vfo: 0\nRPRT 0\n"
    assert resp_erp == expected_erp

@pytest.mark.asyncio
async def test_dump_caps_failure(server, mock_rig):
    mock_rig._backend.dump_caps.return_value = None
    resp = await server._handle_command_line("dump_caps")
    # Standard failure usually RPRT -1 or similar
    assert resp == b"RPRT -1\n"
