import pytest
import time
import json
import re
from playwright.sync_api import Page, expect, APIRequestContext
from tests.e2e.utils import ProfileManager, FakeRigctld

NETMIND_BASE = 'http://127.0.0.1:9000'

def test_settings_band_reset(page: Page, profile_manager: ProfileManager):
    fake_rig = FakeRigctld()
    port = fake_rig.port
    profile_name = "test_settings_band_reset_py"
    
    config = {
        "rigs": [{
            "name": "Settings Band Reset Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": port,
            "poll_interval_ms": 200,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True },
                { "label": "40m", "frequency_hz": 7074000, "enabled": True },
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        
        page.goto("/settings")
        
        rig_fieldset = page.locator("#rigList fieldset").first
        expect(rig_fieldset).to_be_visible()
        
        band_toggle = rig_fieldset.locator('button[data-action="toggle-band-presets"]')
        band_toggle.click()
        
        rows = rig_fieldset.locator(".band-row")
        expect(rows).to_have_count(2)
        
        rig_fieldset.locator('button[data-action="band-reset"]').click()
        
        # After reset, we expect all bands (usually ~16 from FakeRigctld's HF + 2m capabilities).
        expect(rows).not_to_have_count(2)
        
        expect(rig_fieldset.locator('.band-row', has_text='160m')).to_be_visible()
        expect(rig_fieldset.locator('.band-row', has_text='23cm')).to_be_visible() 

    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)

def test_settings_get_caps_netmind(page: Page, profile_manager: ProfileManager, api_manager: ProfileManager):
    # Reset Netmind (using a unique proxy name).
    timestamp = int(time.time())
    proxy_name = f"Multirig_Caps_UI_Py_{timestamp}"
    proxy_port = 9001
    
    # Create Proxy pointing to Real Dummy Rig (4532)
    # Note: 4532 is managed by conftest.py
    proxy_res = profile_manager.create_proxy({
        "local_port": proxy_port,
        "target_host": "127.0.0.1",
        "target_port": 4532,
        "name": proxy_name,
        "protocol": "hamlib"
    })
    assert proxy_res.ok
    
    profile_name = "test_settings_get_caps_netmind_py"
    config = {
        "rigs": [{
            "name": "Caps UI Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": proxy_port,
            "poll_interval_ms": 200,
            "model_id": 2
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        
        page.goto("/settings")
        
        rig_fieldset = page.locator("#rigList fieldset").first
        expect(rig_fieldset).to_be_visible()
        
        caps_el = rig_fieldset.locator(".caps-badges")
        expect(caps_el).to_contain_text("Caps unknown")
        
        btn = rig_fieldset.locator('button[data-action="caps"]')
        expect(btn).to_be_visible()
        
        with page.expect_response(lambda resp: "/api/test-rig" in resp.url and resp.request.method == "POST") as response_info:
            btn.click()
            
        resp = response_info.value
        assert resp.ok
        
        expect(rig_fieldset.locator(".test-result")).to_contain_text("Capabilities updated.")
        expect(caps_el).not_to_contain_text("Caps unknown")
        expect(caps_el.locator(".cap-badge")).to_have_count(4)
        
        # Verify Netmind history
        found = False
        api_req = profile_manager.request
        for _ in range(10):
            res = api_req.get(f"{NETMIND_BASE}/api/history", params={"limit": 200})
            history = res.json()
            # Find dump_caps TX for our proxy
            match = next((p for p in history if 
                          p.get("direction") == "TX" and 
                          p.get("proxy_name") == proxy_name and
                          ("dump_caps" in p.get("data_str", "") or "dump_caps" in p.get("semantic", ""))), None)
            if match:
                found = True
                break
            time.sleep(0.5)
            
        assert found, "dump_caps command not found in Netmind history"

    finally:
        profile_manager.delete_profile(profile_name)
        profile_manager.delete_proxy(proxy_port)

def test_settings_lcd_invert(page: Page, profile_manager: ProfileManager):
    profile_name = "test_settings_invert_py"
    # YAML config equivalent
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
        # Clear local storage
        page.goto("/")
        page.evaluate("localStorage.clear()")
        
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.get_by_role("link", name="Config").click()
        expect(page).to_have_url(re.compile(r"/settings"))
        
        first_rig = page.locator("#rigList fieldset").first
        invert_box = first_rig.locator('input[data-key="inverted"]')
        preview_lcd = first_rig.locator(".lcd-preview-container .lcd")
        color_input = first_rig.locator('input[data-key="color"]')
        
        expect(invert_box).to_be_visible()
        expect(preview_lcd).to_be_visible()
        expect(invert_box).not_to_be_checked()
        expect(preview_lcd).not_to_have_class(re.compile(r"inverted"))
        
        invert_box.check()
        expect(preview_lcd).to_have_class(re.compile(r"inverted"))
        
        color_input.fill("#ff0000")
        color_input.dispatch_event("input")
        # Python playwright uses RGB strings generally
        expect(preview_lcd).to_have_css("color", "rgb(255, 0, 0)")
        
        reset_btn = first_rig.locator('button[data-action="reset-color"]')
        reset_btn.click()
        expect(color_input).to_have_value("#a4c356")
        
        page.get_by_role("button", name="Save").click()
        expect(page.locator("#saveResult")).to_have_text("Saved")
        
        page.get_by_role("link", name="Rigs").click()
        expect(page).to_have_url(re.compile(r"/$")) # Ends with /
        
        dashboard_lcd = page.locator("#rig-0 .lcd")
        expect(dashboard_lcd).to_have_class(re.compile(r"inverted"))
        expect(dashboard_lcd).to_have_css("color", "rgb(164, 195, 86)")
        
    finally:
        profile_manager.delete_profile(profile_name)

def test_test_connection_no_reset_bands(page: Page, profile_manager: ProfileManager):
    fake_rig = FakeRigctld()
    port = fake_rig.port
    profile_name = "test_settings_test_conn_no_reset_py"
    
    config = {
        "rigs": [{
            "name": "Test Connection No Reset Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": port,
            "poll_interval_ms": 200,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True },
                { "label": "40m", "frequency_hz": 7074000, "enabled": True },
            ]
        }],
        "poll_interval_ms": 200
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.reload()
        
        page.goto("/settings")
        
        rig_fieldset = page.locator("#rigList fieldset").first
        expect(rig_fieldset).to_be_visible()
        
        rig_fieldset.locator('button[data-action="toggle-band-presets"]').click()
        rows = rig_fieldset.locator(".band-row")
        expect(rows).to_have_count(2)
        
        rig_fieldset.locator('button[data-action="test"]').click()
        expect(rig_fieldset.locator('.test-result')).to_contain_text(re.compile(r"Connected|Connected successfully|Connected successfully!"))
        
        # Verify presets NOT changed
        expect(rows).to_have_count(2)
        
        # Sanity: reset should work
        rig_fieldset.locator('button[data-action="band-reset"]').click()
        expect(rows).to_have_count(16)
        
    finally:
        fake_rig.stop()
        profile_manager.delete_profile(profile_name)
