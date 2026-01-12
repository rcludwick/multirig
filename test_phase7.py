"""
Tests for Phase 7: Integration and Polish

This tests the application manager and full system integration with all
components working together.
"""
import asyncio
import tempfile
import os
from pathlib import Path

from multirig.application import ApplicationManager
from multirig.config import AppConfig, RigConfig, save_config


async def test_application_manager_startup():
    """Test application manager startup and shutdown."""
    print("\n=== Test 1: Application Manager Startup/Shutdown ===")
    
    # Use temp directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create minimal test config
        config = AppConfig()
        config.test_mode = False  # Allow saving
        config.rigs = []  # No rigs for quick test
        config.sync.enabled = False
        config.rigctl_server.enabled = False
        save_config(config, "test")
        
        # Create and start application manager
        app_manager = ApplicationManager(profile_name="test")
        await app_manager.start()
        print("✓ Application manager started")
        
        # Verify components are initialized
        assert app_manager.config is not None
        assert app_manager.config_store is not None
        print("✓ Components initialized")
        
        # Stop application manager
        await app_manager.stop()
        print("✓ Application manager stopped")


async def test_application_with_adapters():
    """Test application manager with rig adapters."""
    print("\n=== Test 2: Application with Rig Adapters ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create config with a rig
        config = AppConfig()
        config.test_mode = False
        config.rigs = [
            RigConfig(
                rig_id="test_rig",
                name="Test Rig",
                connection_type="rigctld",
                host="127.0.0.1",
                port=14532,  # Non-standard port to avoid conflicts
                enabled=False  # Disabled so we don't try to actually connect
            )
        ]
        config.sync.enabled = False
        config.rigctl_server.enabled = False
        save_config(config, "test")
        
        # Start application
        app_manager = ApplicationManager(profile_name="test")
        await app_manager.start()
        print("✓ Application with rig config started")
        
        # Verify config was loaded
        assert len(app_manager.config.rigs) == 1
        assert app_manager.config.rigs[0].rig_id == "test_rig"
        
        # Since rig is disabled, no adapter should be created
        assert len(app_manager.adapters) == 0
        print("✓ Disabled rig correctly skipped")
        
        await app_manager.stop()
        print("✓ Application stopped")


async def test_application_with_sync():
    """Test application manager with sync engine."""
    print("\n=== Test 3: Application with Sync Engine ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create config with sync enabled
        config = AppConfig()
        config.test_mode = False
        config.rigs = []
        config.sync.enabled = True
        config.sync.source_rig_id = "rig1"
        config.sync.follower_rig_ids = ["rig2"]
        config.rigctl_server.enabled = False
        save_config(config, "test")
        
        # Start application
        app_manager = ApplicationManager(profile_name="test")
        await app_manager.start()
        print("✓ Application with sync enabled started")
        
        # Verify sync engine was created
        assert app_manager.sync_engine is not None
        assert app_manager.sync_engine.enabled == True
        assert app_manager.sync_engine.source_rig_id == "rig1"
        print("✓ Sync engine configured correctly")
        
        await app_manager.stop()
        print("✓ Application stopped")


async def test_application_with_rigctl_server():
    """Test application manager with rigctl server."""
    print("\n=== Test 4: Application with Rigctl Server ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create config with rigctl server enabled
        config = AppConfig()
        config.test_mode = False
        config.rigs = []
        config.sync.enabled = False
        config.rigctl_server.enabled = True
        config.rigctl_server.host = "127.0.0.1"
        config.rigctl_server.port = 14534  # Non-standard port
        config.rigctl_server.target_rig_id = "rig1"
        save_config(config, "test")
        
        # Start application
        app_manager = ApplicationManager(profile_name="test")
        await app_manager.start()
        print("✓ Application with rigctl server started")
        
        # Verify rigctl server was created
        assert app_manager.rigctl_server is not None
        print("✓ Rigctl server initialized")
        
        await app_manager.stop()
        print("✓ Application stopped")


async def test_safety_configuration():
    """Test that safety configuration is applied to adapters."""
    print("\n=== Test 5: Safety Configuration ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create config with band limits
        from multirig.config import BandPreset
        
        config = AppConfig()
        config.test_mode = False
        config.rigs = [
            RigConfig(
                rig_id="test_rig",
                name="Test Rig",
                connection_type="rigctld",
                host="127.0.0.1",
                port=14532,
                enabled=False,  # Don't actually connect
                allow_out_of_band=False,  # Enforce band limits
                band_presets=[
                    BandPreset(label="20m", frequency_hz=14074000, enabled=True),
                    BandPreset(label="40m", frequency_hz=7074000, enabled=True),
                ]
            )
        ]
        config.sync.enabled = False
        config.rigctl_server.enabled = False
        save_config(config, "test")
        
        # Create application but don't start (to avoid connection attempts)
        app_manager = ApplicationManager(profile_name="test")
        app_manager.config = config
        
        # Manually create adapter to test safety config
        rig_config = config.rigs[0]
        adapter = app_manager._create_adapter(rig_config)
        
        # Verify safety config was applied
        assert adapter._allow_out_of_band == False
        assert len(adapter._band_presets) == 2
        assert adapter._band_presets[0].label == "20m"
        print("✓ Safety configuration applied correctly")
        print(f"  - allow_out_of_band: {adapter._allow_out_of_band}")
        print(f"  - band_presets: {len(adapter._band_presets)} bands")


async def test_full_integration():
    """Test full integration with all components."""
    print("\n=== Test 6: Full Integration ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create comprehensive config
        config = AppConfig()
        config.test_mode = False
        config.rigs = []  # No rigs to avoid connection issues
        config.sync.enabled = True
        config.sync.source_rig_id = "rig1"
        config.rigctl_server.enabled = True
        config.rigctl_server.port = 14535
        save_config(config, "test")
        
        # Start full application
        app_manager = ApplicationManager(profile_name="test")
        await app_manager.start()
        print("✓ Full application started with all components")
        
        # Verify all components
        assert app_manager.config_store is not None
        assert app_manager.sync_engine is not None
        assert app_manager.rigctl_server is not None
        print("✓ All components initialized:")
        print(f"  - Config Store: active")
        print(f"  - Sync Engine: active")
        print(f"  - Rigctl Server: active")
        print(f"  - Adapters: {len(app_manager.adapters)}")
        
        # Let it run briefly
        await asyncio.sleep(0.5)
        
        await app_manager.stop()
        print("✓ Full application stopped cleanly")


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 7: Integration and Polish Tests")
    print("=" * 60)
    
    await test_application_manager_startup()
    await test_application_with_adapters()
    await test_application_with_sync()
    await test_application_with_rigctl_server()
    await test_safety_configuration()
    await test_full_integration()
    
    print("\n" + "=" * 60)
    print("✓ All Phase 7 tests passed!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
