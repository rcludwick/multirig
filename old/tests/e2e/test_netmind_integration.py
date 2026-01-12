import pytest
import time
import socket
import json
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

def test_netmind_integration_dump_caps(profile_manager: ProfileManager):
    # This test modifies global config directly (like the JS original).
    # But we can use a profile and load it.
    proxy_port = 9001
    profile_name = "test_netmind_integration_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Netmind_Integration_Proxy", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Netmind Path Rig", "connection_type": "rigctld", "host": "127.0.0.1", "port": proxy_port, "enabled": True, "poll_interval_ms": 1000
        }],
        "rigctl_listen_port": 4534,
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        time.sleep(2)
        
        # Connect to MultiRig and send dump_caps
        cmd = "\\dump_caps\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
            s.settimeout(3.0)
            data = b""
            while True:
                try:
                    chunk = s.recv(4096)
                    if not chunk: break
                    data += chunk
                    if len(data) > 50: # Wait a bit more
                        time.sleep(0.5)
                        break
                except socket.timeout:
                    break
        
        # Verify Netmind captured dump_caps
        found = profile_manager.wait_for_netmind_history(
            "Netmind_Integration_Proxy",
            lambda p: p.get("direction") == "TX" and 
                      ("dump_caps" in p.get("data_str", "") or "dump_caps" in p.get("semantic", ""))
        )
        assert found, "dump_caps not found in Netmind history"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)
