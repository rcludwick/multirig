import pytest
import time
import json
import re
import socket
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager, FakeRigctld

NETMIND_BASE = 'http://127.0.0.1:9000'

def _check_netmind_history(request, proxy_name, condition_fn, limit=500):
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

def test_rig_color(page: Page, profile_manager: ProfileManager):
    profile_name = "test_rig_color_py"
    config = {
        "rigs": [{
            "name": "Rig 1",
            "connection_type": "hamlib",
            "model_id": 1,
            "device": "/dev/null",
            "baud": 38400,
            "color": "#a4c356"
        }],
        "poll_interval_ms": 1000,
        "sync_enabled": True,
        "sync_source_index": 0
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        page.goto("/")
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.get_by_role("link", name="Config").click()
        expect(page).to_have_url(re.compile(r"/settings"))
        
        first_rig = page.locator("#rigList fieldset").first
        color_input = first_rig.locator('input[data-key="color"]')
        expect(color_input).to_be_visible()
        color_input.fill("#ff0000")
        expect(color_input).to_have_value("#ff0000")
        
        page.get_by_role("button", name="Save").click()
        expect(page.locator("#saveResult")).to_have_text("Saved")
        
        page.get_by_role("link", name="Rigs").click()
        expect(page).to_have_url(re.compile(r"/$"))
        
        lcd = page.locator("#rig-0 .lcd")
        expect(lcd).to_be_visible()
        # Check style for red
        expect(lcd).to_have_attribute("style", re.compile(r"linear-gradient.*(?:#ff0000|255,\s*0,\s*0)", re.I))
        
        # Reset
        page.get_by_role("link", name="Config").click()
        first_rig_reset = page.locator("#rigList fieldset").first
        first_rig_reset.locator('button[data-action="reset-color"]').click()
        expect(first_rig_reset.locator('input[data-key="color"]')).to_have_value("#a4c356")
        
        page.get_by_role("button", name="Save").click()
        expect(page.locator("#saveResult")).to_have_text("Saved")
        
        page.get_by_role("link", name="Rigs").click()
        lcd_reset = page.locator("#rig-0 .lcd")
        expect(lcd_reset).to_have_attribute("style", re.compile(r"linear-gradient.*(?:#a4c356|164,\s*195,\s*86)", re.I))

    finally:
        profile_manager.delete_profile(profile_name)

def test_rig_disable_toggle(page: Page, profile_manager: ProfileManager):
    rigA = FakeRigctld(frequency=14074000)
    rigB = FakeRigctld(frequency=7074000)
    
    profile_name = "test_rig_disable_toggle_py"
    config = {
      "rigs": [
        { "name": "Rig A", "enabled": True, "connection_type": "rigctld", "host": "127.0.0.1", "port": rigA.port, "poll_interval_ms": 200 },
        { "name": "Rig B", "enabled": True, "connection_type": "rigctld", "host": "127.0.0.1", "port": rigB.port, "poll_interval_ms": 200 },
      ],
      "poll_interval_ms": 200,
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        page.goto("/")
        profile_manager.load_profile(profile_name)
        page.reload()
        
        card0 = page.locator("#rig-0")
        expect(card0).to_be_visible()
        power0 = card0.locator('input[data-action="power"]')
        expect(power0).to_be_checked()
        
        power0.uncheck()
        expect(power0).not_to_be_checked()
        expect(card0).to_have_attribute("data-enabled", "false")
        
        page.wait_for_timeout(1800)
        expect(power0).not_to_be_checked()
        expect(card0).to_have_attribute("data-enabled", "false")
        
        res = profile_manager.request.get("/api/status")
        assert res.ok
        status = res.json()
        assert status["rigs"][0]["enabled"] is False
        
        page.reload()
        card0b = page.locator("#rig-0")
        expect(card0b).to_be_visible()
        power0b = card0b.locator('input[data-action="power"]')
        expect(power0b).not_to_be_checked()
        expect(card0b).to_have_attribute("data-enabled", "false")

    finally:
        rigA.stop()
        rigB.stop()
        profile_manager.delete_profile(profile_name)

def test_ui_follow_toggle_no_error(page: Page, profile_manager: ProfileManager):
    # Using dummy rig (4532)
    profile_name = "test_ui_follow_toggle_py"
    config = {
        "rigs": [
            { "name": "Main", "connection_type": "rigctld", "host": "127.0.0.1", "port": 4532, "poll_interval_ms": 200 },
            { "name": "Follower", "connection_type": "rigctld", "host": "127.0.0.1", "port": 4532, "follow_main": False, "poll_interval_ms": 200 }
        ],
        "sync_enabled": True,
        "sync_source_index": 0,
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.goto("/")
        
        rig1 = page.locator("#rig-1")
        expect(rig1).to_be_visible(timeout=10000)
        expect(rig1).not_to_have_class(re.compile(r"disabled"))
        
        toggle = rig1.locator('input[data-action="follow-main"]')
        expect(toggle).to_be_visible()
        expect(toggle).to_be_enabled()
        
        toggle.click()
        
        error_box = rig1.locator('[data-role="error"]')
        page.wait_for_timeout(1000)
        
        if error_box.is_visible():
            text = error_box.locator(".rig-error-body").text_content()
            assert "Internal Server Error" not in text
            assert "SyntaxError" not in text
        else:
            assert True

    finally:
        profile_manager.delete_profile(profile_name)

def test_mode_change_validation(page: Page, profile_manager: ProfileManager):
    proxy_port = 9024
    proxy_name = "Mode_Change_Test_Rig"
    profile_name = "test_mode_change_py"
    
    profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    
    config = {
        "rigs": [{
            "name": "Mode Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "model_id": 29001
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.goto("/")
        
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible()
        
        usb_btn = rig_card.locator('button[data-action="set-mode"]', has_text="USB")
        expect(usb_btn).to_be_visible()
        
        start_time = time.time()
        usb_btn.click()
        
        found = _check_netmind_history(
            profile_manager.request,
            proxy_name,
            lambda p: p.get("direction") == "TX" and p.get("timestamp", 0) > start_time and
                      "M USB" in p.get("data_str", "")
        )
        assert found, "Mode change command not found"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_ui_forwarding_inhibition(page: Page, profile_manager: ProfileManager):
    profile_name = "test_forwarding_py"
    config = {
        "rigs": [{
            "name": "Test Rig",
            "connection_type": "hamlib",
            "model_id": 1,
            "device": "/dev/null",
            "baud": 38400
        }],
        "poll_interval_ms": 200,
        "sync_enabled": True,
        "sync_source_index": 0
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        page.goto("/")
        profile_manager.load_profile(profile_name)
        page.reload()
        
        # Connect client to rigctld (4532 - wait, config uses 4532, but it's a dummy managed by backend?)
        # 4532 is the dummy rigctld started by test_env.
        # But if the Rig connects to a device, does it expose a server?
        # Typically MultiRig exposes its own server on 4534 (config dependent).
        # The JS test connected to 4532: `client.connect(4532, ...)`
        # This means it connected directly to the Backend (the dummy rig)!
        # And it clicked the UI.
        # If UI sets frequency, it sends command to Backend.
        # So "Should NOT forward UI band clicks to TCP client [also connected to Backend]"??
        # Rigctld (hamlib) generally broadcasts updates if using async mode.
        # But maybe dummy rigctld doesn't?
        # Or maybe test expects it NOT to broadcast?
        # The test asserts receivedData.length is 0.
        
        received_data = []
        
        # Connect to 4532
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 4532))
        sock.setblocking(False)
        
        rig_card = page.locator("#rig-0")
        expect(rig_card).to_be_visible()
        rig_card.locator(".band-btn", has_text="40m").click()
        
        page.wait_for_timeout(1000)
        
        try:
            data = sock.recv(1024)
            if data:
                received_data.append(data)
        except BlockingIOError:
            pass # No data
            
        sock.close()
        
        assert len(received_data) == 0, f"Received unexpected data: {received_data}"

    finally:
        profile_manager.delete_profile(profile_name)
