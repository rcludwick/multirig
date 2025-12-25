import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from multirig.app import create_app
from multirig.config import AppConfig

@pytest.fixture
def mock_cfg():
    cfg = MagicMock() # removed spec=AppConfig to avoid pydantic attrib issues
    cfg.rigs = []
    cfg.band_presets = []
    cfg.http_port = 8000
    cfg.rigctl_listen_host = "127.0.0.1"
    cfg.rigctl_listen_port = 4534
    cfg.test_mode = False
    cfg.poll_interval_ms = 1000
    cfg.sync_enabled = True
    cfg.sync_source_index = 0
    cfg.rigctl_to_main_enabled = True
    # AppConfig has no rigctl_server field
    return cfg

def test_create_app_with_config(mock_cfg):
    # Test create_app with explicit config
    # Test create_app with explicit config.
    # Note: create_app arguments might change, but this tests logic flow.
    # Then load_config(app.state.config_path).
    
    # We can mock load_config
    with patch("multirig.app.load_config", return_value=mock_cfg):
        app = create_app()
        assert app.state.config is mock_cfg

def test_create_app_load_config_failure():
    # Test create_app when config load fails
    with patch("multirig.app.load_config", side_effect=Exception("Load fail")):
        with pytest.raises(Exception, match="Load fail"):
             create_app()

@pytest.mark.asyncio
async def test_lifespan_startup_shutdown(mock_cfg):
    with patch("multirig.app.load_config", return_value=mock_cfg):
        app = create_app()
    
    app.state.rigs = []
    app.state.sync_service = AsyncMock()
    app.state.rigctl_server = AsyncMock()
    
    # Mock profiles
    app.state.profiles = MagicMock()
    app.state.profiles.get_active_name.return_value = "default"
    
    async with app.router.lifespan_context(app):
        # Startup checks
        app.state.sync_service.start.assert_called()
        app.state.rigctl_server.start.assert_called()
    
    # Shutdown checks
    app.state.sync_service.stop.assert_called()
    app.state.rigctl_server.stop.assert_called()

@pytest.mark.asyncio
async def test_lifespan_startup_error(mock_cfg):
    with patch("multirig.app.load_config", return_value=mock_cfg):
        app = create_app()
        
    app.state.sync_service = AsyncMock()
    app.state.sync_service.start.side_effect = Exception("Start fail")
    
    # No need to patch _bootstrap_active_profile if we don't assert on it and it doesn't fail
    app.state.profiles = MagicMock()
    
    with pytest.raises(Exception, match="Start fail"):
         async with app.router.lifespan_context(app):
             pass

def test_config_endpoint_update_error(mock_cfg):
    # Test /api/config POST error handling
    with patch("multirig.app.load_config", return_value=mock_cfg):
        app = create_app()
    
    # TestClient raises server exceptions by default. Disable it to get 500 response.
    client = TestClient(app, raise_server_exceptions=False)
    
    with patch("multirig.app.save_config", side_effect=Exception("Save fail")):
        # The endpoint calls _apply_config which calls save_config
        resp = client.post("/api/config", json={"rigs": []})
        assert resp.status_code == 500
