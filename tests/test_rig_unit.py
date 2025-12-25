
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from multirig.rig import RigClient, RigctldBackend, RigctlProcessBackend, RigConfig
from multirig.config import BandPreset

@pytest.fixture
def mock_rig_config():
    cfg = MagicMock(spec=RigConfig)
    cfg.connection_type = "rigctld"
    cfg.host = "localhost"
    cfg.port = 4532
    cfg.allow_out_of_band = False
    cfg.band_presets = []
    cfg.enabled = True
    cfg.name = "TestRig"
    cfg.follow_main = True
    cfg.model_id = 123
    cfg.device = "/dev/ttyUSB0"
    cfg.baud = 9600
    cfg.serial_opts = ""
    cfg.extra_args = ""
    cfg.managed = False
    cfg.rigctld_cmd = None
    return cfg

@pytest.fixture
def rig_client(mock_rig_config):
    # Mock _make_backend to avoid side effects during init
    with patch("multirig.rig.RigClient._make_backend") as mock_make:
        mock_backend = AsyncMock()
        mock_make.return_value = mock_backend
        client = RigClient(mock_rig_config)
        client._backend = mock_backend
        return client

@pytest.mark.asyncio
async def test_rig_client_set_frequency_allow_oob(rig_client, mock_rig_config):
    mock_rig_config.allow_out_of_band = True
    mock_rig_config.band_presets = []
    
    rig_client._backend.set_frequency.return_value = True
    
    result = await rig_client.set_frequency(14074000)
    assert result is True
    rig_client._backend.set_frequency.assert_called_with(14074000)

@pytest.mark.asyncio
async def test_rig_client_set_frequency_block_oob(rig_client, mock_rig_config):
    mock_rig_config.allow_out_of_band = False
    p1 = MagicMock(spec=BandPreset)
    p1.enabled = True
    p1.lower_hz = 14000000
    p1.upper_hz = 14350000
    mock_rig_config.band_presets = [p1]
    
    # In band
    rig_client._backend.set_frequency.return_value = True
    result = await rig_client.set_frequency(14074000)
    assert result is True
    rig_client._backend.set_frequency.assert_called_with(14074000)
    
    # Out of band
    rig_client._backend.set_frequency.reset_mock()
    result = await rig_client.set_frequency(7074000)
    assert result is False
    assert rig_client._last_error == "Frequency out of configured band ranges"
    rig_client._backend.set_frequency.assert_not_called()

@pytest.mark.asyncio
async def test_rig_client_set_frequency_no_presets(rig_client, mock_rig_config):
    mock_rig_config.allow_out_of_band = False
    mock_rig_config.band_presets = []
    
    rig_client._backend.set_frequency.return_value = True
    result = await rig_client.set_frequency(14074000)
    assert result is True
    rig_client._backend.set_frequency.assert_called_with(14074000)

@pytest.mark.asyncio
async def test_rig_client_backend_failure(rig_client, mock_rig_config):
    mock_rig_config.allow_out_of_band = True
    rig_client._backend.set_frequency.return_value = False
    
    result = await rig_client.set_frequency(14074000)
    assert result is False
    assert rig_client._last_error == "Failed to set frequency on rig backend"

@pytest.mark.asyncio
async def test_rig_client_factory_hamlib(mock_rig_config):
    mock_rig_config.connection_type = "hamlib"
    mock_rig_config.model_id = 1
    mock_rig_config.device = "/dev/rig"
    
    with patch("multirig.rig.RigctlProcessBackend") as MockBackend:
        client = RigClient(mock_rig_config)
        MockBackend.assert_called_once_with(
            model_id=1,
            device="/dev/rig",
            baud=9600,
            serial_opts="",
            extra_args="",
        )
        assert isinstance(client._backend, MagicMock) # MockBackend instance

@pytest.mark.asyncio
async def test_rig_client_factory_rigctld(mock_rig_config):
    mock_rig_config.connection_type = "rigctld"
    mock_rig_config.host = "1.2.3.4"
    mock_rig_config.port = 1234
    
    with patch("multirig.rig.RigctldBackend") as MockBackend:
        client = RigClient(mock_rig_config)
        MockBackend.assert_called_once_with("1.2.3.4", 1234)
        assert isinstance(client._backend, MagicMock)

# --- RigctldBackend Tests ---

@pytest.mark.asyncio
async def test_rigctld_backend_get_frequency():
    backend = RigctldBackend("localhost", 4532)
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (0, ["14074000"])
        freq = await backend.get_frequency()
        assert freq == 14074000
        mock_send.assert_called_with("f")
        
        # Test error
        mock_send.return_value = (-1, [])
        freq = await backend.get_frequency()
        assert freq is None

@pytest.mark.asyncio
async def test_rigctld_backend_set_frequency():
    backend = RigctldBackend("localhost", 4532)
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (0, [])
        success = await backend.set_frequency(14074000)
        assert success is True
        mock_send.assert_called_with("F 14074000")
        
        mock_send.return_value = (-1, [])
        success = await backend.set_frequency(14074000)
        assert success is False

@pytest.mark.asyncio
async def test_rigctld_backend_get_mode():
    backend = RigctldBackend("localhost", 4532)
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        # Standard format
        mock_send.return_value = (0, ["USB", "2400"])
        mode, pb = await backend.get_mode()
        assert mode == "USB"
        assert pb == 2400
        
        # KV format (Extended)
        mock_send.return_value = (0, ["Mode: USB", "Passband: 2400"])
        mode, pb = await backend.get_mode()
        assert mode == "USB"
        assert pb == 2400

@pytest.mark.asyncio
async def test_rigctld_backend_get_vfo():
    backend = RigctldBackend("localhost", 4532)
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (0, ["VFOA"])
        vfo = await backend.get_vfo()
        assert vfo == "VFOA"

@pytest.mark.asyncio
async def test_rigctld_backend_dump_state():
    backend = RigctldBackend("localhost", 4532)
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = (0, ["dump_state:", "1", "2"])
        lines = await backend.dump_state()
        assert lines == ["1", "2"]

# --- RigctlProcessBackend Tests ---

@pytest.mark.asyncio
async def test_process_backend_get_frequency():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = "14074000"
        freq = await backend.get_frequency()
        assert freq == 14074000
        mock_send.assert_called_with("f")

@pytest.mark.asyncio
async def test_process_backend_set_frequency():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = "RPRT 0"
        success = await backend.set_frequency(14074000)
        assert success is True
        mock_send.assert_called_with("F 14074000")

@pytest.mark.asyncio
async def test_process_backend_get_mode():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send_n", new_callable=AsyncMock) as mock_send_n:
        mock_send_n.return_value = ["USB", "2400"]
        mode, pb = await backend.get_mode()
        assert mode == "USB"
        assert pb == 2400
        
        mock_send_n.return_value = ["USB 2400"]
        mode, pb = await backend.get_mode()
        assert mode == "USB"
        assert pb == 2400

@pytest.mark.asyncio
async def test_process_backend_vfo():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        # set_vfo
        mock_send.return_value = "RPRT 0"
        assert await backend.set_vfo("VFOA") is True
        mock_send.assert_called_with("V VFOA")
        
        # get_vfo
        mock_send.return_value = "VFOA"
        assert await backend.get_vfo() == "VFOA"
        mock_send.assert_called_with("v")
        
        # get_vfo error
        mock_send.return_value = "RPRT -1"
        assert await backend.get_vfo() is None

@pytest.mark.asyncio
async def test_process_backend_ptt():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        # set_ptt
        mock_send.return_value = "RPRT 0"
        assert await backend.set_ptt(1) is True
        mock_send.assert_called_with("T 1")
        
        # get_ptt
        mock_send.return_value = "1"
        assert await backend.get_ptt() == 1
        mock_send.assert_called_with("t")

@pytest.mark.asyncio
async def test_process_backend_extras():
    backend = RigctlProcessBackend(1, "/dev/null")
    with patch.object(backend, "_send", new_callable=AsyncMock) as mock_send:
        # powerstat
        mock_send.return_value = "1"
        assert await backend.get_powerstat() == 1
        mock_send.assert_called_with("\\get_powerstat")
        
        # chk_vfo
        mock_send.return_value = "1"
        assert await backend.chk_vfo() == 1
        mock_send.assert_called_with("\\chk_vfo")

@pytest.mark.asyncio
async def test_rig_client_passthrough_errors(rig_client):
    rig_client._backend.set_vfo.return_value = False
    assert await rig_client.set_vfo("VFOA") is False
    assert rig_client._last_error == "Failed to set VFO on rig backend"
    
    rig_client._backend.set_ptt.return_value = False
    assert await rig_client.set_ptt(1) is False
    assert rig_client._last_error == "Failed to set PTT on rig backend"
    
    rig_client._backend.set_mode.return_value = False
    assert await rig_client.set_mode("USB") is False
    assert rig_client._last_error == "Failed to set mode on rig backend"

@pytest.mark.asyncio
async def test_rig_client_status(rig_client):
    rig_client._backend.status = AsyncMock(return_value="StatusOK")
    st = await rig_client.status()
    assert st == "StatusOK"
    
import multirig.rig as rig_mod

def test_parse_helpers():
    # _parse_bool_flag
    assert rig_mod._parse_bool_flag("Y") is True
    assert rig_mod._parse_bool_flag("E") is True
    assert rig_mod._parse_bool_flag("N") is False
    assert rig_mod._parse_bool_flag("") is False
    assert rig_mod._parse_bool_flag(None) is False
    
    # _parse_mode_list
    assert rig_mod._parse_mode_list("") == []
    assert rig_mod._parse_mode_list("None") == []
    assert rig_mod._parse_mode_list("USB LSB") == ["USB", "LSB"]
    assert rig_mod._parse_mode_list("USB, LSB;") == ["USB", "LSB"]
    assert rig_mod._parse_mode_list("USB .") == ["USB"] # Filter trailing dot?
    
    # parse_dump_caps
    caps, modes = rig_mod.parse_dump_caps("")
    assert caps == {}
    assert modes == []
    
    txt = """
    Can set Frequency: Y
    Can get Frequency: Y
    Mode list: USB LSB
    """
    caps, modes = rig_mod.parse_dump_caps(txt)
    assert caps["freq_set"] is True
    assert caps["freq_get"] is True
    assert "USB" in modes
    assert "LSB" in modes

@pytest.mark.asyncio
async def test_rig_backend_base():
    # Test base class NotImplementedErrors
    base = rig_mod.RigBackend()
    
    with pytest.raises(NotImplementedError):
        await base.get_frequency()
    with pytest.raises(NotImplementedError):
        await base.set_frequency(100)
    with pytest.raises(NotImplementedError):
        await base.get_mode()
    with pytest.raises(NotImplementedError):
        await base.set_mode("USB")
    with pytest.raises(NotImplementedError):
        await base.get_vfo()
    with pytest.raises(NotImplementedError):
        await base.set_vfo("VFOA")
    with pytest.raises(NotImplementedError):
        await base.get_ptt()
    with pytest.raises(NotImplementedError):
        await base.set_ptt(1)
    with pytest.raises(NotImplementedError):
        await base.get_powerstat()
    with pytest.raises(NotImplementedError):
        await base.chk_vfo()
    with pytest.raises(NotImplementedError):
        await base.dump_state()
    with pytest.raises(NotImplementedError):
        await base.dump_caps()
    with pytest.raises(NotImplementedError):
        await base.status()
    
    assert await base.close() is None

@pytest.mark.asyncio
async def test_process_backend_dump():
    backend = RigctlProcessBackend(1, "/dev/null")
    
    # Test dump_state with timeout simulation
    # We mock stdout.readline to return lines then pause
    mock_proc = AsyncMock()
    mock_proc.stdin.write = MagicMock()
    mock_proc.stdin.close = MagicMock()
    mock_proc.stdin.drain = AsyncMock()
    mock_proc.returncode = None
    
    # Simulate lines then a timeout (to break the loop)
    mock_proc.stdout.readline.side_effect = [b"Line1\n", b"Line2\n", b""] 
    
    with patch("multirig.rig.asp.create_subprocess_exec", return_value=mock_proc):
         lines = await backend.dump_state()
         assert lines == ["Line1", "Line2"]
         mock_proc.stdin.write.assert_called_with(b"\\dump_state\n")
    
    # Test dump_caps
    mock_proc.stdout.readline.side_effect = [b"Cap1\n", b""]
    with patch("multirig.rig.asp.create_subprocess_exec", return_value=mock_proc):
         lines = await backend.dump_caps()
         assert lines == ["Cap1"]
         mock_proc.stdin.write.assert_called_with(b"\\dump_caps\n")

@pytest.mark.asyncio
async def test_process_backend_build_cmd():
    # Test command building with all options
    backend = RigctlProcessBackend(
        model_id=123, 
        device="/dev/rig",
        baud=9600,
        serial_opts="dst=33",
        extra_args="-v"
    )
    cmd = backend._build_cmd()
    expected = ["rigctl", "-m", "123", "-r", "/dev/rig", 
                "-s", "9600", "dst=33", "-v"] # shlex.split behavior
    assert cmd == expected

@pytest.mark.asyncio
async def test_process_backend_send_n_retry():
    # Test _send_n (used by get_mode) retry logic
    backend = RigctlProcessBackend(1, "/dev/null")
    
    mock_proc1 = AsyncMock()
    mock_proc1.stdin.write = MagicMock(side_effect=BrokenPipeError()) # Fail 1
    mock_proc1.stdin.close = MagicMock()
    mock_proc1.stdin.drain = AsyncMock()
    mock_proc1.returncode = None
    
    mock_proc2 = AsyncMock()
    mock_proc2.stdin.write = MagicMock()
    mock_proc2.stdin.close = MagicMock()
    mock_proc2.stdin.drain = AsyncMock()
    mock_proc2.stdout.readline.side_effect = [b"USB\n", b"2400\n"] # Success 2
    mock_proc2.returncode = None
    
    with patch("multirig.rig.asp.create_subprocess_exec", side_effect=[mock_proc1, mock_proc2]):
         # get_mode calls _send_n("m", 2)
         mode, pb = await backend.get_mode()
         assert mode == "USB"
         assert pb == 2400
         # Should have tried twice

def test_rigctl_error():
    e = rig_mod.RigctlError(1, "ErrorMsg")
    assert str(e) == "RPRT 1: ErrorMsg"
    assert e.code == 1
    
    e2 = rig_mod.RigctlError(2)
    assert str(e2) == "RPRT 2"

