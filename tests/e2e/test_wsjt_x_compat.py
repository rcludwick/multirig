"""
WSJT-X Compatibility Test

This test verifies that MultiRig correctly handles the rigctl protocol
commands that WSJT-X sends during typical operation.

Based on analysis of real WSJT-X traffic, this test covers:
- Initial connection and capability queries (dump_state, chk_vfo, get_powerstat)
- VFO queries
- Frequency get/set operations
- Mode queries
- PTT operations
- Split VFO queries

The test sends commands directly to MultiRig's rigctl server and validates responses.
"""
import pytest
import socket
import time
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager, FakeRigctld


class RigctlClient:
    """Simple rigctl protocol client for testing."""

    def __init__(self, host='127.0.0.1', port=4534):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        """Establish connection to rigctl server."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(5.0)
        self.sock.connect((self.host, self.port))

    def disconnect(self):
        """Close connection."""
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def send_command(self, cmd: str) -> str:
        """Send command and receive response."""
        if not self.sock:
            raise RuntimeError("Not connected")

        # Send command with newline
        self.sock.sendall(f"{cmd}\n".encode())

        # Receive response (read until we get data, handle multi-line)
        response = b""
        start_time = time.time()

        while time.time() - start_time < 2.0:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                response += chunk

                # For most commands, we expect RPRT or a value ending in \n
                # Simple heuristic: if we got data and it ends with \n, we're done
                if response and response.endswith(b'\n'):
                    break
            except socket.timeout:
                break

        return response.decode('utf-8', errors='ignore')

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


def test_wsjt_x_initialization_sequence(page: Page, profile_manager: ProfileManager):
    """
    Test the typical WSJT-X initialization sequence.

    When WSJT-X connects to a rig, it sends:
    1. get_powerstat - Check if rig is powered on
    2. chk_vfo - Check VFO capabilities
    3. dump_state - Get full rig capabilities
    """
    profile_name = "test_wsjt_x_init"

    # Create a fake rig with specific capabilities
    fake_rig = FakeRigctld(frequency=145000000, mode='FM', passband=15000)

    config = {
        "rigs": [{
            "name": "WSJT-X Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)

        # Wait for rig to connect
        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        # Test initialization sequence
        with RigctlClient() as client:
            # 1. Check power status
            resp = client.send_command('\\get_powerstat')
            assert '1' in resp, f"Expected power on (1), got: {resp}"

            # 2. Check VFO
            resp = client.send_command('\\chk_vfo')
            assert '0' in resp, f"Expected VFO check success (0), got: {resp}"

            # 3. Dump state (just verify we get a response, not empty)
            resp = client.send_command('\\dump_state')
            assert len(resp) > 10, f"Expected dump_state response, got: {resp}"
            # Response may contain "stub" (FakeRigctld) or "done" (real rig) or just data
            assert len(resp.strip()) > 0, f"Expected non-empty dump_state, got: {resp}"

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)


def test_wsjt_x_frequency_operations(page: Page, profile_manager: ProfileManager):
    """
    Test frequency get/set operations typical of WSJT-X.

    WSJT-X frequently:
    - Gets current frequency
    - Sets frequency when user changes band
    - Polls frequency to detect external changes
    """
    profile_name = "test_wsjt_x_freq"

    fake_rig = FakeRigctld(frequency=14074000, mode='USB', passband=2400)

    config = {
        "rigs": [{
            "name": "WSJT-X Freq Test",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)

        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        with RigctlClient() as client:
            # 1. Get initial frequency (WSJT-X uses short command 'f')
            resp = client.send_command('f')
            # Response format: "Frequency: 14074000\nRPRT 0\n" or just "14074000\n"
            assert '14074000' in resp or '14.074' in resp, f"Expected 14074000 Hz, got: {resp}"

            # 2. Set frequency to 145 MHz (2m band)
            resp = client.send_command('F 145000000.000000')
            assert 'RPRT 0' in resp, f"Expected success, got: {resp}"

            # 3. Verify frequency changed
            time.sleep(0.2)  # Brief delay for state update
            resp = client.send_command('f')
            assert '145000000' in resp or '145.000' in resp, f"Expected 145000000 Hz, got: {resp}"

            # 4. Set frequency with offset (typical for digital modes)
            resp = client.send_command('F 145000055.000000')
            assert 'RPRT 0' in resp, f"Expected success, got: {resp}"

            # 5. Verify offset frequency
            time.sleep(0.2)
            resp = client.send_command('f')
            assert '145000055' in resp or '145.000055' in resp, f"Expected 145000055 Hz, got: {resp}"

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)


def test_wsjt_x_mode_and_vfo_queries(page: Page, profile_manager: ProfileManager):
    """
    Test mode and VFO queries.

    WSJT-X queries:
    - Current VFO (v command)
    - Current mode and passband (m command)
    - Split VFO status (s command)
    """
    profile_name = "test_wsjt_x_mode_vfo"

    fake_rig = FakeRigctld(frequency=145000000, mode='FM', passband=15000)

    config = {
        "rigs": [{
            "name": "WSJT-X Mode Test",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)

        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        with RigctlClient() as client:
            # 1. Get VFO
            resp = client.send_command('v')
            assert 'VFO' in resp.upper(), f"Expected VFO response, got: {resp}"

            # 2. Get mode and passband
            resp = client.send_command('m')
            # Response format: "Mode: FM\nPassband: 15000\nRPRT 0\n" or "FM\n15000\n"
            assert 'FM' in resp, f"Expected FM mode, got: {resp}"
            assert '15000' in resp, f"Expected 15000 Hz passband, got: {resp}"

            # 3. Get split VFO status
            # Note: Some rigs may not support this, returning error is acceptable
            resp = client.send_command('s')
            # Valid responses: "0\nNone\n", "0\nVFOA\n", or "RPRT -1\n" (not supported)
            # We just verify we get a response
            assert len(resp) > 0, f"Expected split VFO response, got: {resp}"

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)


def test_wsjt_x_ptt_operations(page: Page, profile_manager: ProfileManager):
    """
    Test PTT (push-to-talk) operations.

    WSJT-X uses PTT for transmit control:
    - Set PTT on (1) before transmitting
    - Set PTT off (0) after transmitting
    - Query PTT status

    Note: PTT query may fail on some rigs (RPRT -11 is acceptable).
    """
    profile_name = "test_wsjt_x_ptt"

    fake_rig = FakeRigctld(frequency=14074000, mode='USB', passband=2400)

    config = {
        "rigs": [{
            "name": "WSJT-X PTT Test",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)

        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        with RigctlClient() as client:
            # 1. Set PTT off
            resp = client.send_command('T 0')
            assert 'RPRT 0' in resp, f"Expected PTT off success, got: {resp}"

            # 2. Set PTT on
            resp = client.send_command('T 1')
            assert 'RPRT 0' in resp, f"Expected PTT on success, got: {resp}"

            # 3. Set PTT off again
            resp = client.send_command('T 0')
            assert 'RPRT 0' in resp, f"Expected PTT off success, got: {resp}"

            # 4. Query PTT status (may fail on some rigs)
            resp = client.send_command('t')
            # Accept either success or "not implemented" error
            assert 'RPRT' in resp or '0' in resp or '1' in resp, f"Expected PTT response, got: {resp}"

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)


def test_wsjt_x_full_session(page: Page, profile_manager: ProfileManager):
    """
    Test a complete WSJT-X session flow.

    Simulates a realistic sequence:
    1. Initialize connection
    2. Query rig state
    3. Set frequency for operation
    4. Monitor and adjust
    5. Clean disconnect
    """
    profile_name = "test_wsjt_x_full"

    fake_rig = FakeRigctld(frequency=145000000, mode='FM', passband=15000)

    config = {
        "rigs": [{
            "name": "WSJT-X Full Test",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.goto("/")

        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        # Verify UI is showing the rig
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible(timeout=5000)

        with RigctlClient() as client:
            # === INITIALIZATION ===
            client.send_command('\\get_powerstat')
            client.send_command('\\chk_vfo')
            client.send_command('\\dump_state')

            # === QUERY CURRENT STATE ===
            client.send_command('v')  # VFO
            client.send_command('l KEYSPD')  # Key speed level (may not be supported)
            resp = client.send_command('f')  # Frequency
            assert '145000000' in resp or '145.000' in resp

            resp = client.send_command('f')  # Frequency (WSJT-X polls twice)
            assert '145000000' in resp or '145.000' in resp

            client.send_command('s')  # Split VFO
            resp = client.send_command('m')  # Mode
            assert 'FM' in resp

            # === SET OPERATING FREQUENCY ===
            resp = client.send_command('F 145000055.000000')
            assert 'RPRT 0' in resp

            # Verify frequency changed
            time.sleep(0.3)
            resp = client.send_command('f')
            assert '145000055' in resp or '145.000055' in resp

            # === RETURN TO BASE FREQUENCY ===
            resp = client.send_command('F 145000000.000000')
            assert 'RPRT 0' in resp

            # === FINAL STATE CHECK ===
            time.sleep(0.3)
            resp = client.send_command('f')
            assert '145000000' in resp or '145.000' in resp

            client.send_command('v')
            client.send_command('s')
            client.send_command('m')

            # PTT query (may fail)
            client.send_command('t')

        # Verify UI updated to final frequency
        time.sleep(0.5)
        lcd = rig_card.locator(".lcd")
        expect(lcd).to_contain_text("145.000")

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)


def test_wsjt_x_connection_handling(page: Page, profile_manager: ProfileManager):
    """
    Test connection lifecycle.

    WSJT-X may:
    - Connect and disconnect multiple times
    - Send 'q' (quit) command
    - Reconnect after errors
    """
    profile_name = "test_wsjt_x_conn"

    fake_rig = FakeRigctld(frequency=14074000)

    config = {
        "rigs": [{
            "name": "WSJT-X Connection Test",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": fake_rig.port,
            "poll_interval_ms": 100,
            "enabled": True
        }],
        "poll_interval_ms": 100,
        "sync_enabled": False,
    }

    try:
        import json
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)

        assert profile_manager.wait_for_ready(profile_name, rig_count=1, timeout=10)

        # Test multiple connect/disconnect cycles
        for i in range(3):
            with RigctlClient() as client:
                # Quick operation
                resp = client.send_command('f')
                assert '14074000' in resp or '14.074' in resp

                # Explicit quit (though context manager will close anyway)
                # Note: 'q' command returns RPRT 0 and closes connection
                # After sending 'q', the socket will be closed by server
                client.send_command('q')

            # Brief delay between cycles
            time.sleep(0.2)

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)