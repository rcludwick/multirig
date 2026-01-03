import pytest
from playwright.sync_api import Page, expect
import time
from multirig.app import create_app
from multirig.config import AppConfig, RigConfig
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from multirig.rig.common import RigStatus

def test_rig_polling_rate_caching(monkeypatch, tmp_path):
    """Verify that RigClient.status() caches results and respects poll_interval_ms."""
    import multirig.core as coremod
    from multirig.rig.common import RigStatus

    # Mock backend to count calls
    class MockBackend:
        def __init__(self):
            self.status_calls = 0
        
        async def status(self):
            self.status_calls += 1
            return RigStatus(connected=True, frequency_hz=14000000, mode="USB")

        async def close(self): pass

    mock_backend = MockBackend()

    # Mock RigClient to use our specific backend but real caching logic
    from multirig.rig.client import RigClient

    # We can't easily mock just the backend creation inside RigClient without refactoring,
    # so we'll instantiate RigClient and swap the backend.
    
    cfg = RigConfig(name="Test", poll_interval_ms=200) # 200ms cache
    client = RigClient(cfg)
    client._backend = mock_backend

    import asyncio

    async def run_test():
        # First call, should hit backend
        await client.status()
        assert mock_backend.status_calls == 1

        # Immediate follow-up (10ms later), should cache hit
        time.sleep(0.01)
        await client.status()
        assert mock_backend.status_calls == 1

        # Wait for TTL to expire (250ms > 200ms)
        time.sleep(0.25)
        await client.status()
        assert mock_backend.status_calls == 2

    asyncio.run(run_test())

class DummyRigStatus:
    def __init__(self, *, connected=True, frequency_hz=None, mode=None, passband=None):
        self.connected = connected
        self.frequency_hz = frequency_hz
        self.mode = mode
        self.passband = passband
        self.error = None

class DummyRigClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self._status = DummyRigStatus(connected=True, frequency_hz=14074000)
    async def status(self): return self._status
    async def safe_status(self): return {"name": self.cfg.name, "enabled": True}
    async def close(self): pass

class DummySyncService:
    def __init__(self, rigs, interval_ms=750, *, enabled=True, source_index=0):
        self.rigs = rigs
        self.interval_ms = interval_ms
        self.enabled = enabled
        self.source_index = source_index
    async def start(self): pass
    async def stop(self): pass

class DummyRigctlServer:
    def __init__(self, *args, **kwargs):
        self._host = "127.0.0.1"
        self._port = 4534
    async def start(self): pass
    async def stop(self): pass

@pytest.fixture
def client(monkeypatch, tmp_path):
    import multirig.app as appmod
    import multirig.core as coremod
    
    cfg = AppConfig(poll_interval_ms=5000)
    monkeypatch.setattr(appmod, "load_config", lambda path: cfg)
    monkeypatch.setattr(appmod, "save_config", lambda cfg, path: None)
    monkeypatch.setattr(coremod, "RigClient", DummyRigClient)
    monkeypatch.setattr(appmod, "RigClient", DummyRigClient)
    monkeypatch.setattr(appmod, "SyncService", DummySyncService)
    monkeypatch.setattr(appmod, "AppRigctlServer", DummyRigctlServer)

    app = appmod.create_app(config_path=tmp_path / "test.yaml")
    with TestClient(app) as client:
        yield client

def test_routes_polling_config_respect(client):
    """Verify routes.py uses the configured poll interval."""
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json()["poll_interval_ms"] == 5000

@pytest.fixture
def rig_client():
    """Fixture to provide a RigClient instance."""
    from multirig.rig.client import RigClient
    from multirig.config import RigConfig
    
    cfg = RigConfig(name="TestClient", poll_interval_ms=1000)
    client = RigClient(cfg)
    # Mock backend to strictly control responses
    client._backend = AsyncMock() 
    # Important: Ensure backend.status is AsyncMock
    client._backend.status = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_failure_is_not_cached(rig_client):
    """Verify that connection failures are not cached."""
    # 1. Successful call (cached)
    rig_client._backend.status = AsyncMock(return_value=RigStatus(connected=True, frequency_hz=14000000))
    await rig_client.status()
    assert rig_client._backend.status.call_count == 1
    
    # Second call uses cache
    await rig_client.status()
    assert rig_client._backend.status.call_count == 1
    
    # 2. Force backend failure
    rig_client._backend.status = AsyncMock(return_value=RigStatus(connected=False, error="Fail"))
    # Invalidate cache manually for the test setup by advancing time logic or just mocking time
    # Here, we can just rely on the fact that if we successfully fetch status again after TTL it should fail
    # But wait, we need to bypass the cache. Let's just reset the cache for this step to simulate TTL expiry
    rig_client._cached_status = None
    
    # 3. Call fails
    s = await rig_client.status()
    assert s.connected is False
    # Mock call count reset
    rig_client._backend.status.call_count = 1 
    
    # 4. Immediate next call (Should NOT be cached)
    # If cached, call_count stays 1. If not cached, it goes to 2.
    await rig_client.status()
    assert rig_client._backend.status.call_count == 2
