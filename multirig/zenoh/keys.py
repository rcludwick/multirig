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
