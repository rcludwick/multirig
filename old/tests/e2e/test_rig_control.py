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

        # Navigate to Settings (React uses NavLink)
        page.get_by_role("link", name="Settings").click()
        expect(page).to_have_url(re.compile(r"/settings"))

        # React uses data-testid for rig config cards
        first_rig = page.locator('[data-testid="rig-config-0"]')
        color_input = first_rig.locator('[data-testid="rig-color-0"]')
        expect(color_input).to_be_visible()
        color_input.fill("#ff0000")
        expect(color_input).to_have_value("#ff0000")

        # Auto-save - wait for save to complete
        page.wait_for_timeout(1500)

        # Navigate to Dashboard
        page.get_by_role("link", name="Dashboard").click()
        expect(page).to_have_url(re.compile(r"/$"))

        # React uses data-testid for LCD
        lcd = page.locator('[data-testid="rig-lcd-0"]')
        expect(lcd).to_be_visible()
        # Check style for red
        expect(lcd).to_have_attribute("style", re.compile(r"linear-gradient.*(?:#ff0000|255,\s*0,\s*0)", re.I))

        # Reset color
        page.get_by_role("link", name="Settings").click()
        first_rig_reset = page.locator('[data-testid="rig-config-0"]')
        # Type the default color directly
        first_rig_reset.locator('[data-testid="rig-color-0"]').fill("#a4c356")

        # Auto-save - wait for save to complete
        page.wait_for_timeout(1500)

        page.get_by_role("link", name="Dashboard").click()
        lcd_reset = page.locator('[data-testid="rig-lcd-0"]')
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

        # React uses data-testid
        card0 = page.locator('[data-testid="rig-card-0"]')
        expect(card0).to_be_visible()
        power0 = card0.locator('[data-testid="power-switch-0"] input')
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
        card0b = page.locator('[data-testid="rig-card-0"]')
        expect(card0b).to_be_visible()
        power0b = card0b.locator('[data-testid="power-switch-0"] input')
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

        # React uses data-testid
        rig1 = page.locator('[data-testid="rig-card-1"]')
        expect(rig1).to_be_visible(timeout=10000)
        expect(rig1).not_to_have_class(re.compile(r"disabled"))

        toggle = rig1.locator('[data-testid="follow-switch-1"] input')
        expect(toggle).to_be_visible()
        expect(toggle).to_be_enabled()

        toggle.click()

        error_box = rig1.locator('[data-testid="rig-error-1"]')
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
        profile_manager.wait_for_ready(profile_name, rig_count=1)

        # Debug JS errors
        page.on("console", lambda msg: print(f"BROWSER CONSOLE: {msg.text}"))

        # Clear browser cache and do fresh navigation
        page.goto("/", wait_until="networkidle")

        # React uses data-testid
        rig_card = page.locator('[data-testid="rig-card-0"]')
        expect(rig_card).to_be_visible()

        # Expand modes section first (collapsed by default)
        modes_section = rig_card.locator('[data-testid="rig-section-0-modes"]')
        modes_header = modes_section.locator('.rig-section-header')
        modes_header.click()

        # Wait for mode buttons to render
        mode_buttons = rig_card.locator('[data-testid="mode-buttons-0"]')
        expect(mode_buttons).to_be_visible(timeout=5000)

        usb_btn = mode_buttons.locator('.mode-btn', has_text="USB")
        # Wait for capabilities to load (async fetch)
        expect(usb_btn).to_be_visible(timeout=10000)

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
            "baud": 38400,
            "band_presets": [
                { "label": "40m", "frequency_hz": 7074000, "enabled": True, "lower_hz": 7000000, "upper_hz": 7300000 }
            ]
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

        # Connect to the dummy rigctld (4532) directly.
        # Verify that clicking the UI band button does not result in forwarded commands to this client.

        received_data = []

        # Connect to 4532
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 4532))
        sock.setblocking(False)

        # React uses data-testid
        rig_card = page.locator('[data-testid="rig-card-0"]')
        expect(rig_card).to_be_visible()

        # Expand bands section first (collapsed by default)
        bands_section = rig_card.locator('[data-testid="rig-section-0-bands"]')
        bands_header = bands_section.locator('.rig-section-header')
        bands_header.click()

        band_buttons = rig_card.locator('[data-testid="band-buttons-0"]')
        expect(band_buttons).to_be_visible()
        band_buttons.locator(".band-btn", has_text="40m").click()

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

def test_lcd_display_values(page: Page, profile_manager: ProfileManager):
    """Verify that the LCD displays the correct frequency and mode."""
    # Use a fake rigctld with known values
    freq = 14074000
    mode = "USB"
    rig = FakeRigctld(frequency=freq, mode=mode)

    profile_name = "test_lcd_data_py"
    config = {
        "rigs": [{
            "name": "LCD Test Rig",
            "connection_type": "rigctld",
            "host": "127.0.0.1",
            "port": rig.port,
            "poll_interval_ms": 200,
            "model_id": 2
        }],
        "poll_interval_ms": 200
    }

    try:
        profile_manager.ensure_profile_exists(profile_name, allow_create=True, config_yaml=json.dumps(config))
        profile_manager.load_profile(profile_name)
        page.goto("/")
        page.reload()

        # React uses data-testid
        rig_card = page.locator('[data-testid="rig-card-0"]')
        expect(rig_card).to_be_visible()

        # Check Frequency
        # The LCD formats frequency, e.g. "14.074.000" or similar
        # We look for the main digits
        lcd = rig_card.locator('[data-testid="rig-lcd-0"]')
        expect(lcd).to_contain_text("14.074000")

        # Check Mode
        # The mode might be in a separate element or part of the LCD text
        # Based on previous issues, it should show "USB" clearly
        expect(lcd).to_contain_text("USB")

    finally:
        rig.stop()
        profile_manager.delete_profile(profile_name)
