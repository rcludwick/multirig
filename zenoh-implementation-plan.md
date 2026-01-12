# MultiRig Zenoh Implementation Plan

This document provides a step-by-step implementation plan for rebuilding MultiRig with Zenoh. Each phase builds on the previous one and can be tested independently.

**Prerequisites:**
- Python 3.10+ installed
- `uv` package manager installed
- Basic understanding of pub/sub messaging
- Familiarity with async Python (asyncio)

**Reference Material:**
- [Zenoh Architecture](./zenoh-architecture.md) - Read this first
- [Zenoh Python Examples](https://github.com/eclipse-zenoh/zenoh-python/tree/main/examples)
- Original code in `old/` directory for hamlib message handling patterns

---

## Phase 0: Setup and Preparation

**Goal:** Prepare the development environment and preserve the old code.

### Step 0.1: Create Old Directory

Move existing code to `old/` for reference:

```bash
mkdir -p old
mv multirig old/
mv tests old/
```

### Step 0.2: Create New Project Structure

```bash
mkdir -p multirig/{zenoh,messages,adapters,engines,gateway,rigctl_server,hamlib}
touch multirig/__init__.py
touch multirig/{zenoh,messages,adapters,engines,gateway,rigctl_server,hamlib}/__init__.py
```

### Step 0.3: Update Dependencies

Add Zenoh to `pyproject.toml`:

```toml
[project]
dependencies = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.20.0",
    "eclipse-zenoh>=1.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "pyserial>=3.5",
]
```

Install dependencies:

```bash
uv sync
```

### Step 0.4: Verify Zenoh Works

Create a test file `test_zenoh.py`:

```python
import zenoh
import time

def test_pubsub():
    """Simple test to verify Zenoh is working."""
    received = []
    
    def listener(sample):
        received.append(sample.payload.to_string())
    
    with zenoh.open() as session:
        # Subscribe
        sub = session.declare_subscriber('test/hello', listener)
        
        # Publish
        session.put('test/hello', 'Hello Zenoh!')
        
        # Wait for message
        time.sleep(0.5)
        
        assert len(received) == 1
        assert received[0] == 'Hello Zenoh!'
        print("✓ Zenoh pub/sub working!")

if __name__ == '__main__':
    test_pubsub()
```

Run it:

```bash
uv run python test_zenoh.py
```

### Checklist for Phase 0:
- [x] Old code moved to `old/` directory
- [x] New directory structure created
- [x] Dependencies updated in pyproject.toml
- [x] `uv sync` completed successfully
- [x] Zenoh test script works

---

## Phase 1: Core Infrastructure

**Goal:** Build the foundational Zenoh utilities and message types.

### Step 1.1: Key Expression Constants

Create `multirig/zenoh/keys.py`:

```python
"""
Zenoh key expression constants.

Key expressions are like MQTT topics. We use a hierarchical structure:
    multirig/rig/{rig_id}/state   - Rig status updates
    multirig/rig/{rig_id}/command - Commands TO the rig
    multirig/rig/{rig_id}/caps    - Rig capabilities
    multirig/sync/state           - Sync engine status
    multirig/config               - Configuration (queryable)
"""

# Base prefix for all MultiRig keys
PREFIX = "multirig"

# Rig-related keys
RIG_STATE = f"{PREFIX}/rig/{{rig_id}}/state"
RIG_COMMAND = f"{PREFIX}/rig/{{rig_id}}/command"
RIG_CAPS = f"{PREFIX}/rig/{{rig_id}}/caps"

# Subscribe to ALL rig states
RIG_STATE_ALL = f"{PREFIX}/rig/*/state"
RIG_COMMAND_ALL = f"{PREFIX}/rig/*/command"

# Sync engine keys
SYNC_STATE = f"{PREFIX}/sync/state"

# Config keys
CONFIG = f"{PREFIX}/config"
CONFIG_DISCOVERED = f"{PREFIX}/config/discovered"
CONFIG_CHANGED = f"{PREFIX}/config/changed"


def rig_state_key(rig_id: str) -> str:
    """Get the state key for a specific rig."""
    return RIG_STATE.format(rig_id=rig_id)


def rig_command_key(rig_id: str) -> str:
    """Get the command key for a specific rig."""
    return RIG_COMMAND.format(rig_id=rig_id)


def rig_caps_key(rig_id: str) -> str:
    """Get the capabilities key for a specific rig."""
    return RIG_CAPS.format(rig_id=rig_id)
```

### Step 1.2: Serialization Helpers

Create `multirig/zenoh/serialization.py`:

```python
"""
JSON serialization helpers for Zenoh messages.

All messages are serialized as JSON for easy debugging and interoperability.
"""
import json
from dataclasses import asdict, is_dataclass
from typing import TypeVar, Type

from pydantic import BaseModel


T = TypeVar('T')


def serialize(obj: object) -> bytes:
    """
    Serialize an object to JSON bytes for Zenoh.
    
    Supports:
    - Pydantic models
    - Dataclasses
    - Dictionaries
    
    Args:
        obj: Object to serialize
        
    Returns:
        UTF-8 encoded JSON bytes
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump_json().encode('utf-8')
    elif is_dataclass(obj) and not isinstance(obj, type):
        return json.dumps(asdict(obj)).encode('utf-8')
    elif isinstance(obj, dict):
        return json.dumps(obj).encode('utf-8')
    else:
        raise TypeError(f"Cannot serialize {type(obj)}")


def deserialize(data: bytes, cls: Type[T]) -> T:
    """
    Deserialize JSON bytes to a typed object.
    
    Args:
        data: UTF-8 encoded JSON bytes
        cls: Target class (Pydantic model or dataclass)
        
    Returns:
        Deserialized object
    """
    json_str = data.decode('utf-8')
    
    if issubclass(cls, BaseModel):
        return cls.model_validate_json(json_str)
    elif is_dataclass(cls):
        return cls(**json.loads(json_str))
    else:
        raise TypeError(f"Cannot deserialize to {cls}")


def deserialize_dict(data: bytes) -> dict:
    """Deserialize JSON bytes to a dictionary."""
    return json.loads(data.decode('utf-8'))
```

### Step 1.3: Zenoh Session Manager

Create `multirig/zenoh/session.py`:

```python
"""
Zenoh session management.

Provides a singleton session for the application and helpers for
common operations like publishing and subscribing.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Callable, Optional

import zenoh

logger = logging.getLogger(__name__)

# Global session instance
_session: Optional[zenoh.Session] = None


def get_session() -> zenoh.Session:
    """
    Get the global Zenoh session.
    
    Raises:
        RuntimeError: If session not initialized
    """
    if _session is None:
        raise RuntimeError("Zenoh session not initialized. Call init_session() first.")
    return _session


async def init_session(config: Optional[zenoh.Config] = None) -> zenoh.Session:
    """
    Initialize the global Zenoh session.
    
    Args:
        config: Optional Zenoh configuration. Uses defaults if not provided.
        
    Returns:
        The initialized session
    """
    global _session
    
    if _session is not None:
        logger.warning("Zenoh session already initialized")
        return _session
    
    # Create session (this is sync but fast)
    if config is None:
        config = zenoh.Config()
    
    _session = zenoh.open(config)
    logger.info("Zenoh session initialized")
    return _session


async def close_session():
    """Close the global Zenoh session."""
    global _session
    
    if _session is not None:
        _session.close()
        _session = None
        logger.info("Zenoh session closed")


@asynccontextmanager
async def session_lifespan():
    """
    Context manager for Zenoh session lifecycle.
    
    Use with FastAPI lifespan:
    
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with session_lifespan():
                yield
    """
    await init_session()
    try:
        yield get_session()
    finally:
        await close_session()


class Publisher:
    """
    Wrapper around Zenoh publisher with serialization.
    
    Example:
        pub = Publisher('multirig/rig/rig1/state')
        pub.publish(rig_state)
    """
    
    def __init__(self, key_expr: str):
        self.key_expr = key_expr
        self._publisher = None
    
    def _ensure_publisher(self):
        if self._publisher is None:
            session = get_session()
            self._publisher = session.declare_publisher(self.key_expr)
    
    def publish(self, data: object):
        """Publish serialized data to the key expression."""
        from .serialization import serialize
        
        self._ensure_publisher()
        payload = serialize(data)
        self._publisher.put(payload)
    
    def close(self):
        if self._publisher is not None:
            self._publisher.undeclare()
            self._publisher = None


class Subscriber:
    """
    Wrapper around Zenoh subscriber with async callback support.
    
    Example:
        async def on_state(sample):
            state = deserialize(sample.payload, RigState)
            print(state)
        
        sub = Subscriber('multirig/rig/*/state', on_state)
    """
    
    def __init__(self, key_expr: str, callback: Callable):
        self.key_expr = key_expr
        self.callback = callback
        self._subscriber = None
        self._loop = None
    
    def start(self):
        """Start the subscriber."""
        session = get_session()
        self._loop = asyncio.get_event_loop()
        
        def sync_callback(sample):
            # Schedule async callback on the event loop
            if asyncio.iscoroutinefunction(self.callback):
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self.callback(sample))
                )
            else:
                self.callback(sample)
        
        self._subscriber = session.declare_subscriber(self.key_expr, sync_callback)
    
    def stop(self):
        """Stop the subscriber."""
        if self._subscriber is not None:
            self._subscriber.undeclare()
            self._subscriber = None
```

### Step 1.4: Message Types

Create `multirig/messages/rig.py`:

```python
"""
Rig-related message types.

These are the core messages that flow through the Zenoh bus for rig control.
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class RigState:
    """
Current state of a rig.
    
    Published to: multirig/rig/{rig_id}/state
    """
    rig_id: str
    timestamp: float  # Unix timestamp
    connected: bool
    
    # Radio state
    frequency: Optional[int] = None      # Hz
    mode: Optional[str] = None           # USB, LSB, CW, FM, etc.
    bandwidth: Optional[int] = None      # Hz
    vfo: Optional[str] = None            # VFOA, VFOB
    ptt: Optional[bool] = None
    power_status: Optional[bool] = None
    
    # Error info
    error: Optional[str] = None
    
    @classmethod
    def disconnected(cls, rig_id: str, error: Optional[str] = None) -> 'RigState':
        """Create a disconnected state."""
        return cls(
            rig_id=rig_id,
            timestamp=datetime.now().timestamp(),
            connected=False,
            error=error
        )


@dataclass
class RigCommand:
    """
    Command to send to a rig.
    
    Published to: multirig/rig/{rig_id}/command
    """
    command_id: str              # UUID for tracking
    command_type: str            # set_frequency, set_mode, set_ptt, etc.
    source: str                  # Who sent it: api, sync, rigctl
    params: dict = field(default_factory=dict)
    
    @classmethod
    def set_frequency(cls, frequency: int, source: str = "api") -> 'RigCommand':
        """Create a set frequency command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_frequency",
            source=source,
            params={"frequency": frequency}
        )
    
    @classmethod
    def set_mode(cls, mode: str, bandwidth: Optional[int] = None, 
                 source: str = "api") -> 'RigCommand':
        """Create a set mode command."""
        params = {"mode": mode}
        if bandwidth is not None:
            params["bandwidth"] = bandwidth
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_mode",
            source=source,
            params=params
        )
    
    @classmethod
    def set_ptt(cls, ptt: bool, source: str = "api") -> 'RigCommand':
        """Create a set PTT command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_ptt",
            source=source,
            params={"ptt": ptt}
        )
    
    @classmethod
    def set_vfo(cls, vfo: str, source: str = "api") -> 'RigCommand':
        """Create a set VFO command."""
        return cls(
            command_id=str(uuid.uuid4()),
            command_type="set_vfo",
            source=source,
            params={"vfo": vfo}
        )


@dataclass
class RigCaps:
    """
    Rig capabilities.
    
    Published to: multirig/rig/{rig_id}/caps
    """
    rig_id: str
    model_id: int
    model_name: str
    manufacturer: str
    
    # Supported modes
    modes: list[str] = field(default_factory=list)
    
    # Supported filter widths (Hz)
    filters: list[int] = field(default_factory=list)
    
    # Feature flags
    has_ptt: bool = False
    has_split: bool = False
    has_power_control: bool = False
    has_get_level: bool = False
    
    # Frequency range
    min_frequency: Optional[int] = None
    max_frequency: Optional[int] = None
```

Create `multirig/messages/sync.py`:

```python
"""
Sync engine message types.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncState:
    """
Current state of the sync engine.
    
    Published to: multirig/sync/state
    """
    enabled: bool
    source_rig_id: Optional[str] = None
    follower_rig_ids: list[str] = field(default_factory=list)
    
    # What to sync
    sync_frequency: bool = True
    sync_mode: bool = True
    sync_ptt: bool = False
    
    # Current status
    last_sync_timestamp: Optional[float] = None
    error: Optional[str] = None
```

Create `multirig/messages/__init__.py`:

```python
"""Message type exports."""
from .rig import RigState, RigCommand, RigCaps
from .sync import SyncState

__all__ = ['RigState', 'RigCommand', 'RigCaps', 'SyncState']
```

### Step 1.5: Test the Infrastructure

Create `test_phase1.py`:

```python
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
```

### Checklist for Phase 1:
- [x] `multirig/zenoh/keys.py` created with key expressions
- [x] `multirig/zenoh/serialization.py` created
- [x] `multirig/zenoh/session.py` created
- [x] `multirig/messages/rig.py` created with RigState, RigCommand, RigCaps
- [x] `multirig/messages/sync.py` created with SyncState
- [x] Phase 1 tests pass

---

## Phase 2: Rig Adapters

**Goal:** Create rig adapters that bridge hamlib to Zenoh, including managed processes and safety checks.

### Step 2.1: Copy Hamlib Utilities

Copy the hamlib message parsing from the old code:

```bash
cp old/multirig/hamlib/*.py multirig/hamlib/
```

### Step 2.2: Port Capabilities Parsing

Create `multirig/hamlib/caps.py` by porting the logic from `old/multirig/rig/common.py` (specifically `parse_dump_caps`). This is essential for populating `RigCaps`.

```python
"""
Capabilities parsing logic ported from legacy code.
"""
def parse_dump_caps(text: str) -> tuple[dict[str, bool], list[str]]:
    """Parse rig capabilities from dump_caps output."""
    # ... implementation from old/multirig/rig/common.py ...
    pass
```

### Step 2.3: Base Adapter Interface (with Safety Checks)

Create `multirig/adapters/base.py`.
**Crucial Update:** Add a `_check_safety(command)` method that adapters call before execution. This should check against band limits if configured (will need access to RigConfig).

```python
class BaseRigAdapter(ABC):
    # ... existing init ...
    
    async def _on_command(self, sample):
        # ... deserialization ...
        if self._connected:
             # Safety Check
             if not self._check_safety(command):
                 logger.warning(f"Command blocked by safety check: {command}")
                 return
             await self._execute_command(command)
```

### Step 2.4: Rigctld TCP Adapter

Create `multirig/adapters/rigctld.py` as defined previously, ensuring it uses the new `RigCaps` populated via `dump_caps`.

### Step 2.5: Managed Process Adapter (Replaces "Process" Adapter)

Create `multirig/adapters/managed.py`.
This adapter must:
1.  Spawn `rigctld` as a subprocess (like `old/multirig/rig/managed.py`).
2.  Wait for it to bind to a port.
3.  Instantiate a `RigctldAdapter` (from step 2.4) to talk to it.
4.  Manage the subprocess lifecycle (kill on stop).

This is preferred over direct stdin/stdout interaction as it leverages the stable TCP protocol.

### Step 2.6: Test the Adapters

Create `test_phase2.py` covering both direct TCP and managed process adapters.

### Checklist for Phase 2:
- [x] Hamlib utilities copied
- [x] `multirig/hamlib/caps.py` created
- [x] `multirig/adapters/base.py` created with safety hooks
- [x] `multirig/adapters/rigctld.py` created
- [x] `multirig/adapters/managed.py` created
- [x] Adapter tests pass

---

## Phase 3: Sync Engine

**Goal:** Implement the sync engine that propagates changes from source to followers.

### Step 3.1: Create Sync Engine

Create `multirig/engines/sync.py`. (Same as previous plan).

### Checklist for Phase 3:
- [x] `multirig/engines/sync.py` created
- [x] Sync engine tests pass

---

## Phase 4: API Gateway

**Goal:** Create REST and WebSocket APIs that bridge HTTP to Zenoh.

### Step 4.1: REST Routes
### Step 4.2: WebSocket Handler
### Step 4.3: Main App

(Same as previous plan).

### Checklist for Phase 4:
- [x] API Gateway components created
- [x] WebSocket streaming works

---

## Phase 5: Rigctl Server (External App Support)

**Goal:** TCP server that allows WSJT-X and similar apps to connect.

### Step 5.1: Port Legacy Command Map

The `RigctlServer` must implement the full command map found in `old/multirig/rig/server.py`.
This includes stubs for:
- `dump_caps` (return simplified caps or forward from Zenoh)
- `get_level` (return 0)
- `chk_vfo`
- `dump_state`
- `get_powerstat`

Create `multirig/rigctl_server/server.py` that imports `RigctlServer` logic but adapts it to query Zenoh for state instead of holding a direct reference to a `RigClient`.

**Optimistic Updates:**
When receiving a `set_freq` command via TCP, the server should publish the command to Zenoh AND immediately update its local cached state for that rig. This ensures that a subsequent `get_freq` from WSJT-X returns the new value immediately, preventing "jumping" in the UI.

### Checklist for Phase 5:
- [ ] `multirig/rigctl_server/server.py` created with FULL command map
- [ ] Server responds to WSJT-X initialization commands without error
- [ ] WSJT-X can control frequency

---

## Phase 6: Configuration and Profiles

**Goal:** Add configuration persistence and profile management.

### Key Tasks:
- [ ] Copy config models from old code (`old/multirig/config.py`)
- [ ] Ensure `RigConfig` includes band limits (`allow_out_of_band`, `band_presets`)
- [ ] Add config queryable to Zenoh
- [ ] Implement profile switching

---

## Phase 7: Integration and Polish

**Goal:** Bring everything together.

### Key Tasks:
- [ ] Create main entry point
- [ ] Wire up config to create `ManagedRigAdapter` or `RigctldAdapter` based on config
- [ ] Connect frontend
- [ ] Verify band limit safety

---

## Phase 8: Rig Discovery

**Goal:** Implement hybrid discovery.

### Step 8.1: Discovery Message Types

Add to `multirig/messages/config.py`:

```python
"""
Configuration-related message types.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DiscoveredRig:
    """Info about a rig discovered on the bus but not in config."""
    rig_id: str
    first_seen: float
    last_seen: float
    connected: bool
    model_name: Optional[str] = None


@dataclass
class ConfigDiscovered:
    """
    List of rigs discovered on the bus but not in config.
    
    Published to: multirig/config/discovered
    """
    discovered_rigs: list[DiscoveredRig] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class ConfigChanged:
    """
    Notification that configuration has changed.
    
    Published to: multirig/config/changed
    
    Components subscribe to this to react to config changes:
    - Sync Engine: updates follower list when rigs added/removed
    - API Gateway: refreshes state for frontend
    """
    change_type: str  # "rig_added", "rig_removed", "rig_updated", "sync_updated"
    rig_id: Optional[str] = None
    timestamp: float = 0.0
```

### Step 8.2: Add Discovery Keys

Update `multirig/zenoh/keys.py`:

```python
# Add these new keys for discovery
CONFIG_DISCOVERED = f"{PREFIX}/config/discovered"
CONFIG_CHANGED = f"{PREFIX}/config/changed"
```

### Step 8.3: Discovery in Config Store

Update `multirig/engines/config_store.py` to add discovery logic:

```python
"""
Config store with rig discovery.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Set

from multirig.messages import RigState
from multirig.messages.config import DiscoveredRig, ConfigDiscovered, ConfigChanged
from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Publisher, Subscriber
from multirig.zenoh.serialization import serialize, deserialize

logger = logging.getLogger(__name__)


class ConfigStore:
    """
    Manages configuration and discovers new rigs.
    
    The Config Store:
    1. Loads/saves configuration from YAML
    2. Watches for new rigs on the Zenoh bus
    3. Publishes discovered rigs for the UI
    4. Publishes config change notifications
    """
    
    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        
        # Known rig IDs from config
        self._configured_rig_ids: Set[str] = set()
        
        # Discovered rigs (not in config)
        self._discovered_rigs: dict[str, DiscoveredRig] = {}
        
        # Zenoh
        self._state_subscriber: Optional[Subscriber] = None
        self._discovered_publisher: Optional[Publisher] = None
        self._changed_publisher: Optional[Publisher] = None
    
    def load_config(self):
        """Load configuration and populate configured_rig_ids."""
        # TODO: Load from YAML file
        # For now, start with empty config
        self._configured_rig_ids = set()
    
    def add_rig_to_config(self, rig_id: str, rig_config: dict):
        """
        Add a rig to the configuration.
        
        Called when user clicks "Add" on a discovered rig.
        """
        self._configured_rig_ids.add(rig_id)
        
        # Remove from discovered
        if rig_id in self._discovered_rigs:
            del self._discovered_rigs[rig_id]
            self._publish_discovered()
        
        # TODO: Save to YAML
        
        # Notify other components
        self._publish_changed("rig_added", rig_id)
    
    def remove_rig_from_config(self, rig_id: str):
        """Remove a rig from the configuration."""
        self._configured_rig_ids.discard(rig_id)
        
        # TODO: Save to YAML
        
        # Notify other components
        self._publish_changed("rig_removed", rig_id)
    
    async def start(self):
        """Start the config store and discovery."""
        logger.info("Starting config store with discovery")
        
        self.load_config()
        
        # Publishers
        self._discovered_publisher = Publisher(keys.CONFIG_DISCOVERED)
        self._changed_publisher = Publisher(keys.CONFIG_CHANGED)
        
        # Subscribe to all rig states for discovery
        self._state_subscriber = Subscriber(
            keys.RIG_STATE_ALL,
            self._on_rig_state
        )
        self._state_subscriber.start()
        
        # Publish initial discovered list (empty)
        self._publish_discovered()
    
    async def stop(self):
        """Stop the config store."""
        if self._state_subscriber:
            self._state_subscriber.stop()
        if self._discovered_publisher:
            self._discovered_publisher.close()
        if self._changed_publisher:
            self._changed_publisher.close()
    
    async def _on_rig_state(self, sample):
        """Handle rig state - check if it's a new discovery."""
        try:
            state = deserialize(sample.payload.to_bytes(), RigState)
            rig_id = state.rig_id
            
            # Skip if already configured
            if rig_id in self._configured_rig_ids:
                return
            
            now = datetime.now().timestamp()
            
            # Update or create discovered rig entry
            if rig_id in self._discovered_rigs:
                # Update existing
                self._discovered_rigs[rig_id].last_seen = now
                self._discovered_rigs[rig_id].connected = state.connected
            else:
                # New discovery!
                logger.info(f"Discovered new rig: {rig_id}")
                self._discovered_rigs[rig_id] = DiscoveredRig(
                    rig_id=rig_id,
                    first_seen=now,
                    last_seen=now,
                    connected=state.connected,
                    model_name=None  # Will be updated from caps
                )
                self._publish_discovered()
                
        except Exception as e:
            logger.error(f"Error in discovery: {e}")
    
    def _publish_discovered(self):
        """Publish the current discovered rigs list."""
        if self._discovered_publisher:
            msg = ConfigDiscovered(
                discovered_rigs=list(self._discovered_rigs.values()),
                timestamp=datetime.now().timestamp()
            )
            self._discovered_publisher.publish(msg)
    
    def _publish_changed(self, change_type: str, rig_id: Optional[str] = None):
        """Publish a config change notification."""
        if self._changed_publisher:
            msg = ConfigChanged(
                change_type=change_type,
                rig_id=rig_id,
                timestamp=datetime.now().timestamp()
            )
            self._changed_publisher.publish(msg)
```

### Step 8.4: Sync Engine Reacts to Config Changes

Update `multirig/engines/sync.py` to subscribe to config changes:

```python
# Add to SyncEngine.__init__:
self._config_subscriber: Optional[Subscriber] = None

# Add to SyncEngine.start():
self._config_subscriber = Subscriber(
    keys.CONFIG_CHANGED,
    self._on_config_changed
)
self._config_subscriber.start()

# Add new method:
async def _on_config_changed(self, sample):
    """React to configuration changes."""
    try:
        change = deserialize(sample.payload.to_bytes(), ConfigChanged)
        
        if change.change_type == "rig_added" and change.rig_id:
            # New rig available - could be added as follower
            logger.info(f"New rig available: {change.rig_id}")
            # Don't auto-add - user must explicitly configure as follower
            
        elif change.change_type == "rig_removed" and change.rig_id:
            # Rig removed - remove from followers if present
            if change.rig_id in self.follower_rig_ids:
                self.remove_follower(change.rig_id)
            if change.rig_id == self.source_rig_id:
                self.set_source(None)
            
    except Exception as e:
        logger.error(f"Error handling config change: {e}")
```

### Step 8.5: API Endpoints for Discovery

Add to `multirig/gateway/routes.py`:

```python
from multirig.messages.config import ConfigDiscovered

@router.get("/rigs/discovered")
async def get_discovered_rigs() -> dict:
    """Get list of discovered (unconfigured) rigs."""
    session = get_session()
    
    # Query the latest discovered list
    replies = session.get(keys.CONFIG_DISCOVERED)
    
    for reply in replies:
        if reply.ok:
            discovered = deserialize(reply.ok.payload.to_bytes(), ConfigDiscovered)
            return {
                "discovered_rigs": [
                    {
                        "rig_id": r.rig_id,
                        "first_seen": r.first_seen,
                        "last_seen": r.last_seen,
                        "connected": r.connected,
                        "model_name": r.model_name
                    }
                    for r in discovered.discovered_rigs
                ]
            }
    
    return {"discovered_rigs": []}


@router.post("/rigs/{rig_id}/add")
async def add_discovered_rig(rig_id: str):
    """Add a discovered rig to the configuration."""
    # This would call config_store.add_rig_to_config()
    # For now, publish a command to the config store
    session = get_session()
    
    # TODO: Implement proper config store interaction
    # Could use a Zenoh queryable or direct method call
    
    return {"status": "ok", "message": f"Rig {rig_id} added to config"}
```

### Step 8.6: Frontend Discovery UI

The frontend should:
1.  Subscribe to `multirig/config/discovered` via WebSocket
2.  Display discovered rigs in a separate "Available Rigs" section
3.  Provide an "Add" button for each discovered rig
4.  Move rig to "Configured Rigs" after adding

Example UI flow:
```
┌─────────────────────────────────────────┐
│ Configured Rigs                         │
│ ┌─────────────────────────────────────┐ │
│ │ Rig 1 (IC-7300) - 14.074.000 USB   │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ Discovered Rigs (click to add)          │
│ ┌─────────────────────────────────────┐ │
│ │ rig3 - Connected        [+ Add]    │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘
```

### Checklist for Phase 8:
- [ ] `multirig/messages/config.py` created with discovery messages
- [ ] Discovery keys added to `multirig/zenoh/keys.py`
- [ ] `ConfigStore` updated with discovery logic
- [ ] `SyncEngine` reacts to config changes
- [ ] REST endpoints for discovered rigs
- [ ] Frontend shows discovered rigs with "Add" button
- [ ] Adding a discovered rig moves it to configured list

---

## Next Steps After Implementation

1.  **Performance tuning**: Adjust poll intervals, debounce times
2.  **Error recovery**: Add reconnection logic, circuit breakers
3.  **Monitoring**: Add metrics, health checks
4.  **Frontend updates**: Update JS to use new API endpoints
5.  **Documentation**: Update README, add API docs