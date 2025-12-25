
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from multirig.rigctl_tcp import (
    RigctlServer, 
    _default_server_config, 
    _is_erp_prefix, 
    _records_to_bytes,
    RigctlServerConfig
)

class ConcreteRigctlServer(RigctlServer):
    def __init__(self, port=0):
        super().__init__(RigctlServerConfig(host="127.0.0.1", port=port))

    def get_rigs(self):
        return []

@pytest.mark.asyncio
async def test_helpers():
    # _default_server_config
    cfg = _default_server_config()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 4534
    
    # _is_erp_prefix
    assert _is_erp_prefix("") is False
    assert _is_erp_prefix("A") is False
    assert _is_erp_prefix(" ") is False
    assert _is_erp_prefix("\\") is False
    assert _is_erp_prefix("+") is True
    
    # _records_to_bytes (sep != \n)
    assert _records_to_bytes(["a", "b"], "|") == b"a|b|"

@pytest.mark.asyncio
async def test_server_base_methods():
    server = ConcreteRigctlServer()
    
    # Default methods
    assert server.get_source_index() == 0
    assert server.get_rigctl_to_main_enabled() is True
    assert server.get_sync_enabled() is True
    
    # _source_rig empty
    assert server._source_rig() is None
    
    # Mock rigs for _source_rig
    mock_rig = MagicMock()
    server.get_rigs = MagicMock(return_value=[mock_rig])
    
    # valid index
    server.get_source_index = MagicMock(return_value=0)
    assert server._source_rig() == mock_rig
    
    # invalid index
    server.get_source_index = MagicMock(return_value=99)
    assert server._source_rig() is None

@pytest.mark.asyncio
async def test_server_lifecycle():
    server = ConcreteRigctlServer()
    server._handle_client = AsyncMock()
    
    # Start
    await server.start()
    assert server._server is not None
    s1 = server._server
    
    # Start again (should be no-op)
    await server.start()
    assert server._server is s1
    
    # Stop
    await server.stop()
    assert server._server is None
    
    # Stop again (no-op)
    await server.stop()

@pytest.mark.asyncio
async def test_handle_command_line_edge_cases():
    server = ConcreteRigctlServer()
    server.get_rigs = MagicMock(return_value=[])
    
    # Empty cmd
    assert await server._handle_command_line("") == b""
    assert await server._handle_command_line("   ") == b""
    
    # chk_vfo dispatch
    # Mock _cmd_chk_vfo
    server._cmd_chk_vfo = AsyncMock(return_value=b"chk_vfo_resp")
    
    # Standard call (not raw) - typically chk_vfo is internal or via correct dispatch?
    # Logic: if cmd_key == "chk_vfo": return await self._cmd_chk_vfo
    # But cmd_key defaults to cmd.
    assert await server._handle_command_line("chk_vfo 1") == b"chk_vfo_resp"
    server._cmd_chk_vfo.assert_called_with(None, False)
    
    # Raw call
    assert await server._handle_command_line("\\chk_vfo") == b"chk_vfo_resp"
    server._cmd_chk_vfo.assert_called_with(None, True)

@pytest.mark.asyncio
async def test_abstract_methods_raise():
    # Base class direct instantiation (if possible or via subclass super calls)
    # RigctlServer inherits BaseTcpServer
    # BaseTcpServer._handle_client raises NotImplementedError
    
    from multirig.rigctl_tcp import BaseTcpServer
    base = BaseTcpServer("h", 1)
    with pytest.raises(NotImplementedError):
        await base._handle_client(None, None)
        
    s = RigctlServer()
    with pytest.raises(NotImplementedError):
        s.get_rigs()

@pytest.mark.asyncio
async def test_cmd_handlers_error_paths():
    server = ConcreteRigctlServer()
    # No rigs
    server.get_rigs = MagicMock(return_value=[])
    
    # set_freq errors
    assert await server._cmd_set_freq([], None) == b"RPRT -1\n"
    assert await server._cmd_set_freq(["bad"], None) == b"RPRT -1\n"
    assert await server._cmd_set_freq(["14000000"], None) == b"RPRT -11\n" # No rigs
    
    # get_freq errors
    # (get_freq checks source rig -> -1)
    assert await server._cmd_get_freq([], None) == b"RPRT -1\n"

    # set_mode errors
    # (set_mode checks get_rigs -> -11)
    assert await server._cmd_set_mode([], None) == b"RPRT -1\n"
    assert await server._cmd_set_mode(["USB"], None) == b"RPRT -11\n" # Missing bandwidth (rig check first)
    assert await server._cmd_set_mode(["USB", "bad"], None) == b"RPRT -11\n" # Bad bandwidth (rig check first)
    assert await server._cmd_set_mode(["USB", "2400"], None) == b"RPRT -11\n" # No rigs

    # get_mode errors
    # (get_mode checks source rig -> -1)
    assert await server._cmd_get_mode([], None) == b"RPRT -1\n"
    
    # set_vfo errors
    assert await server._cmd_set_vfo([], None) == b"RPRT -1\n" 
    assert await server._cmd_set_vfo(["VFOA"], None) == b"RPRT -11\n"

    # get_vfo errors
    assert await server._cmd_get_vfo([], None) == b"RPRT -1\n"

    # set_ptt errors
    assert await server._cmd_set_ptt([], None) == b"RPRT -1\n"
    assert await server._cmd_set_ptt(["bad"], None) == b"RPRT -1\n"
    assert await server._cmd_set_ptt(["1"], None) == b"RPRT -11\n"

    # get_ptt errors
    assert await server._cmd_get_ptt([], None) == b"RPRT -1\n"

@pytest.mark.asyncio
async def test_handle_client_loop():
    server = ConcreteRigctlServer()
    server._handle_command_line = AsyncMock(return_value=b"OK\n")
    
    reader = AsyncMock()
    writer = MagicMock()
    writer.drain = AsyncMock()
    
    # Simulate: line 1, line 2, empty bytes (EOF)
    reader.readline.side_effect = [b"freq\n", b"quit\n"]
    
    await server._handle_client(reader, writer)
    
    assert server._handle_command_line.call_count >= 1
    writer.close.assert_called()
    
    # Test error in wait_closed
    writer.wait_closed = AsyncMock(side_effect=Exception("ignore"))
    reader.readline.side_effect = [b"quit\n"]
    await server._handle_client(reader, writer) # Should not raise
