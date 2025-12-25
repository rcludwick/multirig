import sys
import pytest
from unittest.mock import patch
import importlib
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse

def test_app_works_without_orjson(monkeypatch, tmp_path):
    # Simulate orjson missing by removing it from sys.modules and preventing import
    with patch.dict(sys.modules, {'orjson': None}):
        # Reload multirig.app to trigger the import logic again
        import multirig.app
        importlib.reload(multirig.app)
        
        # Now create the app
        from multirig.app import create_app
        import multirig.app as appmod
        
        # Mock dependencies
        class DummyRigStatus:
            def __init__(self):
                self.connected = True
                self.frequency_hz = 14000000
                self.frequency_a_hz = None
                self.frequency_b_hz = None
                self.mode = "USB"
                self.passband = 0
                self.vfo = "VFOA"
                self.ptt = False
                self.error = None

        class DummyRigClient:
            def __init__(self, cfg):
                self.cfg = cfg
                self._status = DummyRigStatus()
            
            async def safe_status(self):
                return {
                    "name": getattr(self.cfg, "name", "Rig"),
                    "enabled": getattr(self.cfg, "enabled", True),
                    "connected": True,
                    "frequency_hz": 14000000,
                    "mode": "USB",
                }
            async def close(self): pass
            
        class DummySyncService:
            def __init__(self, *args, **kwargs):
                self.source_index = 0
                self.enabled = True
            async def start(self): pass
            async def stop(self): pass
            
        class DummyRigctlServer:
            def __init__(self, *args, **kwargs):
                self.host = "127.0.0.1"
                self.port = 4534
            async def start(self): pass
            async def stop(self): pass

        # Core module uses these
        import multirig.core as coremod
        monkeypatch.setattr(coremod, "RigClient", DummyRigClient)
        monkeypatch.setattr(appmod, "SyncService", DummySyncService)
        # Core imports RigctlServer for typing/inheritance?
        # Actually app.py imports AppRigctlServer from core.
        # core imports RigctlServer from rigctl_tcp.
        # app.py instantiates AppRigctlServer which is in core.
        # core.py imports RigctlServer
        monkeypatch.setattr(coremod, "RigctlServer", DummyRigctlServer)
        
        # Create app with dummy config
        app = create_app(config_path=tmp_path / "test.yaml")
        client = TestClient(app)
        
        # Make a request that returns JSON
        response = client.get("/api/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "rigs" in data
        
        # Verify that ORJSONResponse is aliased to JSONResponse in the module
        assert appmod.ORJSONResponse is JSONResponse