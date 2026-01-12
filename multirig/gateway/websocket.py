"""
WebSocket handler for real-time updates.

Streams rig state changes and sync updates to connected WebSocket clients.
"""
import asyncio
import json
import logging
from typing import Set
from fastapi import WebSocket, WebSocketDisconnect

from multirig.zenoh import keys
from multirig.zenoh.session import get_session, Subscriber
from multirig.zenoh.serialization import deserialize
from multirig.messages import RigState, SyncState

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and streams Zenoh updates.
    
    Subscribes to Zenoh topics and broadcasts updates to all connected
    WebSocket clients.
    """
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._state_subscriber: Subscriber = None
        self._sync_subscriber: Subscriber = None
        self._started = False
    
    async def start(self):
        """Start subscribing to Zenoh topics."""
        if self._started:
            return
        
        logger.info("Starting WebSocket manager")
        
        # Subscribe to all rig states
        self._state_subscriber = Subscriber(
            keys.RIG_STATE_ALL,
            self._on_rig_state
        )
        self._state_subscriber.start()
        
        # Subscribe to sync state
        self._sync_subscriber = Subscriber(
            keys.SYNC_STATE,
            self._on_sync_state
        )
        self._sync_subscriber.start()
        
        self._started = True
        logger.info("WebSocket manager started")
    
    async def stop(self):
        """Stop subscribing and close all connections."""
        if not self._started:
            return
        
        logger.info("Stopping WebSocket manager")
        
        # Stop subscribers
        if self._state_subscriber:
            self._state_subscriber.stop()
        if self._sync_subscriber:
            self._sync_subscriber.stop()
        
        # Close all connections
        for connection in list(self.active_connections):
            await connection.close()
        self.active_connections.clear()
        
        self._started = False
        logger.info("WebSocket manager stopped")
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total clients: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")
    
    async def _on_rig_state(self, sample):
        """Handle rig state updates from Zenoh."""
        try:
            state = deserialize(sample.payload.to_bytes(), RigState)
            
            # Broadcast to all connected clients
            message = {
                "type": "rig_state",
                "data": {
                    "rig_id": state.rig_id,
                    "timestamp": state.timestamp,
                    "connected": state.connected,
                    "frequency": state.frequency,
                    "mode": state.mode,
                    "bandwidth": state.bandwidth,
                    "vfo": state.vfo,
                    "ptt": state.ptt,
                    "power_status": state.power_status,
                    "error": state.error
                }
            }
            
            await self._broadcast(message)
            
        except Exception as e:
            logger.error(f"Error handling rig state in WebSocket manager: {e}")
    
    async def _on_sync_state(self, sample):
        """Handle sync state updates from Zenoh."""
        try:
            state = deserialize(sample.payload.to_bytes(), SyncState)
            
            # Broadcast to all connected clients
            message = {
                "type": "sync_state",
                "data": {
                    "enabled": state.enabled,
                    "source_rig_id": state.source_rig_id,
                    "follower_rig_ids": state.follower_rig_ids,
                    "sync_frequency": state.sync_frequency,
                    "sync_mode": state.sync_mode,
                    "sync_ptt": state.sync_ptt,
                    "last_sync_timestamp": state.last_sync_timestamp,
                    "error": state.error
                }
            }
            
            await self._broadcast(message)
            
        except Exception as e:
            logger.error(f"Error handling sync state in WebSocket manager: {e}")
    
    async def _broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        if not self.active_connections:
            return
        
        json_message = json.dumps(message)
        
        # Send to all clients, removing any that fail
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json_message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")
                disconnected.append(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self.disconnect(connection)
    
    async def send_to_client(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending to WebSocket client: {e}")
            self.disconnect(websocket)


# Global WebSocket manager instance
ws_manager = WebSocketManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint handler.
    
    Usage:
        app.add_websocket_route("/ws", websocket_endpoint)
    """
    await ws_manager.connect(websocket)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()
            
            # Handle client messages (e.g., subscribe to specific rigs)
            try:
                message = json.loads(data)
                
                # Echo back for now (could implement subscription filtering)
                await ws_manager.send_to_client(websocket, {
                    "type": "ack",
                    "message": "Message received"
                })
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from WebSocket client: {data}")
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
