"""Tests for Phase 1 infrastructure."""
import asyncio
import time
from multirig.zenoh import keys
from multirig.zenoh.serialization import serialize, deserialize
from multirig.zenoh.session import init_session, close_session, get_session
from multirig.messages import RigState, RigCommand


async def test_serialization():
    """Test message serialization."""
    state = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=14074000,
        mode="USB"
    )
    
    # Serialize
    data = serialize(state)
    assert isinstance(data, bytes)
    
    # Deserialize
    restored = deserialize(data, RigState)
    assert restored.rig_id == "rig1"
    assert restored.frequency == 14074000
    print("✓ Serialization works")


async def test_pubsub():
    """Test pub/sub with message types."""
    await init_session()
    session = get_session()
    
    received = []
    
    def on_message(sample):
        state = deserialize(sample.payload.to_bytes(), RigState)
        received.append(state)
    
    # Subscribe
    key = keys.rig_state_key("rig1")
    sub = session.declare_subscriber(key, on_message)
    
    # Publish
    state = RigState(
        rig_id="rig1",
        timestamp=time.time(),
        connected=True,
        frequency=7074000
    )
    session.put(key, serialize(state))
    
    # Wait and check
    await asyncio.sleep(0.5)
    assert len(received) == 1
    assert received[0].frequency == 7074000
    print("✓ Pub/sub with message types works")
    
    sub.undeclare()
    await close_session()


async def main():
    await test_serialization()
    await test_pubsub()
    print("\n✓ All Phase 1 tests passed!")


if __name__ == '__main__':
    asyncio.run(main())
