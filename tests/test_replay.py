import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from multirig.rigctl_tcp import RigctlServer, RigctlServerConfig
from multirig.rig import RigClient, RigConfig

def parse_dump(path):
    transactions = []
    current_tx = None
    
    with open(path, 'r') as f:
        lines = f.readlines()
        
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "C->S" in line:
            # New command
            # Extract command part: "[...] C->S <len> bytes: <cmd>"
            parts = line.split(" bytes: ", 1)
            if len(parts) == 2:
                cmd = parts[1]
                if current_tx:
                    transactions.append(current_tx)
                current_tx = {'cmd': cmd, 'response': []}
        elif "S->C" in line:
            # Response header. The content follows, potentially starting inline.
            parts = line.split(" bytes: ", 1)
            if len(parts) == 2 and parts[1]:
                current_tx['response'].append(parts[1])
        elif current_tx is not None:
            # Body lines. Exclude log headers or direction markers.
            if not ("[" in line and "]" in line and ("C->S" in line or "S->C" in line or "New connection" in line or "Forwarding" in line or "Listening" in line)):
                 current_tx['response'].append(line)
        i += 1
        
    if current_tx:
        transactions.append(current_tx)
        
    return transactions

@pytest.mark.asyncio
async def test_replay_traffic():
    dump_path = "scripts/tcp_dump.txt"
    transactions = parse_dump(dump_path)
    
    # Mock RigClient
    mock_rig = MagicMock(spec=RigClient)
    mock_rig.cfg = MagicMock()
    mock_rig.cfg.enabled = True
    mock_rig.cfg.follow_main = True
    
    # Mock responses to match what the server logic expects.
    # Where the server wraps the response, we mock the raw inner response.
    
    async def mock_execute(cmd_key):
        pass

    # Setup mocks
    mock_rig.get_powerstat = AsyncMock(return_value="1")
    mock_rig.chk_vfo = AsyncMock(return_value="0") # Expect "0" from server

    # Extract dump_state response
    dump_state_lines = []
    for t in transactions:
        if "dump_state" in t['cmd']:
            dump_state_lines = t['response']
            break

    mock_rig.dump_state = AsyncMock(return_value=dump_state_lines)    
    mock_rig.get_level = AsyncMock(return_value="0")
    mock_rig.get_frequency = AsyncMock(return_value=18100000)
    mock_rig.get_split = AsyncMock(return_value=(0, "None"))
    mock_rig.get_vfo = AsyncMock(return_value="None")
    mock_rig.get_mode = AsyncMock(return_value=("FM", 15000))

    rigs = [mock_rig]
    rigs = [mock_rig]
    
    class TestRigctlServer(RigctlServer):
        def get_rigs(self):
            return rigs
        def get_source_index(self):
            return 0

    server = TestRigctlServer(
        config=RigctlServerConfig(host="127.0.0.1", port=0)
    )
    
    # Run transactions
    for t in transactions:
        cmd = t['cmd']
        expected_lines = t['response']
        if "New connection" in cmd: continue
        
        # Validate dump_state separately
        if "dump_state" in cmd:
            resp = await server._handle_command_line(cmd)
            resp_str = resp.decode()
            assert resp_str.startswith("1")
            assert "rig_model=1" in resp_str
            assert resp_str.strip().endswith("done")
            continue
            
        # Execute command
        resp = await server._handle_command_line(cmd)
        resp_str = resp.decode().strip()
        expected = "\n".join(expected_lines).strip()
        
        if cmd == "f" or cmd == "\\f":
             assert resp_str == "18100000"
        elif "chk_vfo" in cmd:
             assert resp_str == expected
        elif "get_powerstat" in cmd:
             assert resp_str == expected
        elif cmd.startswith("l "):
             assert resp_str == expected
        elif cmd == "m":
             assert resp_str == expected
        elif cmd == "s":
             assert resp_str == expected

