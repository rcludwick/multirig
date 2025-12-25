import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from multirig.rig import RigctldBackend, RigctlProcessBackend, RigBackend

# --- RigctldBackend Tests ---

@pytest.fixture
def rigctld_backend():
    return RigctldBackend(host="127.0.0.1", port=4532)

@pytest.mark.asyncio
async def test_rigctld_send_raw_success(rigctld_backend):
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    # Mock readline to return the response
    mock_reader.readline.side_effect = [b"RPRT 0\n", b""] # Response then EOF? Or just RPRT 0 is enough logic to break
    
    with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)) as mock_open:
        code, lines = await rigctld_backend._send_raw("test_cmd")
        
        mock_open.assert_called_with("127.0.0.1", 4532)
        mock_writer.write.assert_called_with(b"test_cmd\n")
        assert code == 0
        assert lines == [] 

@pytest.mark.asyncio
async def test_rigctld_send_raw_data(rigctld_backend):
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    # Returns data then RPRT 0
    mock_reader.readline.side_effect = [b"Line1\n", b"Line2\n", b"RPRT 0\n"]
    
    with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
        code, lines = await rigctld_backend._send_raw("test_cmd")
        assert code == 0
        assert lines == ["Line1", "Line2"]

@pytest.mark.asyncio
async def test_rigctld_connect_failure(rigctld_backend):
    with patch("asyncio.open_connection", side_effect=OSError("Refused")):
        with pytest.raises(ConnectionError):
            await rigctld_backend._send_raw("test_cmd")

@pytest.mark.asyncio
async def test_rigctld_send_erp_success(rigctld_backend):
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()
    mock_writer.write = MagicMock()
    mock_writer.close = MagicMock()
    mock_writer.wait_closed = AsyncMock()
    
    # RPRT 0 response
    mock_reader.readline.side_effect = [b"RPRT 0\n", b""]
    
    with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
        code, lines = await rigctld_backend._send_erp("valid_cmd")
        assert code == 0
        mock_writer.write.assert_called_with(b"+valid_cmd\n") # ERP prefix +

@pytest.mark.asyncio
async def test_rigctld_send_fallback(rigctld_backend):
    # To trigger fallback: _send_erp must return non-zero code, and _send_raw must return 0.
    
    rigctld_backend._erp_supported = True
    
    with patch.object(rigctld_backend, "_send_erp", new_callable=AsyncMock) as mock_erp:
        with patch.object(rigctld_backend, "_send_raw", new_callable=AsyncMock) as mock_raw:
             mock_erp.return_value = (-1, [])
             mock_raw.return_value = (0, ["RawResp"])
             
             code, lines = await rigctld_backend._send("cmd")
             
             assert code == 0
             assert lines == ["RawResp"]
             assert rigctld_backend._erp_supported is False
             
             # Next call should skip erp
             mock_erp.reset_mock()
             await rigctld_backend._send("cmd2")
             mock_erp.assert_not_called()
             mock_raw.assert_called_with("cmd2", timeout=1.5)

@pytest.mark.asyncio
async def test_rigctld_methods(rigctld_backend):
    # Mock _send to avoid networking logic in high-level tests
    with patch.object(rigctld_backend, "_send", new_callable=AsyncMock) as mock_send:
        # get_frequency
        mock_send.return_value = (0, ["Frequency: 14000"])
        freq = await rigctld_backend.get_frequency()
        assert freq == 14000
        
        # set_frequency
        mock_send.return_value = (0, [])
        ret = await rigctld_backend.set_frequency(14200)
        assert ret is True
        mock_send.assert_called_with("F 14200")

# --- RigctlProcessBackend Tests ---

@pytest.fixture
def process_backend():
    return RigctlProcessBackend(model_id=2, device="/dev/dummy")

@pytest.mark.asyncio
async def test_process_ensure_proc(process_backend):
    mock_proc = AsyncMock()
    mock_proc.returncode = None
    
    # Patch the reference used in the module
    with patch("multirig.rig.process.asp.create_subprocess_exec", return_value=mock_proc) as mock_exec:
        proc = await process_backend._ensure_proc()
        assert proc is mock_proc
        mock_exec.assert_called()
        
        # Second call returns same proc
        proc2 = await process_backend._ensure_proc()
        assert proc2 is proc
        assert mock_exec.call_count == 1

@pytest.mark.asyncio
async def test_process_send(process_backend):
    mock_proc = AsyncMock()
    # stdin.write is sync
    mock_proc.stdin.write = MagicMock()
    mock_proc.stdin.close = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.stdout.readline.return_value = b"RPRT 0\n"
    mock_proc.returncode = None
    
    with patch("multirig.rig.process.asp.create_subprocess_exec", return_value=mock_proc):
        # We need to ensure proc is created
        resp = await process_backend._send("chk_vfo")
        assert resp == "RPRT 0"
        mock_proc.stdin.write.assert_called_with(b"chk_vfo\n")

@pytest.mark.asyncio
async def test_process_restart_on_failure(process_backend):
    mock_proc1 = AsyncMock()
    mock_proc1.stdin.write = MagicMock(side_effect=BrokenPipeError())
    mock_proc1.stdin.close = MagicMock()
    mock_proc1.stdin.drain = AsyncMock()
    mock_proc1.returncode = None # Initially alive
    
    mock_proc2 = AsyncMock()
    mock_proc2.stdin.write = MagicMock()
    mock_proc2.stdin.close = MagicMock()
    mock_proc2.stdin.drain = AsyncMock()
    mock_proc2.stdout.readline.return_value = b"RESTARTED\n"
    mock_proc2.returncode = None
    
    with patch("multirig.rig.process.asp.create_subprocess_exec", side_effect=[mock_proc1, mock_proc2]) as mock_exec:
        # First call fails on write, triggers restart
        resp = await process_backend._send("cmd")
        assert resp == "RESTARTED"
        assert mock_exec.call_count == 2
