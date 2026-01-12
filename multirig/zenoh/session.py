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
