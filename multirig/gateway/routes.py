"""
REST API routes for MultiRig.

Provides HTTP endpoints that interact with the Zenoh bus.
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from multirig.zenoh import keys
from multirig.zenoh.session import get_session
from multirig.zenoh.serialization import serialize, deserialize, deserialize_dict
from multirig.messages import RigState, RigCommand, RigCaps, SyncState

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response models

class FrequencyRequest(BaseModel):
    frequency: int


class ModeRequest(BaseModel):
    mode: str
    bandwidth: Optional[int] = None


class PTTRequest(BaseModel):
    ptt: bool


class VFORequest(BaseModel):
    vfo: str


class SyncConfigRequest(BaseModel):
    enabled: bool
    source_rig_id: Optional[str] = None
    follower_rig_ids: List[str] = []
    sync_frequency: bool = True
    sync_mode: bool = True
    sync_ptt: bool = False


# Rig control endpoints

@router.get("/api/rigs")
async def list_rigs() -> Dict[str, Any]:
    """Get list of all known rigs with their current states."""
    # Query all rig states
    # Note: This is a simplified implementation
    # A real implementation might track rig list in config
    return {
        "rigs": [],
        "message": "Rig discovery not yet implemented - use config to add rigs"
    }


@router.get("/api/rigs/{rig_id}/state")
async def get_rig_state(rig_id: str) -> Dict[str, Any]:
    """Get current state of a specific rig."""
    try:
        session = get_session()
        
        # Query the latest state for this rig
        # Note: Zenoh get() returns the latest published value
        replies = session.get(keys.rig_state_key(rig_id), timeout=1.0)
        
        for reply in replies:
            if reply.ok:
                state = deserialize(reply.ok.payload.to_bytes(), RigState)
                return {
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
        
        raise HTTPException(status_code=404, detail=f"Rig {rig_id} not found or no state available")
        
    except Exception as e:
        logger.error(f"Error getting rig state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/rigs/{rig_id}/caps")
async def get_rig_caps(rig_id: str) -> Dict[str, Any]:
    """Get capabilities of a specific rig."""
    try:
        session = get_session()
        
        replies = session.get(keys.rig_caps_key(rig_id), timeout=1.0)
        
        for reply in replies:
            if reply.ok:
                caps = deserialize(reply.ok.payload.to_bytes(), RigCaps)
                return {
                    "rig_id": caps.rig_id,
                    "model_id": caps.model_id,
                    "model_name": caps.model_name,
                    "manufacturer": caps.manufacturer,
                    "modes": caps.modes,
                    "filters": caps.filters,
                    "has_ptt": caps.has_ptt,
                    "has_split": caps.has_split,
                    "has_power_control": caps.has_power_control,
                    "has_get_level": caps.has_get_level,
                    "min_frequency": caps.min_frequency,
                    "max_frequency": caps.max_frequency
                }
        
        raise HTTPException(status_code=404, detail=f"Capabilities for rig {rig_id} not found")
        
    except Exception as e:
        logger.error(f"Error getting rig caps: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rigs/{rig_id}/frequency")
async def set_rig_frequency(rig_id: str, request: FrequencyRequest) -> Dict[str, str]:
    """Set frequency of a specific rig."""
    try:
        session = get_session()
        
        # Create and publish command
        cmd = RigCommand.set_frequency(request.frequency, source="api")
        session.put(keys.rig_command_key(rig_id), serialize(cmd))
        
        return {"status": "ok", "message": f"Frequency command sent to {rig_id}"}
        
    except Exception as e:
        logger.error(f"Error setting frequency: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rigs/{rig_id}/mode")
async def set_rig_mode(rig_id: str, request: ModeRequest) -> Dict[str, str]:
    """Set mode of a specific rig."""
    try:
        session = get_session()
        
        # Create and publish command
        cmd = RigCommand.set_mode(request.mode, request.bandwidth, source="api")
        session.put(keys.rig_command_key(rig_id), serialize(cmd))
        
        return {"status": "ok", "message": f"Mode command sent to {rig_id}"}
        
    except Exception as e:
        logger.error(f"Error setting mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rigs/{rig_id}/ptt")
async def set_rig_ptt(rig_id: str, request: PTTRequest) -> Dict[str, str]:
    """Set PTT of a specific rig."""
    try:
        session = get_session()
        
        # Create and publish command
        cmd = RigCommand.set_ptt(request.ptt, source="api")
        session.put(keys.rig_command_key(rig_id), serialize(cmd))
        
        return {"status": "ok", "message": f"PTT command sent to {rig_id}"}
        
    except Exception as e:
        logger.error(f"Error setting PTT: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/rigs/{rig_id}/vfo")
async def set_rig_vfo(rig_id: str, request: VFORequest) -> Dict[str, str]:
    """Set VFO of a specific rig."""
    try:
        session = get_session()
        
        # Create and publish command
        cmd = RigCommand.set_vfo(request.vfo, source="api")
        session.put(keys.rig_command_key(rig_id), serialize(cmd))
        
        return {"status": "ok", "message": f"VFO command sent to {rig_id}"}
        
    except Exception as e:
        logger.error(f"Error setting VFO: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Sync endpoints

@router.get("/api/sync/state")
async def get_sync_state() -> Dict[str, Any]:
    """Get current sync engine state."""
    try:
        session = get_session()
        
        replies = session.get(keys.SYNC_STATE, timeout=1.0)
        
        for reply in replies:
            if reply.ok:
                state = deserialize(reply.ok.payload.to_bytes(), SyncState)
                return {
                    "enabled": state.enabled,
                    "source_rig_id": state.source_rig_id,
                    "follower_rig_ids": state.follower_rig_ids,
                    "sync_frequency": state.sync_frequency,
                    "sync_mode": state.sync_mode,
                    "sync_ptt": state.sync_ptt,
                    "last_sync_timestamp": state.last_sync_timestamp,
                    "error": state.error
                }
        
        # Return default state if not found
        return {
            "enabled": False,
            "source_rig_id": None,
            "follower_rig_ids": [],
            "sync_frequency": True,
            "sync_mode": True,
            "sync_ptt": False,
            "last_sync_timestamp": None,
            "error": None
        }
        
    except Exception as e:
        logger.error(f"Error getting sync state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/sync/configure")
async def configure_sync(request: SyncConfigRequest) -> Dict[str, str]:
    """
    Configure the sync engine.
    
    Note: This requires the sync engine to subscribe to a config topic.
    For now, this is a placeholder that would need to publish to a
    sync/configure topic that the sync engine watches.
    """
    try:
        # TODO: Implement sync engine configuration via Zenoh
        # This would publish to a multirig/sync/configure topic
        # that the sync engine subscribes to
        
        return {
            "status": "ok",
            "message": "Sync configuration endpoint not yet fully implemented"
        }
        
    except Exception as e:
        logger.error(f"Error configuring sync: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check

@router.get("/api/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    try:
        session = get_session()
        return {"status": "ok", "zenoh": "connected"}
    except Exception as e:
        return {"status": "error", "zenoh": str(e)}


# Status endpoint for backward compatibility

@router.get("/api/status")
async def get_status() -> Dict[str, Any]:
    """
    Get overall system status.
    
    This provides a simplified view of all rigs and sync state.
    """
    try:
        # Get sync state
        sync_state = await get_sync_state()
        
        return {
            "sync": sync_state,
            "rigs": {},  # Would need to track rig list
            "timestamp": None
        }
        
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
