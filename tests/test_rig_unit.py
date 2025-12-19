
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

