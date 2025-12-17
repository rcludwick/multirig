import pytest
from fastapi.testclient import TestClient


class DummyRigStatus:
    def __init__(self, *, connected=True, frequency_hz=None, mode=None, passband=None):
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
        self._freq = None
        self._mode = None
        self._pb = None
        self._status = DummyRigStatus(connected=True, frequency_hz=cfg.band_presets[0].frequency_hz if cfg.band_presets else None)
        self.set_freq_calls = []
        self.set_mode_calls = []

    async def status(self):
        return self._status

    async def safe_status(self):
        s = await self.status()
        return {
            "name": self.cfg.name,
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
            "connection_type": getattr(self.cfg, "connection_type", "hamlib"),
            "model_id": getattr(self.cfg, "model_id", None),
            "allow_out_of_band": getattr(self.cfg, "allow_out_of_band", False),
            "band_presets": [bp.model_dump() for bp in getattr(self.cfg, "band_presets", [])],
            "host": getattr(self.cfg, "host", None),
            "port": getattr(self.cfg, "port", None),
        }

    async def set_frequency(self, hz: int) -> bool:
        self.set_freq_calls.append(int(hz))
        self._status.frequency_hz = int(hz)
        return True

    async def set_mode(self, mode: str, passband=None) -> bool:
        self.set_mode_calls.append((str(mode), passband))
        self._status.mode = str(mode)
        self._status.passband = passband
        return True

    async def set_vfo(self, vfo: str) -> bool:
        self._status.vfo = str(vfo)
        return True

    async def close(self) -> None:
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
    from multirig.config import AppConfig, RigConfig, BandPreset

    cfg = AppConfig(
        rigs=[
            RigConfig(
                name="Main",
                enabled=True,
                follow_main=True,
                allow_out_of_band=False,
                band_presets=[BandPreset(label="20m", frequency_hz=14074000, lower_hz=14000000, upper_hz=14350000)],
            ),
            RigConfig(
                name="Follower",
                enabled=True,
                follow_main=True,
                allow_out_of_band=False,
                band_presets=[BandPreset(label="20m", frequency_hz=14074000, lower_hz=14000000, upper_hz=14350000)],
            ),
            RigConfig(
                name="Manual",
                enabled=True,
                follow_main=False,
                allow_out_of_band=False,
                band_presets=[BandPreset(label="20m", frequency_hz=14074000, lower_hz=14000000, upper_hz=14350000)],
            ),
        ],
        sync_enabled=True,
        sync_source_index=0,
    )

    monkeypatch.setattr(appmod, "load_config", lambda path: cfg)
    monkeypatch.setattr(appmod, "save_config", lambda cfg, path: None)
    monkeypatch.setattr(appmod, "RigClient", DummyRigClient)
    monkeypatch.setattr(appmod, "SyncService", DummySyncService)
    monkeypatch.setattr(appmod, "RigctlTcpServer", DummyRigctlServer)

    app = appmod.create_app(config_path=tmp_path / "test.yaml")
    return TestClient(app)


def test_follow_main_toggle(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["rigs"][1]["follow_main"] is True

    r2 = client.post("/api/rig/1/follow_main", json={"follow_main": False})
    assert r2.status_code == 200
    assert r2.json()["status"] == "ok"
    assert r2.json()["follow_main"] is False

    r3 = client.get("/api/config")
    assert r3.json()["rigs"][1]["follow_main"] is False


def test_set_rig_frequency_out_of_band_blocked(client):
    # 1 MHz is outside 20m
    r = client.post("/api/rig/0/set", json={"frequency_hz": 1000000})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "out of configured band ranges" in body["error"]


def test_set_rig_frequency_in_band_allowed(client):
    r = client.post("/api/rig/0/set", json={"frequency_hz": 14074000})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_sync_source_index_sets_main_rig(client):
    r = client.post("/api/sync", json={"source_index": 1})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["sync_source_index"] == 1

    st = client.get("/api/status").json()
    assert st["sync_source_index"] == 1


def test_sync_all_once_only_follows_followers(client):
    # Make rig0 the source, rig1 follower, rig2 manual
    r = client.post("/api/sync", json={"source_index": 0})
    assert r.status_code == 200

    # Put a known frequency on the source
    r2 = client.post("/api/rig/0/set", json={"frequency_hz": 14074000})
    assert r2.status_code == 200

    r3 = client.post("/api/rig/sync_all_once", json={})
    assert r3.status_code == 200
    body = r3.json()
    assert body["status"] == "ok"

    synced = [x["index"] for x in body["results"]]
    assert 1 in synced
    assert 2 not in synced
