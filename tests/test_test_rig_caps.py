import pytest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient


class DummyRigStatus:
    def __init__(self, *, connected=True, frequency_hz=14074000, mode="USB", passband=2400):
        self.connected = connected
        self.frequency_hz = frequency_hz
        self.frequency_a_hz = None
        self.frequency_b_hz = None
        self.mode = mode
        self.passband = passband
        self.vfo = None
        self.ptt = None
        self.error = None


class DummyRigClient:
    def __init__(self, cfg):
        self.cfg = cfg
        self._backend = AsyncMock()

    async def safe_status(self):
        s = DummyRigStatus(connected=True)
        return {
            "name": getattr(self.cfg, "name", "Rig"),
            "enabled": getattr(self.cfg, "enabled", True),
            "follow_main": getattr(self.cfg, "follow_main", True),
            "connected": s.connected,
            "frequency_hz": s.frequency_hz,
            "frequency_a_hz": s.frequency_a_hz,
            "frequency_b_hz": s.frequency_b_hz,
            "mode": s.mode,
            "passband": s.passband,
            "vfo": s.vfo,
            "ptt": s.ptt,
            "error": s.error,
            "connection_type": getattr(self.cfg, "connection_type", "rigctld"),
            "model_id": getattr(self.cfg, "model_id", None),
            "allow_out_of_band": getattr(self.cfg, "allow_out_of_band", False),
            "band_presets": [],
            "host": getattr(self.cfg, "host", None),
            "port": getattr(self.cfg, "port", None),
            "caps": None,
            "modes": None,
        }

    async def dump_state(self):
        return []

    async def refresh_caps(self):
        return {
            "caps": {"freq_get": True, "freq_set": True},
            "modes": ["USB"],
            "raw": ["dump_caps:", "Can get Frequency: Y"],
        }

    async def status(self):
        return DummyRigStatus(connected=True)

    async def close(self):
        return None


class DummySyncService:
    def __init__(self, rigs, interval_ms=750, *, enabled=True, source_index=0):
        self.rigs = rigs
        self.interval_ms = interval_ms
        self.enabled = enabled
        self.source_index = source_index

    async def start(self):
        return None

    async def stop(self):
        return None


class DummyRigctlServer:
    def __init__(self, *args, **kwargs):
        self._host = (kwargs.get("config").host if kwargs.get("config") else "127.0.0.1")
        self._port = (kwargs.get("config").port if kwargs.get("config") else 4534)

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    async def start(self):
        return None

    async def stop(self):
        return None


@pytest.fixture()
def client(monkeypatch, tmp_path):
    import multirig.app as appmod
    from multirig.config import AppConfig

    cfg = AppConfig(rigs=[], sync_enabled=False)

    monkeypatch.setattr(appmod, "load_config", lambda path: cfg)
    monkeypatch.setattr(appmod, "save_config", lambda cfg, path: None)
    monkeypatch.setattr(appmod, "RigClient", DummyRigClient)
    monkeypatch.setattr(appmod, "SyncService", DummySyncService)
    monkeypatch.setattr(appmod, "RigctlServer", DummyRigctlServer)

    app = appmod.create_app(config_path=tmp_path / "test.yaml")
    return TestClient(app)


def test_test_rig_returns_caps_and_modes(client):
    payload = {
        "name": "Rig",
        "enabled": True,
        "connection_type": "rigctld",
        "host": "127.0.0.1",
        "port": 4532,
        "model_id": 2,
        "band_presets": [],
    }

    r = client.post("/api/test-rig", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"success", "warning"}
    assert body["caps"] == {"freq_get": True, "freq_set": True}
    assert body["modes"] == ["USB"]
