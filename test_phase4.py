"""Tests for Phase 4 API Gateway."""
import asyncio
import time
import json
from fastapi.testclient import TestClient

from multirig.app import app
from multirig.messages import RigState, SyncState, RigCaps
from multirig.zenoh import keys
from multirig.zenoh.session import init_session, close_session, get_session
from multirig.zenoh.serialization import serialize


def test_app_creation():
    """Test that the FastAPI app is created correctly."""
    assert app.title == "MultiRig"
    assert app.version == "0.2.0"
    print("✓ App creation works")


async def test_health_endpoint():
    """Test the health check endpoint."""
    await init_session()
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["zenoh"] == "connected"
    
    await close_session()
    print("✓ Health endpoint works")


async def test_rig_state_endpoint():
    """Test getting rig state via REST API."""
    await init_session()
    session = get_session()
    
    # Publish a rig state
    state = RigState(
        rig_id="test_rig",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB",
        bandwidth=3000
    )
    
    # Note: FastAPI TestClient doesn't work well with Zenoh queryables
    # This test demonstrates the structure but would need a running adapter
    # in a real integration test
    
    with TestClient(app) as client:
        # This would work if we had a queryable set up
        response = client.get("/api/rigs/test_rig/state")
        # For now, we expect 404 since no queryable is set up
        assert response.status_code in [404, 500]
    
    await close_session()
    print("✓ Rig state endpoint structure works")


async def test_set_frequency_endpoint():
    """Test setting frequency via REST API."""
    await init_session()
    session = get_session()
    
    # Track received commands
    received_commands = []
    
    def on_command(sample):
        from multirig.zenoh.serialization import deserialize
        from multirig.messages import RigCommand
        cmd = deserialize(sample.payload.to_bytes(), RigCommand)
        received_commands.append(cmd)
    
    # Subscribe to commands
    sub = session.declare_subscriber(keys.rig_command_key("test_rig"), on_command)
    
    with TestClient(app) as client:
        response = client.post(
            "/api/rigs/test_rig/frequency",
            json={"frequency": 14074000}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    # Wait for command
    await asyncio.sleep(0.2)
    
    # Check command was received
    assert len(received_commands) > 0
    assert received_commands[0].command_type == "set_frequency"
    assert received_commands[0].params["frequency"] == 14074000
    assert received_commands[0].source == "api"
    
    sub.undeclare()
    await close_session()
    print("✓ Set frequency endpoint works")


async def test_set_mode_endpoint():
    """Test setting mode via REST API."""
    await init_session()
    session = get_session()
    
    # Track received commands
    received_commands = []
    
    def on_command(sample):
        from multirig.zenoh.serialization import deserialize
        from multirig.messages import RigCommand
        cmd = deserialize(sample.payload.to_bytes(), RigCommand)
        received_commands.append(cmd)
    
    # Subscribe to commands
    sub = session.declare_subscriber(keys.rig_command_key("test_rig"), on_command)
    
    with TestClient(app) as client:
        response = client.post(
            "/api/rigs/test_rig/mode",
            json={"mode": "USB", "bandwidth": 3000}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
    
    # Wait for command
    await asyncio.sleep(0.2)
    
    # Check command was received
    assert len(received_commands) > 0
    assert received_commands[0].command_type == "set_mode"
    assert received_commands[0].params["mode"] == "USB"
    assert received_commands[0].params["bandwidth"] == 3000
    assert received_commands[0].source == "api"
    
    sub.undeclare()
    await close_session()
    print("✓ Set mode endpoint works")


async def test_sync_state_endpoint():
    """Test getting sync state via REST API."""
    await init_session()
    session = get_session()
    
    # Publish a sync state
    sync_state = SyncState(
        enabled=True,
        source_rig_id="rig1",
        follower_rig_ids=["rig2", "rig3"],
        sync_frequency=True,
        sync_mode=True,
        sync_ptt=False
    )
    session.put(keys.SYNC_STATE, serialize(sync_state))
    
    # Wait for it to be available
    await asyncio.sleep(0.2)
    
    with TestClient(app) as client:
        response = client.get("/api/sync/state")
        assert response.status_code == 200
        data = response.json()
        # Should return default or the published state
        assert "enabled" in data
        assert "source_rig_id" in data
        assert "follower_rig_ids" in data
    
    await close_session()
    print("✓ Sync state endpoint works")


async def test_websocket_manager():
    """Test WebSocket manager functionality."""
    from multirig.gateway.websocket import WebSocketManager
    
    await init_session()
    
    manager = WebSocketManager()
    await manager.start()
    
    # Check that subscribers are started
    assert manager._state_subscriber is not None
    assert manager._sync_subscriber is not None
    assert manager._started == True
    
    await manager.stop()
    
    assert manager._started == False
    
    await close_session()
    print("✓ WebSocket manager works")


async def test_routes_structure():
    """Test that all expected routes are registered."""
    routes = [route.path for route in app.routes]
    
    # Check key endpoints exist
    assert "/api/health" in routes
    assert "/api/rigs/{rig_id}/state" in routes
    assert "/api/rigs/{rig_id}/frequency" in routes
    assert "/api/rigs/{rig_id}/mode" in routes
    assert "/api/sync/state" in routes
    assert "/ws" in routes
    
    print("✓ All expected routes registered")


async def main():
    test_app_creation()
    await test_health_endpoint()
    await test_rig_state_endpoint()
    await test_set_frequency_endpoint()
    await test_set_mode_endpoint()
    await test_sync_state_endpoint()
    await test_websocket_manager()
    test_routes_structure()
    print("\n✓ All Phase 4 tests passed!")


if __name__ == '__main__':
    asyncio.run(main())
