import pytest
from unittest.mock import AsyncMock
from multirig.rigctl_tcp import RigctlTcpServer, RigctlServerConfig, _sep_for_erp
from multirig.rig import RigClient, RigConfig

@pytest.mark.asyncio
async def test_dump_state_command():
    # Mock dependencies
    cfg = RigConfig(name="TestRig", connection_type="rigctld", host="1.2.3.4", port=4532)
    mock_rig = RigClient(cfg)
    mock_rig._backend = AsyncMock()
    mock_rig._backend.close = AsyncMock()
    mock_rig.dump_state = AsyncMock(return_value=["Some State"])

    rigs = [mock_rig]
    server = RigctlTcpServer(
        get_rigs=lambda: rigs,
        get_source_index=lambda: 0,
        config=RigctlServerConfig(host="127.0.0.1", port=4534)
    )

    # Test standard command (no ERP)
    resp = await server._handle_command_line("dump_state")
    assert resp == b"Some State\n"

    # Test with ERP prefix (e.g., +dump_state)
    resp_erp = await server._handle_command_line("+dump_state")
    expected_erp = b"dump_state:\nSome State\nRPRT 0\n"
    assert resp_erp == expected_erp
    
    # Test raw mode
    resp_raw = await server._handle_command_line("\\dump_state")
    assert resp_raw == b"Some State\n"
