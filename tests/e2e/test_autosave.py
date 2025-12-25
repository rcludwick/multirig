import pytest
import time
import json
from playwright.sync_api import Page, expect, APIRequestContext
from tests.e2e.utils import ProfileManager

def test_autosave_profile_on_change(page: Page, profile_manager: ProfileManager):
    profile_name = "test_autosave_profile_on_change_py"
    
    initial_config = {
        "rigs": [{
            "name": "Autosave Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": 4532,
            "poll_interval_ms": 5000,
            "band_presets": [
                { "label": "20m", "frequency_hz": 14074000, "enabled": True },
            ],
        }],
        "poll_interval_ms": 5000,
    }
    
    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(initial_config))
        
        page.goto("/settings")
        # Ensure we are on the right profile
        page.locator("#profileSelectBtn").click()
        page.locator("#profileSelectChoice").select_option(profile_name)
        page.locator("#profileSelectConfirm").click()
        
        expect(page.locator("#profileResult")).to_contain_text("Loaded profile")
        
        rig_fieldset = page.locator("#rigList fieldset").first
        expect(rig_fieldset).to_be_visible()
        
        rig_port_input = rig_fieldset.locator('input[data-key="port"]')
        expect(rig_port_input).to_be_visible()
        
        new_port = 9991
        rig_port_input.fill(str(new_port))
        rig_port_input.blur()
        
        # Debounce is 700ms
        time.sleep(2.0)
        
        # Verify running config
        assert profile_manager.wait_for_status(
            lambda s: s.get("rigs") and len(s["rigs"]) > 0 and s["rigs"][0].get("port") == new_port,
            timeout=5
        ), "Config not applied to running server"
        
        # Verify profile persisted
        import urllib.parse
        encoded_name = urllib.parse.quote(profile_name)
        assert profile_manager.wait_for_status(
            lambda s: True, # Just a dummy to use polling logic if I want, but I need to poll export
            timeout=0 # wait_for_status doesn't fit export easily without helper
        ) == False # wait_for_status isn't right here
        
        saved = False
        api_req = profile_manager.request
        for _ in range(10):
            res = api_req.get(f"/api/config/profiles/{encoded_name}/export")
            if res.ok and f"port: {new_port}" in res.text():
                saved = True
                break
            time.sleep(0.2)
        assert saved, "Config not saved to profile"
        
    finally:
        profile_manager.delete_profile(profile_name)
