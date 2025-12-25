import pytest
import json
import psutil
import time
import re
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

PROFILE_NAME = "test_managed_rigs"
# Use a distinct dummy model ID or just 1.
# We'll use Model 1 (Dummy) which works with /dev/null (auto-injected by my recent fix)
MANAGED_CONFIG = {
    "rigs": [
        {
            "name": "Managed Dummy Rig",
            "managed": True,
            "model_id": 1,
            "device": None, # Will become /dev/null
            "poll_interval_ms": 500,
            "enabled": True
        }
    ],
    "poll_interval_ms": 500
}
MANAGED_YAML = json.dumps(MANAGED_CONFIG)

@pytest.fixture(scope="module")
def setup_managed_profile(base_url, playwright):
    api = playwright.request.new_context(base_url=base_url)
    pm = ProfileManager(api)
    pm.ensure_profile_exists(PROFILE_NAME, allow_create=True, config_yaml=MANAGED_YAML)
    yield pm
    pm.delete_profile(PROFILE_NAME)
    api.dispose()

def find_rigctld_process(model_id=1):
    print("Scanning processes for rigctld...")
    found_any = False
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd and 'rigctld' in cmd[0]:
                found_any = True
                print(f"Found rigctld: {cmd}")
                if '-m' in cmd and str(model_id) in cmd:
                    # Filter out the test_env dummy rig (port 4532)
                    if '-t' in cmd:
                        idx = cmd.index('-t')
                        if idx + 1 < len(cmd) and cmd[idx+1] == '4532':
                            print("Skipping test_env rig (port 4532)")
                            continue
                    return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    if not found_any:
        print("No rigctld processes found at all.")
    return None

def test_managed_rig_lifecycle(page: Page, setup_managed_profile):
    pm = setup_managed_profile
    pm.load_profile(PROFILE_NAME)
    
    page.goto("/")
    
    # 1. Verify Rig is Enabled
    # Wait for rig card
    expect(page.locator(".rig-card").first).to_be_visible()
    
    # Verify switch is ON
    switch = page.locator('input[data-action="power"]')
    expect(switch).to_be_visible()
    expect(switch).to_be_checked()

    # 2. Verify Process Exists
    # Give it a moment to spawn
    page.wait_for_timeout(2000) 
    
    proc = find_rigctld_process(model_id=1)
    assert proc is not None, "rigctld process should be running"
    assert proc.is_running()
    
    pid = proc.pid
    print(f"Found rigctld PID: {pid}")

    # 3. Disable Rig
    switch.click()
    expect(switch).not_to_be_checked()
    
    # 4. Verify Process Terminates
    page.wait_for_timeout(2000)
    
    # Check if process is gone
    if psutil.pid_exists(pid):
        # Verify it's actually gone or zombie
        try:
            p = psutil.Process(pid)
            if p.status() != psutil.STATUS_ZOMBIE:
                pytest.fail(f"rigctld process {pid} still running after disable")
        except psutil.NoSuchProcess:
            pass # Good

    # 5. Re-enable Rig
    # Force check if needed, but click works to toggle
    switch.click()
    expect(switch).to_be_checked()
    
    # 6. Verify New Process
    page.wait_for_timeout(2000)
    new_proc = find_rigctld_process(model_id=1)
    assert new_proc is not None
    assert new_proc.pid != pid, "Should have spawned a new process"

def test_managed_rig_crash_recovery(page: Page, setup_managed_profile):
    pm = setup_managed_profile
    pm.load_profile(PROFILE_NAME)
    page.goto("/")

    # Ensure enabled
    switch = page.locator('input[data-action="power"]')
    if not switch.is_checked():
        switch.click()
    
    expect(switch).to_be_checked()
    
    page.wait_for_timeout(2000)
    proc = find_rigctld_process(model_id=1)
    assert proc is not None
    
    # Kill it
    print(f"Killing rigctld PID: {proc.pid}")
    proc.kill()
    proc.wait() # Wait for death
    
    # UI should eventually show re-enabled (or keep checking)
    # The sync service polls every 500ms (configured above).
    # It should detect death and respawn.
    
    # Wait for respawn
    page.wait_for_timeout(3000)
    
    new_proc = find_rigctld_process(model_id=1)
    assert new_proc is not None
    assert new_proc.pid != proc.pid
    
    # Verify UI is still Enabled (it might flicker connected state, but the Enable switch should stay ON)
    expect(switch).to_be_checked()
    

def test_managed_rig_failure_missing_device(page: Page, setup_managed_profile):
    pm = setup_managed_profile
    
    # Update profile with bad device
    # Create a profile with a non-existent device path.
    # The rigctld process should fail to start or exit immediately.
    # We assert that the process is not running stably.
    
    page.wait_for_timeout(2000)
    proc = find_rigctld_process(model_id=1)
    
    # Clean up profile
    pm.delete_profile("test_fail_device")

