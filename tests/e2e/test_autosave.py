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
        # Ensure fresh start
        profile_manager.delete_profile(profile_name)

        # Manual configure and save
        res = profile_manager.request.post("/api/config", data=initial_config)
        if not res.ok:
            raise RuntimeError(f"Failed to apply config: {res.text()}")

        res = profile_manager.request.post(f"/api/config/profiles/{profile_name}")
        if not res.ok:
            raise RuntimeError(f"Failed to save profile: {res.text()}")

        time.sleep(1.0) # avoid race condition with file system
        
        # Use API to load profile to avoid UI flakiness/race conditions
        profile_manager.load_profile(profile_name)

        page.goto("/settings")
    
        # Wait for the backend to acknowledge the profile is active AND config is loaded
        # checking "rigs" guarantees _apply_config has finished rebuilding rigs
        def check_status(s):
            rigs = s.get("rigs", [])
            return (s.get("active_profile") == profile_name and
                    len(rigs) > 0 and
                    rigs[0].get("name") == "Autosave Rig")

        assert profile_manager.wait_for_status(check_status, timeout=10), \
            f"Timeout waiting for ACTIVE profile. Current status: {profile_manager.request.get('/api/status').text()}"

        # Reload to ensure we see the true state of the server
        page.reload()
        expect(page.locator("#rigList")).to_be_visible()
        
        # Find the fieldset that contains the input with the correct rig name
        rig_fieldset = page.locator("#rigList fieldset").filter(has=page.locator('input[data-key="name"][value="Autosave Rig"]'))
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
        # Verify profile persisted (polling export endpoint)
        assert profile_manager.wait_for_status(
            lambda s: True, 
            timeout=0 
        ) == False 
        
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
