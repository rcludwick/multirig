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
            # Response header
            # The actual content follows in subsequent lines, or is inline?
            # Example: "[...] S->C 2 bytes: 1"
            parts = line.split(" bytes: ", 1)
            if len(parts) == 2 and parts[1]:
                # Inline content
                current_tx['response'].append(parts[1])
            # If large response, content is on following lines?
            # Example dump_state has content on following lines.
            # We need to look ahead.
        elif current_tx is not None:
            # Continuation of response?
            # Lines 10-73 in dump seem to be continuation.
            # We treat them as part of the response body.
            # But we must exclude log lines like "[...] New connection" or "C->S"
            if not ("[" in line and "]" in line and ("C->S" in line or "S->C" in line or "New connection" in line or "Forwarding" in line or "Listening" in line)):
                 # It's content (unless it's blank line at end?)
                 # The dump has newlines. We should preserve them?
                 # parse_dump logic needs to be robust.
                 # Actually, looking at the dump, the lines 10-73 are raw content lines.
                 # line 9 is "S->C ... bytes: 1".
                 # So "1" is the first line.
                 # Then "1", "0", etc.
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
    
    # We need to mock the methods called by RigctlTcpServer
    # dump_state, chk_vfo, etc.
    # The responses in the dump are what the server returned.
    # So if server logic wraps them, we expect the wrapped result.
    # But if server logic is just forwarding, the rig must return the raw data.
    
    # Configure mock responses based on commands
    async def mock_execute(cmd_key):
        # Find matching transaction?
        # This is hard because we are iterating.
        # We'll just configure specific mocks.
        pass

    # Setup specific mocks based on dump analysis
    # \get_powerstat -> 1
    mock_rig.get_powerstat = AsyncMock(return_value="1")
    
    # \chk_vfo -> 0
    # dump shows "0" response from server. 
    # If server adds "CHKVFO", then rig returned something else?
    # Or server just returns "0"?
    # If \chk_vfo is standard command, response is standard.
    mock_rig.chk_vfo = AsyncMock(return_value="0")
    
    # \dump_state -> huge blob
    # We will grab the blob from the parsed transactions
    dump_state_lines = []
    for t in transactions:
        if "dump_state" in t['cmd']:
            dump_state_lines = t['response']
            break

    mock_rig.dump_state = AsyncMock(return_value=dump_state_lines) # Rig usually returns string    
    # l KEYSPD -> 0
    # Command key 'l', args ['KEYSPD']
    mock_rig.get_level = AsyncMock(return_value="0")
    
    # f -> 18100000
    mock_rig.get_frequency = AsyncMock(return_value=18100000)
    
    # s -> 0 (get_split?)
    # Expects tuple (enabled, vfo)
    # Dump shows response "0\nNone", so vfo should be "None"
    mock_rig.get_split = AsyncMock(return_value=(0, "None"))
    mock_rig.get_vfo = AsyncMock(return_value="None")

    # m -> FM 15000
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
        # Reconstruct expected bytes
        # If response lines are ["1"], bytes is b"1\n" (readline adds newline usually?)
        # The dump strips newlines probably.
        # Let's verify what server returns.
        
        # Skip some setup noise in dump
        if "New connection" in cmd: continue
        
        # Handle command
        # cmd might be "\get_powerstat"
        
        # Special handling for dump_state validation due to size
        if "dump_state" in cmd:
            resp = await server._handle_command_line(cmd)
            resp_str = resp.decode()
            # Verify it starts with 1
            assert resp_str.startswith("1")
            assert "rig_model=1" in resp_str
            assert resp_str.strip().endswith("done")
            continue
            
        # Run
        resp = await server._handle_command_line(cmd)
        resp_str = resp.decode().strip()
        
        # Join expected lines
        # dump "S->C 2 bytes: 1" -> line is "1"
        # multi line response?
        expected = "\n".join(expected_lines).strip()
        
        # Loose comparison for now to identify gaps
        # print(f"CMD: {cmd} -> GOT: {resp_str!r} EXPECT: {expected!r}")
        
        # For 'f' command, dump shows "18100000". Server get_freq returns "18100000" (if mocked)
        if cmd == "f" or cmd == "\\f":
             assert resp_str == "18100000"
        elif "chk_vfo" in cmd:
             # Dump says "0". Server currently returns "CHKVFO 0" or "0"?
             # We want to verify what it currently does vs expectation.
             # If expectation is "0", we need to adjust server.
             assert resp_str == expected
        elif "get_powerstat" in cmd:
             assert resp_str == expected
        elif cmd.startswith("l "):
             # l KEYSPD
             assert resp_str == expected
        elif cmd == "m":
             assert resp_str == expected
        elif cmd == "s":
             assert resp_str == expected

