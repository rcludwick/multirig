import pytest
import time
import json
import re
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

NETMIND_BASE = 'http://127.0.0.1:9000'

def test_auto_caps_detection(profile_manager: ProfileManager):
    proxy_port = 9040
    proxy_name = "Auto_Caps_Test_Rig"
    profile_name = "test_auto_caps_detection_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": proxy_name, "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Auto Caps Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        
        profile_manager.wait_for_ready(profile_name, rig_count=1)
        assert profile_manager.wait_for_caps(rig_index=0, timeout=10)
        
        # Give Netmind history a moment to catch up
        time.sleep(2)
        
        status = profile_manager.get_status()
        rig = status["rigs"][0]
        caps = rig["caps"]
        assert caps.get("freq_get") is True
        assert caps.get("freq_set") is True
        assert caps.get("mode_get") is True
        assert caps.get("mode_set") is True
        assert "USB" in rig["modes"]
        assert "LSB" in rig["modes"]
        
        # Verify dump_caps in Netmind history
        found = profile_manager.wait_for_netmind_history(
            proxy_name,
            lambda p: p.get("direction") == "TX" and ("dump_caps" in p.get("data_str", "") or "dump_caps" in p.get("semantic", "")),
            limit=2000
        )
        if not found:
            # Dump history summary for debugging
            res = profile_manager.request.get(f"{NETMIND_BASE}/api/history", params={"limit": 100, "proxy_name": proxy_name})
            if res.ok:
                h = res.json()
                print(f"DEBUG: History tail (10 pkts): {[(p.get('direction'), p.get('semantic')) for p in h[-10:]]}")
        assert found, "dump_caps not found in Netmind history"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_auto_caps_reconnection(profile_manager: ProfileManager):
    proxy_port = 9041
    proxy_name = "Reconnect_Caps_Test_Rig"
    profile_name = "test_auto_caps_reconnection_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": proxy_name, "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": proxy_name,
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=1)
        
        # Give a moment for initial caps detection to finish history logging
        time.sleep(2.0)
    
        api_req = profile_manager.request
        
        def count_dump_caps():
            res = api_req.get(f"{NETMIND_BASE}/api/history", params={"limit": 2000, "proxy_name": proxy_name})
            if not res.ok: return 0
            history = res.json()
            return len([p for p in history if p.get("direction") == "TX" and ("dump_caps" in p.get("data_str", "") or "dump_caps" in p.get("semantic", ""))])
            
        initial_count = count_dump_caps()
        assert initial_count >= 1, "Initial dump_caps should have been sent"
        
        # Disconnect by deleting proxy
        profile_manager.delete_proxy(proxy_port)
        profile_manager.wait_for_status(lambda s: not s["rigs"][0]["connected"] and not s["rigs"][0].get("caps_detected"), timeout=10)
        
        # Reconnect
        profile_manager.create_proxy({
            "local_port": proxy_port, "target_host": "127.0.0.1", "target_port": 4532,
            "name": proxy_name, "protocol": "hamlib"
        })
        profile_manager.wait_for_status(lambda s: s["rigs"][0]["connected"] and s["rigs"][0].get("caps_detected"), timeout=10)
        
        # Give a moment for the poll loop to detect connection and send dump_caps again
        time.sleep(3.0)
        
        new_count = count_dump_caps()
        assert new_count > initial_count, "dump_caps should have been sent again after reconnection"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_auto_caps_ui_display(page: Page, profile_manager: ProfileManager):
    proxy_port = 9042
    proxy_name = "UI_Caps_Test_Rig"
    profile_name = "test_auto_caps_ui_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": proxy_name, "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": proxy_name,
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "model_id": 2, # Standard dummy
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True }
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=1)
        profile_manager.wait_for_caps(rig_index=0)
        
        page.goto("/settings")
        
        rig_fieldset = page.locator("#rigList fieldset").first
        expect(rig_fieldset).to_be_visible()
        
        caps_el = rig_fieldset.locator(".caps-badges")
        expect(caps_el).not_to_contain_text("Caps unknown", timeout=10000)
        expect(caps_el.locator(".cap-badge")).not_to_have_count(0)

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)
