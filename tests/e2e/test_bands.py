import pytest
import time
import json
import socket
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

NETMIND_BASE = 'http://127.0.0.1:9000'

def _check_netmind_history(request, proxy_name, condition_fn, limit=20):
    for _ in range(20):
        res = request.get(f"{NETMIND_BASE}/api/history", params={"limit": limit, "proxy_name": proxy_name})
        if not res.ok:
            time.sleep(0.2)
            continue
        history = res.json()
        match = next((p for p in history if condition_fn(p)), None)
        if match:
            return True
        time.sleep(0.2)
    return False

def test_band_change_validation(page: Page, profile_manager: ProfileManager):
    proxy_port = 9022
    proxy_name = "Band_Change_Test_Rig"
    profile_name = "test_band_change_validation_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Band Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True },
                { "label": "40m", "frequency_hz": 7074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.goto("/")
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible()
        
        btn40m = rig_card.locator("button", has_text="40m")
        expect(btn40m).to_be_visible()
        
        start_time = time.time()
        btn40m.click()
        
        found = _check_netmind_history(
            profile_manager.request, 
            proxy_name,
            lambda p: p.get("direction") == "TX" and p.get("timestamp") > start_time and
                      ("F 7074000" in p.get("data_str", "") or "SET FREQ: 7074000" in p.get("semantic", ""))
        )
        assert found, "Band change command not found in history"
        
    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_band_change_out_of_band_validation(page: Page, profile_manager: ProfileManager):
    proxy_port = 9021
    proxy_name = "OOB_Allowed_Test_Rig"
    profile_name = "test_oob_allowed_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "OOB Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "allow_out_of_band": True,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.goto("/")
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible()
        
        rig_card.locator('button[data-action="edit-freq"]').click()
        input_el = rig_card.locator('input[data-role="freq-input"]')
        expect(input_el).to_be_visible()
        
        target_freq = "7074000" # 40m, but 20m is enabled. Allowed because OOB=True
        input_el.fill(target_freq)
        rig_card.locator('button[data-action="freq-save"]').click()
        
        expect(rig_card.locator('[data-role="error"]')).not_to_be_visible()
        
        found = _check_netmind_history(
            profile_manager.request,
            proxy_name,
            lambda p: p.get("direction") == "TX" and f"F {target_freq}" in p.get("data_str", "")
        )
        assert found
        
    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_band_change_error_validation(page: Page, profile_manager: ProfileManager):
    proxy_port = 9020
    proxy_name = "Band_Error_Test_Rig"
    profile_name = "test_oob_error_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Error Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "allow_out_of_band": False,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.goto("/")
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible()
        
        rig_card.locator('button[data-action="edit-freq"]').click()
        input_el = rig_card.locator('input[data-role="freq-input"]')
        input_el.fill("7074000") # OOB
        rig_card.locator('button[data-action="freq-save"]').click()
        
        error_box = rig_card.locator('[data-role="error"]')
        expect(error_box).to_be_visible()
        expect(error_box).to_contain_text("Frequency out of configured band ranges")
        
        # Verify it was NOT sent
        found = _check_netmind_history(
            profile_manager.request,
            proxy_name,
            lambda p: p.get("direction") == "TX" and "F 7074000" in p.get("data_str", "")
        )
        assert not found, "Blocked frequency command was sent to rig!"
        
    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_band_disabled_validation(page: Page, profile_manager: ProfileManager):
    proxy_port = 9023
    proxy_name = "Disabled_Band_Test_Rig"
    profile_name = "test_band_disabled_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Disabled Band Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "allow_out_of_band": False,
            "band_presets": [
                { "label": "40m", "frequency_hz": 7074000, "enabled": True },
                { "label": "80m", "frequency_hz": 3573000, "enabled": False }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        # Ensure rigctl server is running (it is by default in conftest)
        
        profile_manager.load_profile(profile_name)
        time.sleep(1)
        
        # Connect to MultiRig Rigctl Server and send command
        cmd = "F 3573000\n" # 80m (Disabled)
        
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
            # Send command. Protocol dictates response behavior, but for this test
            # we primarily verify behavior via Netmind history (absence of forwarding).
            
        found = _check_netmind_history(
            profile_manager.request,
            proxy_name,
            lambda p: p.get("direction") == "TX" and "F 3573000" in p.get("data_str", ""),
            limit=20
        )
        assert not found, "Disabled band frequency was forwarded!"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)
