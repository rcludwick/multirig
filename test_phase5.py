"""
Tests for Phase 5: Rigctl Server

This tests the rigctl TCP server that allows external apps like WSJT-X to
connect and control rigs through the Zenoh bus.
"""
import asyncio
import time
from multirig.zenoh.session import init_session, close_session, get_session
from multirig.zenoh import keys
from multirig.zenoh.serialization import serialize, deserialize
from multirig.messages import RigState, RigCommand, RigCaps
from multirig.rigctl_server import RigctlServer, RigctlServerConfig


async def test_server_startup():
    """Test that the server starts and stops cleanly."""
    print("\n=== Test 1: Server Startup/Shutdown ===")
    
    await init_session()
    
    config = RigctlServerConfig(
        host="127.0.0.1",
        port=14532,  # Use different port for testing
        target_rig_id="test_rig"
    )
    
    server = RigctlServer(config)
    await server.start()
    print("✓ Server started")
    
    await asyncio.sleep(0.5)
    
    await server.stop()
    print("✓ Server stopped")
    
    await close_session()


async def test_basic_commands():
    """Test basic rigctl commands through TCP."""
    print("\n=== Test 2: Basic Commands ===")
    
    await init_session()
    session = get_session()
    
    # Start server FIRST
    config = RigctlServerConfig(
        host="127.0.0.1",
        port=14532,
        target_rig_id="test_rig"
    )
    
    server = RigctlServer(config)
    await server.start()
    
    # NOW publish initial rig state (so subscription receives it)
    initial_state = RigState(
        rig_id="test_rig",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB",
        bandwidth=2400,
        vfo="VFOA",
        ptt=False
    )
    session.put(keys.rig_state_key("test_rig"), serialize(initial_state))
    
    # Publish capabilities
    caps = RigCaps(
        rig_id="test_rig",
        model_id=1035,
        model_name="IC-7300",
        manufacturer="Icom",
        modes=["USB", "LSB", "CW", "FM"],
        has_ptt=True
    )
    session.put(keys.rig_caps_key("test_rig"), serialize(caps))
    
    # Give server time to receive state
    await asyncio.sleep(1.0)
    
    # Connect as a client
    reader, writer = await asyncio.open_connection('127.0.0.1', 14532)
    print("✓ Client connected")
    
    # Test get_freq
    writer.write(b"f\n")
    await writer.drain()
    response = await reader.readline()
    freq = int(response.decode().strip())
    assert freq == 14074000, f"Expected 14074000, got {freq}"
    print(f"✓ get_freq returned {freq}")
    
    # Test get_mode
    writer.write(b"m\n")
    await writer.drain()
    mode_line = await reader.readline()
    bw_line = await reader.readline()
    mode = mode_line.decode().strip()
    bandwidth = int(bw_line.decode().strip())
    assert mode == "USB", f"Expected USB, got {mode}"
    assert bandwidth == 2400, f"Expected 2400, got {bandwidth}"
    print(f"✓ get_mode returned {mode} {bandwidth}")
    
    # Test set_freq (optimistic update)
    writer.write(b"F 7074000\n")
    await writer.drain()
    response = await reader.readline()
    assert response.decode().strip() == "RPRT 0"
    print("✓ set_freq command accepted")
    
    # Verify optimistic update - get_freq should immediately return new value
    writer.write(b"f\n")
    await writer.drain()
    response = await reader.readline()
    freq = int(response.decode().strip())
    assert freq == 7074000, f"Expected optimistic update to 7074000, got {freq}"
    print(f"✓ Optimistic update working: get_freq immediately returned {freq}")
    
    # Test stub commands
    writer.write(b"l KEYSPD\n")
    await writer.drain()
    response = await reader.readline()
    level = int(response.decode().strip())
    assert level == 0, f"Expected 0 for stub get_level, got {level}"
    print("✓ get_level stub returned 0")
    
    writer.write(b"get_powerstat\n")
    await writer.drain()
    response = await reader.readline()
    powerstat = int(response.decode().strip())
    assert powerstat == 1, f"Expected 1 for powerstat (connected), got {powerstat}"
    print("✓ get_powerstat returned 1 (connected)")
    
    # Close client
    writer.close()
    await writer.wait_closed()
    print("✓ Client disconnected")
    
    await server.stop()
    await close_session()


async def test_extended_response_protocol():
    """Test extended response protocol (ERP)."""
    print("\n=== Test 3: Extended Response Protocol ===")
    
    await init_session()
    session = get_session()
    
    # Start server FIRST
    config = RigctlServerConfig(
        host="127.0.0.1",
        port=14532,
        target_rig_id="test_rig"
    )
    
    server = RigctlServer(config)
    await server.start()
    
    # NOW publish initial state
    initial_state = RigState(
        rig_id="test_rig",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB"
    )
    session.put(keys.rig_state_key("test_rig"), serialize(initial_state))
    
    await asyncio.sleep(1.0)
    
    # Connect as a client
    reader, writer = await asyncio.open_connection('127.0.0.1', 14532)
    
    # Test ERP with + prefix
    writer.write(b"+f\n")
    await writer.drain()
    
    # Read multi-line response
    line1 = await reader.readline()
    line2 = await reader.readline()
    line3 = await reader.readline()
    
    assert line1.decode().strip() == "get_freq:"
    assert "Frequency:" in line2.decode()
    assert line3.decode().strip() == "RPRT 0"
    print("✓ Extended response protocol working")
    
    writer.close()
    await writer.wait_closed()
    
    await server.stop()
    await close_session()


async def test_command_propagation():
    """Test that commands are published to Zenoh."""
    print("\n=== Test 4: Command Propagation ===")
    
    await init_session()
    session = get_session()
    
    # Subscribe to commands
    received_commands = []
    
    def on_command(sample):
        cmd = deserialize(sample.payload.to_bytes(), RigCommand)
        received_commands.append(cmd)
    
    sub = session.declare_subscriber(keys.rig_command_key("test_rig"), on_command)
    
    # Start server
    config = RigctlServerConfig(
        host="127.0.0.1",
        port=14532,
        target_rig_id="test_rig"
    )
    
    server = RigctlServer(config)
    await server.start()
    
    # Publish initial state
    initial_state = RigState(
        rig_id="test_rig",
        timestamp=time.time(),
        connected=True
    )
    session.put(keys.rig_state_key("test_rig"), serialize(initial_state))
    await asyncio.sleep(0.5)
    
    # Connect and send command
    reader, writer = await asyncio.open_connection('127.0.0.1', 14532)
    
    writer.write(b"F 14074000\n")
    await writer.drain()
    await reader.readline()  # Read RPRT response
    
    # Wait for command to propagate
    await asyncio.sleep(0.5)
    
    # Verify command was published
    assert len(received_commands) == 1
    cmd = received_commands[0]
    assert cmd.command_type == "set_frequency"
    assert cmd.params["frequency"] == 14074000
    assert cmd.source == "rigctl"
    print(f"✓ Command propagated to Zenoh: {cmd.command_type} {cmd.params}")
    
    writer.close()
    await writer.wait_closed()
    
    sub.undeclare()
    await server.stop()
    await close_session()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 5: Rigctl Server Tests")
    print("=" * 60)
    
    await test_server_startup()
    await test_basic_commands()
    await test_extended_response_protocol()
    await test_command_propagation()
    
    print("\n" + "=" * 60)
    print("✓ All Phase 5 tests passed!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
