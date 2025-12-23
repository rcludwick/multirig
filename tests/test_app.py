"""Unit tests for app.py - ProfileManager, API endpoints, and configuration management."""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from multirig.app import ProfileManager

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

# Original test_app.py tests
def test_set_rig_frequency_out_of_band_blocked(client):
    # 1 MHz is outside 20m
    r = client.post("/api/rig/0/set", json={"frequency_hz": 1000000})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "out of configured band ranges" in body["error"]

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

# ProfileManager tests from test_app_profiles.py
class TestProfileManager:
    """Test the ProfileManager class."""

    def test_init_creates_memory_store(self):
        """ProfileManager should initialize with empty memory store."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert isinstance(pm._memory_store, dict)
        assert len(pm._memory_store) == 0

    def test_persist_active_name_in_test_mode(self):
        """persist_active_name should not write files in test_mode."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        pm.persist_active_name("TestProfile")
        # Should not raise any errors
        assert True

    def test_persist_active_name_writes_file(self, tmp_path):
        """persist_active_name should write to file when not in test_mode."""
        active_file = tmp_path / "active_profile"
        pm = ProfileManager(tmp_path, test_mode=False)
        pm.active_profile_path = active_file

        pm.persist_active_name("MyProfile")
        assert active_file.exists()
        assert active_file.read_text().strip() == "MyProfile"

    def test_get_active_name_returns_empty_string(self, tmp_path):
        """get_active_name should return empty string when no active profile."""
        pm = ProfileManager(tmp_path, test_mode=False)
        assert pm.get_active_name() == ""

    def test_get_active_name_returns_profile_name(self, tmp_path):
        """get_active_name should return the active profile name."""
        pm = ProfileManager(tmp_path, test_mode=False)
        pm.active_profile_path = tmp_path / "active_profile"
        (tmp_path / "active_profile").write_text("MyProfile\n")
        assert pm.get_active_name() == "MyProfile"

    def test_list_names_empty_in_test_mode(self):
        """list_names should return empty list when no profiles exist."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert pm.list_names() == []

    def test_list_names_returns_sorted_list(self, tmp_path):
        """list_names should return sorted list of profile names."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "z_profile.yaml").write_text("")
        (profiles_dir / "a_profile.yaml").write_text("")

        pm = ProfileManager(tmp_path, test_mode=False)
        pm.profiles_dir = profiles_dir
        names = pm.list_names()
        assert names == ["a_profile", "z_profile"]

    def test_exists_returns_false_for_nonexistent(self):
        """exists should return False for non-existent profile."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert not pm.exists("NonexistentProfile")

    def test_exists_returns_true_in_test_mode(self):
        """exists should return True for profile in memory store."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        pm._memory_store["TestProfile"] = {}
        assert pm.exists("TestProfile")

    def test_load_data_raises_error_for_missing(self):
        """load_data should raise FileNotFoundError for missing profile."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        with pytest.raises(FileNotFoundError):
            pm.load_data("MissingProfile")

    def test_load_data_returns_data_from_memory(self):
        """load_data should return data from memory store in test_mode."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        test_data = {"key": "value"}
        pm._memory_store["TestProfile"] = test_data
        assert pm.load_data("TestProfile") == test_data

    def test_save_data_stores_in_memory(self):
        """save_data should store data in memory when in test_mode."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        test_data = {"key": "value"}
        pm.save_data("TestProfile", test_data)
        assert pm._memory_store["TestProfile"] == test_data

    def test_delete_removes_from_memory(self):
        """delete should remove profile from memory store in test_mode."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        pm._memory_store["TestProfile"] = {"key": "value"}
        assert pm.delete("TestProfile") is True
        assert "TestProfile" not in pm._memory_store

    def test_rename_in_memory(self):
        """rename should rename profile in memory store."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        pm._memory_store["OldName"] = {"key": "value"}
        pm.rename("OldName", "NewName")
        assert "NewName" in pm._memory_store
        assert "OldName" not in pm._memory_store

    def test_is_valid_name_returns_false_for_empty(self):
        """is_valid_name should return False for empty string."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert not pm.is_valid_name("")

    def test_is_valid_name_returns_false_for_invalid_chars(self):
        """is_valid_name should return False for invalid characters."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert not pm.is_valid_name("Invalid@Name")
        assert not pm.is_valid_name("Has Spaces")

    def test_is_valid_name_returns_true_for_valid(self):
        """is_valid_name should return True for valid names."""
        pm = ProfileManager(Path("/tmp/test"), test_mode=True)
        assert pm.is_valid_name("Valid_Name")
        assert pm.is_valid_name("Profile123")
        assert pm.is_valid_name("Test-Profile")

def test_profile_manager_file_operations(tmp_path):
    """Test ProfileManager file operations outside of test_mode."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    pm = ProfileManager(tmp_path, test_mode=False)
    pm.profiles_dir = profiles_dir

    # Test save and load
    test_data = {"config": "value"}
    pm.save_data("TestProfile", test_data)

    assert (profiles_dir / "TestProfile.yaml").exists()
    loaded = pm.load_data("TestProfile")
    assert loaded == test_data

    # Test exists
    assert pm.exists("TestProfile")

    # Test list_names
    names = pm.list_names()
    assert "TestProfile" in names

    # Test delete
    assert pm.delete("TestProfile") is True
    assert not pm.exists("TestProfile")

# API endpoint tests from test_app_api.py
def test_update_config(client):
    """Test updating the configuration."""
    new_config = {
        "rigs": [
            {"name": "Main", "enabled": True, "follow_main": True},
            {"name": "Follower", "enabled": False, "follow_main": True},
            {"name": "Manual", "enabled": False, "follow_main": False},
        ],
        "sync_enabled": False,
        "sync_source_index": 0,
    }
    response = client.post("/api/config", json=new_config)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_list_config_profiles(client):
    """Test listing configuration profiles."""
    response = client.get("/api/config/profiles")
    assert response.status_code == 200
    data = response.json()
    assert "profiles" in data

def test_get_active_profile(client):
    """Test getting the active profile name."""
    response = client.get("/api/config/active_profile")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data

def test_create_config_profile(client):
    """Test creating a new configuration profile."""
    response = client.post("/api/config/profiles/NewProfile/create")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_rename_config_profile(client):
    """Test renaming a configuration profile."""
    # First create a profile
    client.post("/api/config/profiles/OldName/create")

    response = client.post("/api/config/profiles/OldName/rename", json={"new_name": "NewName"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_duplicate_config_profile(client):
    """Test duplicating a configuration profile."""
    # First create a profile
    client.post("/api/config/profiles/Source/create")

    response = client.post("/api/config/profiles/Source/duplicate", json={"new_name": "Copy"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_save_config_profile(client):
    """Test saving a configuration to a profile."""
    # First create the profile
    client.post("/api/config/profiles/TestProfile/create")
    response = client.post("/api/config/profiles/TestProfile")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_export_config_profile(client):
    """Test exporting a configuration profile."""
    # First create a profile
    client.post("/api/config/profiles/ExportMe/create")

    response = client.get("/api/config/profiles/ExportMe/export")
    assert response.status_code == 200
    assert "text/yaml" in response.headers["content-type"]

def test_load_config_profile(client):
    """Test loading a configuration profile."""
    # First create a profile
    client.post("/api/config/profiles/LoadMe/create")

    response = client.post("/api/config/profiles/LoadMe/load")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_delete_config_profile(client):
    """Test deleting a configuration profile."""
    # First create a profile
    client.post("/api/config/profiles/DeleteMe/create")

    response = client.delete("/api/config/profiles/DeleteMe")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_rigctl_listener_status(client):
    """Test getting rigctl listener status."""
    response = client.get("/api/rigctl_listener")
    assert response.status_code == 200
    data = response.json()
    assert "host" in data
    assert "port" in data

def test_set_rig_enabled(client):
    """Test enabling/disabling a rig."""
    response = client.post("/api/rig/0/enabled", json={"enabled": False})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["enabled"] is False

def test_set_rig_follow_main(client):
    """Test setting rig follow_main flag."""
    response = client.post("/api/rig/0/follow_main", json={"follow_main": False})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["follow_main"] is False

def test_set_all_rigs_enabled(client):
    """Test enabling/disabling all rigs."""
    response = client.post("/api/rig/enabled_all", json={"enabled": False})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["enabled"] is False

def test_sync_settings(client):
    """Test updating sync settings."""
    response = client.post("/api/sync", json={"enabled": False, "source_index": 1})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["enabled"] is False
    assert data["sync_source_index"] == 1

def test_rigctl_to_main_settings(client):
    """Test updating rigctl to main settings."""
    response = client.post("/api/rigctl_to_main", json={"enabled": False})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["enabled"] is False

def test_get_status(client):
    """Test getting overall system status."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "rigs" in data
    assert isinstance(data["rigs"], list)

def test_get_bind_addrs(client):
    """Test getting available bind addresses."""
    response = client.get("/api/bind_addrs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Should include localhost and 0.0.0.0
    assert "127.0.0.1" in data or "0.0.0.0" in data

def test_set_rig_mode(client):
    """Test setting rig mode."""
    response = client.post("/api/rig/a/set", json={"mode": "USB"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_set_rig_vfo(client):
    """Test setting rig VFO."""
    response = client.post("/api/rig/a/set", json={"vfo": "VFOA"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

def test_sync_rig_from_source(client):
    """Test syncing a rig from the source."""
    response = client.post("/api/rig/1/sync_from_source")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
