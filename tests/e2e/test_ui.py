import pytest
import json
from playwright.sync_api import Page, expect
from tests.e2e.utils import ProfileManager

PROFILE_NAME = "test_ui_default"
CONFIG_JSON = {
    "rigs": [
        {
            "name": "UI Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": 4532,
            "poll_interval_ms": 200,
        },
    ],
    "poll_interval_ms": 200,
}
CONFIG_YAML = json.dumps(CONFIG_JSON)

@pytest.fixture(scope="module", autouse=True)
def setup_profile(base_url, playwright):
    # API context for setup
    api = playwright.request.new_context(base_url=base_url)
    pm = ProfileManager(api)
    
    pm.ensure_profile_exists(PROFILE_NAME, allow_create=True, config_yaml=CONFIG_YAML)
    pm.load_profile(PROFILE_NAME)
    
    yield
    
    # Cleanup
    pm.delete_profile(PROFILE_NAME)
    api.dispose()

def test_sync_all_once_button_removed(page: Page, profile_manager: ProfileManager):
    page.goto("/")
    # Reload profile to be safe
    profile_manager.load_profile(PROFILE_NAME)
    page.reload()
    
    btn = page.locator("#syncAllOnce")
    expect(btn).not_to_be_visible()

def test_server_debug_turnstile(page: Page, profile_manager: ProfileManager):
    page.goto("/")
    profile_manager.load_profile(PROFILE_NAME)
    page.reload()

    section = page.locator("#serverDebugSection")
    toggle = page.locator("#toggleServerDebug")

    expect(section).to_be_visible()
    expect(section).to_have_class(re.compile(r"collapsed"))

    expect(toggle).to_contain_text("TCP Traffic")
    expect(toggle).to_have_text(re.compile(r"TCP Traffic \((TCP|\d+)\)"))

    icon = toggle.locator(".turnstile")
    expect(icon).to_have_text("▼")

    toggle.click()
    expect(section).not_to_have_class(re.compile(r"collapsed"))

    log = page.locator("#serverDebugLog")
    expect(log).to_be_visible()

def test_main_rig_no_sync_button(page: Page, profile_manager: ProfileManager):
    page.goto("/")
    profile_manager.load_profile(PROFILE_NAME)
    page.reload()

    expect(page.locator(".rig-card").first).to_be_visible()
    
    rig0 = page.locator("#rig-0")
    expect(rig0).to_be_visible()

    sync_btn = rig0.locator('button[data-action="sync"]')
    expect(sync_btn).to_be_hidden()

def test_turnstile_arrow_direction(page: Page, profile_manager: ProfileManager):
    page.goto("/")
    profile_manager.load_profile(PROFILE_NAME)
    page.reload()

    expect(page.locator(".rig-card").first).to_be_visible()
    
    rig0 = page.locator("#rig-0")
    expect(rig0).to_be_visible()

    vfo_section = rig0.locator('.rig-section[data-section="vfo"]')
    vfo_header = vfo_section.locator('.rig-section-header')
    vfo_icon = vfo_header.locator('.turnstile')

    expect(vfo_icon).to_have_text("▼")

def test_settings_band_presets_turnstile(page: Page):
    page.goto("/settings")
    
    rig_list = page.locator("#rigList")
    expect(rig_list).to_be_visible()
    expect(rig_list.locator("fieldset").first).to_be_visible()

    rig0 = rig_list.locator("fieldset").first
    band_section = rig0.locator('.rig-section[data-role="band-presets-section"]')
    header = band_section.locator(".rig-section-header")
    icon = header.locator(".turnstile")

    expect(icon).to_have_text("▼")

import re
