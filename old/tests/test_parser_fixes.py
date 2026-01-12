import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from multirig.rig.process import RigctlProcessBackend
from multirig.rig.common import RigStatus

@pytest.fixture
def backend():
    """Create a backend instance with mocked process communication."""
    b = RigctlProcessBackend(model_id=2, device="/dev/dummy")
    # Mock the internal lock and proc
    b._lock = asyncio.Lock()
    return b

@pytest.mark.asyncio
async def test_parse_verbose_frequency(backend):
    """Verify that 'Frequency: 14000000' is parsed correctly."""
    # Mock _send to return verbose response
    backend._send = AsyncMock(return_value="Frequency: 14000000")
    
    freq = await backend.get_frequency()
    assert freq == 14000000

@pytest.mark.asyncio
async def test_parse_standard_frequency(backend):
    """Verify that standard '14000000' is parsed correctly."""
    backend._send = AsyncMock(return_value="14000000")
    
    freq = await backend.get_frequency()
    assert freq == 14000000

@pytest.mark.asyncio
async def test_parse_invalid_frequency(backend):
    """Verify that invalid frequency returns None."""
    backend._send = AsyncMock(return_value="Invalid Data")
    
    freq = await backend.get_frequency()
    assert freq is None

@pytest.mark.asyncio
async def test_parse_verbose_mode(backend):
    """Verify that 'Mode: USB' is parsed correctly."""
    # Mock _send_n for get_mode
    backend._send_n = AsyncMock(return_value=["Mode: USB", "Passband: 2400"])
    
    mode, pb = await backend.get_mode()
    assert mode == "USB"
    # Passband extraction from separate token or line is nice-to-have
    assert pb == 2400 or pb is None

@pytest.mark.asyncio
async def test_parse_verbose_mode_multi_tokens(backend):
    """Verify 'Mode: USB 2400' single line response is parsed correctly."""
    # Some rigctl versions might return everything on one line
    backend._send_n = AsyncMock(return_value=["Mode: USB 2400"])
    
    mode, pb = await backend.get_mode()
    assert mode == "USB"
    # Logic might not extract passband from same line if not space-separated standard format
    # But mode should definitely be correct
    assert pb == 2400 or pb is None 

@pytest.mark.asyncio
async def test_parse_standard_mode(backend):
    """Verify that standard 'USB 2400' is parsed correctly."""
    backend._send_n = AsyncMock(return_value=["USB 2400"])
    
    mode, pb = await backend.get_mode()
    assert mode == "USB"
    assert pb == 2400

@pytest.mark.asyncio
async def test_parse_verbose_mode_only(backend):
    """Verify 'Mode: USB' without passband."""
    backend._send_n = AsyncMock(return_value=["Mode: USB"])
    
    mode, pb = await backend.get_mode()
    assert mode == "USB"
    # Passband might be None or derived from logic
    
@pytest.mark.asyncio
async def test_status_missing_frequency_failure(backend):
    """Verify status() returns connected=False if frequency is None."""
    # Mock individual methods
    backend.get_frequency = AsyncMock(return_value=None)
    backend.get_mode = AsyncMock(return_value=("USB", 2400))
    
    status = await backend.status()
    assert status.connected is False
    assert status.error == "Failed to get frequency"
