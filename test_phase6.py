"""
Tests for Phase 6: Configuration and Profiles

This tests the configuration system, profile management, and config store
with Zenoh queryables and rig discovery.
"""
import asyncio
import time
from pathlib import Path
import tempfile
import os

from multirig.config import (
    AppConfig, RigConfig, SyncConfig, RigctlServerConfig,
    BandPreset, load_config, save_config, list_profiles,
    detect_bands_from_ranges, parse_dump_state_ranges
)
from multirig.messages import RigState
from multirig.messages.config import ConfigDiscovered, ConfigChanged
from multirig.engines.config_store import ConfigStore
from multirig.zenoh.session import init_session, close_session, get_session
from multirig.zenoh import keys
from multirig.zenoh.serialization import serialize, deserialize, deserialize_dict


async def test_config_models():
    """Test configuration models."""
    print("\n=== Test 1: Config Models ===")
    
    # Test BandPreset auto-fill
    preset = BandPreset(label="20m", frequency_hz=14074000)
    assert preset.lower_hz == 14000000
    assert preset.upper_hz == 14350000
    print(f"✓ BandPreset auto-fill: {preset.label} {preset.lower_hz}-{preset.upper_hz}")
    
    # Test RigConfig
    rig = RigConfig(
        rig_id="test_rig",
        name="Test Rig",
        connection_type="rigctld",
        host="localhost",
        port=4532
    )
    assert rig.rig_id == "test_rig"
    assert rig.connection_type == "rigctld"
    print(f"✓ RigConfig: {rig.name} ({rig.connection_type})")
    
    # Test AppConfig
    app_config = AppConfig()
    assert len(app_config.rigs) == 1
    assert app_config.sync.enabled == False
    print(f"✓ AppConfig: {len(app_config.rigs)} rigs")


async def test_config_persistence():
    """Test loading/saving configuration."""
    print("\n=== Test 2: Config Persistence ===")
    
    # Use temp directory for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create and save config
        config = AppConfig()
        config.rigs.append(RigConfig(rig_id="rig2", name="Rig 2", port=4533))
        config.sync.enabled = True
        config.sync.source_rig_id = "rig1"
        save_config(config, "test_profile")
        
        # Verify file was created
        config_path = Path(tmpdir) / "test_profile.yaml"
        assert config_path.exists()
        print(f"✓ Config saved to {config_path}")
        
        # Load config back
        loaded = load_config("test_profile")
        assert len(loaded.rigs) == 2
        assert loaded.sync.enabled == True
        assert loaded.sync.source_rig_id == "rig1"
        print(f"✓ Config loaded: {len(loaded.rigs)} rigs, sync={loaded.sync.enabled}")
        
        # Test profile listing
        profiles = list_profiles()
        assert "test_profile" in profiles
        print(f"✓ Profiles: {profiles}")


async def test_band_detection():
    """Test band detection from frequency ranges."""
    print("\n=== Test 3: Band Detection ===")
    
    # Test with HF rig coverage
    freq_ranges = [
        (1800000, 30000000),  # HF coverage
    ]
    
    bands = detect_bands_from_ranges(freq_ranges)
    band_labels = [b.label for b in bands]
    
    assert "20m" in band_labels
    assert "40m" in band_labels
    assert "80m" in band_labels
    print(f"✓ Detected {len(bands)} bands from HF range: {band_labels[:5]}...")
    
    # Test dump_state parsing
    dump_state_lines = [
        "0",  # Protocol
        "2",  # Model
        "2",  # ITU region
        "1800000 30000000 0x1ff -1 -1 0x10000003 0x3",  # RX range
        "1800000 30000000 0x1ff 5000 100000 0x10000003 0x3",  # TX range
    ]
    
    ranges = parse_dump_state_ranges(dump_state_lines)
    assert len(ranges) == 2
    assert ranges[0] == (1800000, 30000000)
    print(f"✓ Parsed {len(ranges)} frequency ranges from dump_state")


async def test_config_store():
    """Test config store with Zenoh queryable."""
    print("\n=== Test 4: Config Store ===")
    
    await init_session()
    
    # Use temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Create and start config store
        store = ConfigStore(profile_name="test")
        await store.start()
        
        # Verify initial config
        assert len(store.config.rigs) == 1
        print(f"✓ Config store started with {len(store.config.rigs)} rigs")
        
        # Test adding a rig
        store.add_rig({
            "rig_id": "rig2",
            "name": "Rig 2",
            "connection_type": "rigctld",
            "port": 4533
        })
        assert len(store.config.rigs) == 2
        print("✓ Added rig to config")
        
        # Test updating a rig
        store.update_rig("rig2", {"name": "Updated Rig 2"})
        rig2 = [r for r in store.config.rigs if r.rig_id == "rig2"][0]
        assert rig2.name == "Updated Rig 2"
        print("✓ Updated rig config")
        
        # Test sync config update
        store.update_sync({"enabled": True, "source_rig_id": "rig1"})
        assert store.config.sync.enabled == True
        print("✓ Updated sync config")
        
        await store.stop()
    
    await close_session()


async def test_config_queryable():
    """Test Zenoh queryable for config."""
    print("\n=== Test 5: Config Queryable ===")
    
    await init_session()
    session = get_session()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Start config store
        store = ConfigStore(profile_name="test")
        await store.start()
        
        # Wait for queryable to be ready
        await asyncio.sleep(0.5)
        
        # Query for config
        replies = session.get(keys.CONFIG)
        config_dict = None
        for reply in replies:
            if reply.ok:
                config_dict = deserialize_dict(reply.ok.payload.to_bytes())
                break
        
        assert config_dict is not None
        assert "rigs" in config_dict
        assert "sync" in config_dict
        print(f"✓ Queried config via Zenoh: {len(config_dict['rigs'])} rigs")
        
        await store.stop()
    
    await close_session()


async def test_rig_discovery():
    """Test rig discovery from bus."""
    print("\n=== Test 6: Rig Discovery ===")
    
    await init_session()
    session = get_session()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Subscribe to discovered rigs
        discovered_msgs = []
        
        def on_discovered(sample):
            msg = deserialize(sample.payload.to_bytes(), ConfigDiscovered)
            discovered_msgs.append(msg)
        
        sub = session.declare_subscriber(keys.CONFIG_DISCOVERED, on_discovered)
        
        # Start config store
        store = ConfigStore(profile_name="test")
        await store.start()
        
        # Wait for initial discovered message
        await asyncio.sleep(0.5)
        
        # Publish state for unknown rig
        unknown_state = RigState(
            rig_id="unknown_rig",
            timestamp=time.time(),
            connected=True,
            frequency=14074000
        )
        session.put(keys.rig_state_key("unknown_rig"), serialize(unknown_state))
        
        # Wait for discovery
        await asyncio.sleep(0.5)
        
        # Verify discovery
        assert len(discovered_msgs) > 0
        latest = discovered_msgs[-1]
        assert len(latest.discovered_rigs) == 1
        assert latest.discovered_rigs[0].rig_id == "unknown_rig"
        print(f"✓ Discovered rig: {latest.discovered_rigs[0].rig_id}")
        
        # Add discovered rig to config
        store.add_rig({
            "rig_id": "unknown_rig",
            "name": "Discovered Rig",
            "connection_type": "rigctld",
            "port": 4535
        })
        
        # Wait for update
        await asyncio.sleep(0.5)
        
        # Verify it was removed from discovered list
        latest = discovered_msgs[-1]
        assert len(latest.discovered_rigs) == 0
        print("✓ Discovered rig moved to configured rigs")
        
        sub.undeclare()
        await store.stop()
    
    await close_session()


async def test_config_change_notifications():
    """Test config change notifications."""
    print("\n=== Test 7: Config Change Notifications ===")
    
    await init_session()
    session = get_session()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["MULTIRIG_CONFIG_DIR"] = tmpdir
        
        # Subscribe to config changes
        changes = []
        
        def on_changed(sample):
            msg = deserialize(sample.payload.to_bytes(), ConfigChanged)
            changes.append(msg)
        
        sub = session.declare_subscriber(keys.CONFIG_CHANGED, on_changed)
        
        # Start config store
        store = ConfigStore(profile_name="test")
        await store.start()
        
        # Make some changes
        store.add_rig({
            "rig_id": "rig2",
            "name": "Rig 2",
            "connection_type": "rigctld",
            "port": 4533
        })
        
        await asyncio.sleep(0.3)
        
        store.update_sync({"enabled": True})
        
        await asyncio.sleep(0.3)
        
        # Verify notifications
        assert len(changes) >= 2
        assert any(c.change_type == "rig_added" and c.rig_id == "rig2" for c in changes)
        assert any(c.change_type == "sync_updated" for c in changes)
        print(f"✓ Received {len(changes)} config change notifications")
        
        sub.undeclare()
        await store.stop()
    
    await close_session()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 6: Configuration and Profiles Tests")
    print("=" * 60)
    
    await test_config_models()
    await test_config_persistence()
    await test_band_detection()
    await test_config_store()
    await test_config_queryable()
    await test_rig_discovery()
    await test_config_change_notifications()
    
    print("\n" + "=" * 60)
    print("✓ All Phase 6 tests passed!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
