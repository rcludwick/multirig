import pytest
import time
import json
import socket
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

def test_rig_following_basic(page: Page, profile_manager: ProfileManager):
    main_port = 9010
    follower_port = 9011
    profile_name = "test_rig_following_basic_py"
    
    profile_manager.create_proxy({
        "local_port": main_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Main_Rig_Basic", "protocol": "hamlib"
    })
    profile_manager.create_proxy({
        "local_port": follower_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Follower_Rig_Basic", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": main_port, "poll_interval_ms": 200 },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": follower_port, "poll_interval_ms": 200, "follow_main": True }
        ],
        "sync_enabled": True, "sync_source_index": 0, "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=2)
        
        # Send command to MultiRig (4534)
        cmd = "F 14074000\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
        
        # Verify Main
        found_main = profile_manager.wait_for_netmind_history(
            "Main_Rig_Basic", 
            lambda p: p.get("direction") == "TX" and "F 14074000" in p.get("data_str", "")
        )
        assert found_main
        
        # Verify Follower
        found_follower = profile_manager.wait_for_netmind_history(
            "Follower_Rig_Basic",
            lambda p: p.get("direction") == "TX" and "F 14074000" in p.get("data_str", "")
        )
        assert found_follower

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(main_port)
        profile_manager.delete_proxy(follower_port)

def test_rig_following_disabled_at_follower(page: Page, profile_manager: ProfileManager):
    main_port = 9012
    follower_port = 9013
    profile_name = "test_rig_following_disabled_py"
    
    profile_manager.create_proxy({
        "local_port": main_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Main_Rig_NoFollow", "protocol": "hamlib"
    })
    profile_manager.create_proxy({
        "local_port": follower_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Follower_Rig_NoFollow", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": main_port, "poll_interval_ms": 200 },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": follower_port, "poll_interval_ms": 200, "follow_main": False }
        ],
        "sync_enabled": True, "sync_source_index": 0, "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=2)
        
        cmd = "F 14074000\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
        
        found_main = profile_manager.wait_for_netmind_history(
            "Main_Rig_NoFollow",
            lambda p: p.get("direction") == "TX" and "F 14074000" in p.get("data_str", "")
        )
        assert found_main
        
        found_follower = profile_manager.wait_for_netmind_history(
            "Follower_Rig_NoFollow",
            lambda p: p.get("direction") == "TX" and "F 14074000" in p.get("data_str", "")
        )
        # Should NOT find it
        assert not found_follower

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(main_port)
        profile_manager.delete_proxy(follower_port)

def test_sync_to_follower_band_error(page: Page, profile_manager: ProfileManager):
    main_port = 9027
    follower_port = 9028
    profile_name = "test_sync_error_py"
    
    profile_manager.create_proxy({
        "local_port": main_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Sync_Error_Main", "protocol": "hamlib"
    })
    profile_manager.create_proxy({
        "local_port": follower_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Sync_Error_Follower", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": main_port, "poll_interval_ms": 200, 
              "band_presets": [{"label": "20m", "frequency_hz": 14074000, "enabled": True}, {"label": "40m", "frequency_hz": 7074000, "enabled": True}] },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": follower_port, "poll_interval_ms": 200, "follow_main": True,
              "allow_out_of_band": False,
              "band_presets": [{"label": "20m", "frequency_hz": 14074000, "enabled": True, "lower_hz": 14000000, "upper_hz": 14350000}] }
        ],
        "sync_enabled": True, "sync_source_index": 0, "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=2)
        
        # Send 40m freq (7074000) to Main. Main accepts. Follower rejects (only 20m enabled).
        cmd = "F 7074000\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
        
        found_main = profile_manager.wait_for_netmind_history(
            "Sync_Error_Main",
            lambda p: p.get("direction") == "TX" and "F 7074000" in p.get("data_str", "")
        )
        assert found_main
        
        found_follower = profile_manager.wait_for_netmind_history(
            "Sync_Error_Follower",
            lambda p: p.get("direction") == "TX" and "F 7074000" in p.get("data_str", "")
        )
        assert not found_follower
        
        # Verify status error for Follower (rig 1)
        res = profile_manager.request.get("/api/status")
        assert res.ok
        status = res.json()
        assert status["rigs"][1]["last_error"] is not None
        assert "Frequency out of configured band ranges" in status["rigs"][1]["last_error"]

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(main_port)
        profile_manager.delete_proxy(follower_port)
        
def test_follower_band_error_ui(page: Page, profile_manager: ProfileManager):
    main_port = 9070
    follower_port = 9071
    profile_name = "test_follower_ui_error_py"
    
    profile_manager.create_proxy({
        "local_port": main_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "UI_Error_Main", "protocol": "hamlib"
    })
    profile_manager.create_proxy({
        "local_port": follower_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "UI_Error_Follower", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": main_port, "poll_interval_ms": 200, 
              "band_presets": [{"label": "20m", "frequency_hz": 14074000, "enabled": True}, {"label": "40m", "frequency_hz": 7074000, "enabled": True}] },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": follower_port, "poll_interval_ms": 200, "follow_main": True,
              "allow_out_of_band": False,
              "band_presets": [{"label": "20m", "frequency_hz": 14074000, "enabled": True}] }
        ],
        "sync_enabled": True, "sync_source_index": 0, "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.goto("/")
        
        rig1 = page.locator("#rig-1") # Follower
        expect(rig1).to_be_visible()
        
        # Change Main to 40m via UI
        rig0 = page.locator("#rig-0")
        rig0.locator('button', has_text="40m").click()
        
        # Wait for error on rig1
        error_box = rig1.locator('[data-role="error"]')
        expect(error_box).to_be_visible(timeout=5000)
        expect(error_box).to_contain_text("Frequency out of configured band ranges")
        
    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(main_port)
        profile_manager.delete_proxy(follower_port)

def test_sync_globally_disabled(page: Page, profile_manager: ProfileManager):
    main_port = 9025
    follower_port = 9026
    profile_name = "test_sync_globally_disabled_py"
    
    profile_manager.create_proxy({
        "local_port": main_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Global_No_Sync_Main", "protocol": "hamlib"
    })
    profile_manager.create_proxy({
        "local_port": follower_port, "target_host": "127.0.0.1", "target_port": 4532,
        "name": "Global_No_Sync_Follower", "protocol": "hamlib"
    })
    
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": main_port, "poll_interval_ms": 200 },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": follower_port, "poll_interval_ms": 200, "follow_main": True }
        ],
        "sync_enabled": False, "sync_source_index": 0, "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        profile_manager.wait_for_ready(profile_name, rig_count=2)
        
        cmd = "F 14075000\n"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("127.0.0.1", 4534))
            s.sendall(cmd.encode())
        
        found_main = profile_manager.wait_for_netmind_history(
            "Global_No_Sync_Main",
            lambda p: p.get("direction") == "TX" and "F 14075000" in p.get("data_str", "")
        )
        assert found_main
        
        found_follower = profile_manager.wait_for_netmind_history(
            "Global_No_Sync_Follower",
            lambda p: p.get("direction") == "TX" and "F 14075000" in p.get("data_str", "")
        )
        assert not found_follower

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(main_port)
        profile_manager.delete_proxy(follower_port)

