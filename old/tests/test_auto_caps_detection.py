"""Unit tests for automatic capability detection on rig connection."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from multirig.rig import RigClient, RigStatus
from multirig.config import RigConfig


@pytest.fixture
def mock_rigctld_config():
    """Create a mock rigctld configuration."""
    return RigConfig(
        name="Test Rig",
        connection_type="rigctld",
        host="127.0.0.1",
        port=4532,
        poll_interval_ms=1000,
        band_presets=[],
        allow_out_of_band=False,
    )


@pytest.fixture
def mock_dump_caps_output():
    """Mock dump_caps output from a typical rig."""
    return [
        "Caps dump for model: 2",
        "Model name: Dummy",
        "Mfg name: Hamlib",
        "Backend version: 20191231.0",
        "Can get Frequency: Y",
        "Can set Frequency: Y",
        "Can get Mode: Y",
        "Can set Mode: Y",
        "Can get VFO: Y",
        "Can set VFO: Y",
        "Can get PTT: Y",
        "Can set PTT: Y",
        "Mode list: USB LSB CW AM FM",
    ]


@pytest.mark.anyio
async def test_refresh_caps_parses_and_caches_capabilities(mock_rigctld_config, mock_dump_caps_output):
    """Test that refresh_caps parses dump_caps output and caches capabilities."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the dump_caps method
    rig._backend.dump_caps = AsyncMock(return_value=mock_dump_caps_output)
    rig._backend.close = MagicMock()
    
    # Call refresh_caps
    result = await rig.refresh_caps()
    
    # Verify the result structure
    assert "caps" in result
    assert "modes" in result
    assert "raw" in result
    
    # Verify capabilities were parsed correctly
    assert result["caps"]["freq_get"] is True
    assert result["caps"]["freq_set"] is True
    assert result["caps"]["mode_get"] is True
    assert result["caps"]["mode_set"] is True
    assert result["caps"]["vfo_get"] is True
    assert result["caps"]["vfo_set"] is True
    assert result["caps"]["ptt_get"] is True
    assert result["caps"]["ptt_set"] is True
    
    # Verify modes were parsed correctly
    assert "USB" in result["modes"]
    assert "LSB" in result["modes"]
    assert "CW" in result["modes"]
    assert "AM" in result["modes"]
    assert "FM" in result["modes"]
    
    # Verify capabilities are cached in the rig instance
    assert rig._caps == result["caps"]
    assert rig._modes == result["modes"]


@pytest.mark.anyio
async def test_refresh_caps_on_first_successful_status(mock_rigctld_config, mock_dump_caps_output):
    """Test that capabilities are automatically refreshed on first successful connection."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the backend methods
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    rig._backend.dump_caps = AsyncMock(return_value=mock_dump_caps_output)
    
    # Initially, capabilities should be None
    assert rig._caps is None
    assert rig._modes is None
    assert rig._caps_detected is False
    
    # Simulate the first status check that triggers capability detection
    await rig.check_and_refresh_caps()
    
    # Verify capabilities were detected
    assert rig._caps is not None
    assert rig._modes is not None
    assert rig._caps_detected is True
    assert rig._caps["freq_get"] is True
    assert "USB" in rig._modes


@pytest.mark.anyio
async def test_caps_not_refreshed_on_disconnected_rig(mock_rigctld_config):
    """Test that capabilities are not refreshed when rig is disconnected."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the backend to return disconnected status
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=False,
        error="Connection refused"
    ))
    rig._backend.dump_caps = AsyncMock()
    
    # Attempt to check and refresh caps
    await rig.check_and_refresh_caps()
    
    # Verify dump_caps was not called
    rig._backend.dump_caps.assert_not_called()
    
    # Verify capabilities remain None
    assert rig._caps is None
    assert rig._modes is None
    assert rig._caps_detected is False


@pytest.mark.anyio
async def test_caps_only_refreshed_once_on_connection(mock_rigctld_config, mock_dump_caps_output):
    """Test that capabilities are only refreshed once, not on every status check."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the backend methods
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    rig._backend.dump_caps = AsyncMock(return_value=mock_dump_caps_output)
    
    # First call should trigger capability detection
    await rig.check_and_refresh_caps()
    assert rig._backend.dump_caps.call_count == 1
    
    # Subsequent calls should not trigger capability detection
    await rig.check_and_refresh_caps()
    await rig.check_and_refresh_caps()
    assert rig._backend.dump_caps.call_count == 1


@pytest.mark.anyio
async def test_caps_refreshed_after_reconnection(mock_rigctld_config, mock_dump_caps_output):
    """Test that capabilities are refreshed again after a disconnection and reconnection."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock initial connected status
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    rig._backend.dump_caps = AsyncMock(return_value=mock_dump_caps_output)
    
    # First connection - should detect caps
    await rig.check_and_refresh_caps()
    assert rig._backend.dump_caps.call_count == 1
    assert rig._caps_detected is True
    
    # Simulate disconnection
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=False,
        error="Connection lost"
    ))
    # Invalidate cache to ensure fresh status fetch
    rig._cached_status = None
    
    await rig.check_and_refresh_caps()
    
    # The disconnection should reset the caps_detected flag
    assert rig._caps_detected is False
    
    # Simulate reconnection
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    
    # Should detect caps again after reconnection
    await rig.check_and_refresh_caps()
    assert rig._backend.dump_caps.call_count == 2
    assert rig._caps_detected is True


@pytest.mark.anyio
async def test_safe_status_includes_detected_capabilities(mock_rigctld_config, mock_dump_caps_output):
    """Test that safe_status includes the detected capabilities."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the backend methods
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    rig._backend.dump_caps = AsyncMock(return_value=mock_dump_caps_output)
    
    # Detect capabilities
    await rig.check_and_refresh_caps()
    
    # Get safe status
    status = await rig.safe_status()
    
    # Verify capabilities are included
    assert "caps" in status
    assert status["caps"] is not None
    assert status["caps"]["freq_get"] is True
    assert "modes" in status
    assert "USB" in status["modes"]


@pytest.mark.anyio
async def test_caps_detection_handles_dump_caps_failure(mock_rigctld_config):
    """Test that capability detection handles dump_caps failures gracefully."""
    rig = RigClient(mock_rigctld_config)
    
    # Mock the backend to raise an exception on dump_caps
    rig._backend.status = AsyncMock(return_value=RigStatus(
        connected=True,
        frequency_hz=14074000,
        mode="USB",
        passband=2400
    ))
    rig._backend.dump_caps = AsyncMock(side_effect=Exception("dump_caps failed"))
    
    # Attempt to check and refresh caps - should not raise
    await rig.check_and_refresh_caps()
    
    # Verify capabilities remain None but detection was attempted
    assert rig._caps is None
    assert rig._modes is None
    # Even though it failed, we mark it as detected to avoid repeated failures
    assert rig._caps_detected is True
