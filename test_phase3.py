"""Tests for Phase 3 Sync Engine."""
import asyncio
import time
from multirig.engines.sync import SyncEngine
from multirig.messages import RigState, RigCommand, SyncState
from multirig.zenoh import keys
from multirig.zenoh.session import init_session, close_session, get_session
from multirig.zenoh.serialization import serialize, deserialize


async def test_sync_engine_configuration():
    """Test sync engine configuration."""
    engine = SyncEngine()
    
    # Test initial state
    assert engine.enabled == False
    assert engine.source_rig_id is None
    assert len(engine.follower_rig_ids) == 0
    
    # Test configuration
    engine.configure(
        enabled=True,
        source_rig_id="rig1",
        follower_rig_ids=["rig2", "rig3"],
        sync_frequency=True,
        sync_mode=True,
        sync_ptt=False
    )
    
    assert engine.enabled == True
    assert engine.source_rig_id == "rig1"
    assert "rig2" in engine.follower_rig_ids
    assert "rig3" in engine.follower_rig_ids
    assert engine.sync_frequency == True
    assert engine.sync_mode == True
    assert engine.sync_ptt == False
    
    print("✓ Sync engine configuration works")


async def test_follower_management():
    """Test adding and removing followers."""
    engine = SyncEngine()
    
    # Add followers
    engine.add_follower("rig2")
    engine.add_follower("rig3")
    assert "rig2" in engine.follower_rig_ids
    assert "rig3" in engine.follower_rig_ids
    
    # Remove follower
    engine.remove_follower("rig2")
    assert "rig2" not in engine.follower_rig_ids
    assert "rig3" in engine.follower_rig_ids
    
    # Set source
    engine.set_source("rig1")
    assert engine.source_rig_id == "rig1"
    
    print("✓ Follower management works")


async def test_state_change_detection():
    """Test that sync engine detects relevant state changes."""
    engine = SyncEngine()
    engine.sync_frequency = True
    engine.sync_mode = True
    engine.sync_ptt = False
    
    # Initial state
    state1 = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB",
        bandwidth=3000,
        ptt=False
    )
    
    # Should be changed (first state)
    assert engine._state_changed(state1) == True
    engine._last_source_state = state1
    
    # Same state - should not be changed
    state2 = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB",
        bandwidth=3000,
        ptt=False
    )
    assert engine._state_changed(state2) == False
    
    # Frequency changed - should be detected
    state3 = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14076000,  # Changed
        mode="USB",
        bandwidth=3000,
        ptt=False
    )
    assert engine._state_changed(state3) == True
    engine._last_source_state = state3
    
    # Mode changed - should be detected
    state4 = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14076000,
        mode="LSB",  # Changed
        bandwidth=3000,
        ptt=False
    )
    assert engine._state_changed(state4) == True
    engine._last_source_state = state4
    
    # PTT changed but not syncing PTT - should not be detected
    state5 = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14076000,
        mode="LSB",
        bandwidth=3000,
        ptt=True  # Changed but not syncing
    )
    assert engine._state_changed(state5) == False
    
    # Now enable PTT sync
    engine.sync_ptt = True
    assert engine._state_changed(state5) == True
    
    print("✓ State change detection works")


async def test_sync_engine_integration():
    """Test sync engine with Zenoh integration."""
    await init_session()
    session = get_session()
    
    # Track received commands
    received_commands = []
    
    def on_command(sample):
        cmd = deserialize(sample.payload.to_bytes(), RigCommand)
        received_commands.append(cmd)
    
    # Subscribe to follower commands
    sub = session.declare_subscriber(keys.rig_command_key("rig2"), on_command)
    
    # Create and configure sync engine
    engine = SyncEngine(debounce_ms=50)  # Short debounce for testing
    engine.configure(
        enabled=True,
        source_rig_id="rig1",
        follower_rig_ids=["rig2"],
        sync_frequency=True,
        sync_mode=True,
        sync_ptt=False
    )
    
    await engine.start()
    
    # Wait a moment for subscriptions to settle
    await asyncio.sleep(0.2)
    
    # Publish a state change from source rig
    state = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB",
        bandwidth=3000
    )
    session.put(keys.rig_state_key("rig1"), serialize(state))
    
    # Wait for debounce and processing
    await asyncio.sleep(0.3)
    
    # Check that commands were sent to follower
    assert len(received_commands) >= 2  # Should have freq and mode commands
    
    # Check command types
    command_types = [cmd.command_type for cmd in received_commands]
    assert "set_frequency" in command_types
    assert "set_mode" in command_types
    
    # Check command sources
    for cmd in received_commands:
        assert cmd.source == "sync"
    
    # Check frequency command
    freq_cmds = [cmd for cmd in received_commands if cmd.command_type == "set_frequency"]
    assert freq_cmds[0].params["frequency"] == 14074000
    
    # Check mode command
    mode_cmds = [cmd for cmd in received_commands if cmd.command_type == "set_mode"]
    assert mode_cmds[0].params["mode"] == "USB"
    
    print("✓ Sync engine integration works")
    
    # Cleanup
    await engine.stop()
    sub.undeclare()
    await close_session()


async def test_sync_state_publishing():
    """Test that sync engine publishes its state."""
    await init_session()
    session = get_session()
    
    # Track received sync states
    received_states = []
    
    def on_sync_state(sample):
        state = deserialize(sample.payload.to_bytes(), SyncState)
        received_states.append(state)
    
    # Subscribe to sync state
    sub = session.declare_subscriber(keys.SYNC_STATE, on_sync_state)
    
    # Create and start sync engine
    engine = SyncEngine()
    engine.configure(
        enabled=True,
        source_rig_id="rig1",
        follower_rig_ids=["rig2", "rig3"],
        sync_frequency=True,
        sync_mode=True,
        sync_ptt=False
    )
    
    await engine.start()
    
    # Wait for state to be published
    await asyncio.sleep(0.2)
    
    # Check that sync state was published
    assert len(received_states) > 0
    
    latest_state = received_states[-1]
    assert latest_state.enabled == True
    assert latest_state.source_rig_id == "rig1"
    assert "rig2" in latest_state.follower_rig_ids
    assert "rig3" in latest_state.follower_rig_ids
    assert latest_state.sync_frequency == True
    assert latest_state.sync_mode == True
    assert latest_state.sync_ptt == False
    
    print("✓ Sync state publishing works")
    
    # Cleanup
    await engine.stop()
    sub.undeclare()
    await close_session()


async def main():
    await test_sync_engine_configuration()
    await test_follower_management()
    await test_state_change_detection()
    await test_sync_engine_integration()
    await test_sync_state_publishing()
    print("\n✓ All Phase 3 tests passed!")


if __name__ == '__main__':
    asyncio.run(main())
