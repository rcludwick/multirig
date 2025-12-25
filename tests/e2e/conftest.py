import os
import time
import subprocess
import requests
import pytest
from tests.e2e.utils import ProfileManager

@pytest.fixture(scope="session")
def base_url():
    """Override base_url for pytest-playwright/pytest-base-url."""
    return "http://127.0.0.1:8001"

@pytest.fixture(scope="session", autouse=True)
def test_env(base_url):
    """Start all required services for E2E testing."""
    processes = []
    
    # 1. Start Netmind (9000)
    netmind_cmd = ["uv", "run", "uvicorn", "netmind.app:app", "--host", "127.0.0.1", "--port", "9000"]
    print(f"Starting Netmind: {netmind_cmd}")
    netmind = subprocess.Popen(
        netmind_cmd,
        cwd="ext/netmind",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE # Capture stderr for debugging if needed
    )
    processes.append(netmind)

    # 2. Start Dummy Rigctld (4532)
    # Using system rigctld since we removed ext/hamlib
    rigctl_cmd = ["rigctld", "-m", "1", "-r", "/dev/null", "-t", "4532"]
    print(f"Starting Rigctld: {rigctl_cmd}")
    rigctl = subprocess.Popen(
        rigctl_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(rigctl)
    
    # 3. Start MultiRig (8001)
    env = os.environ.copy()
    env.update({
        "MULTIRIG_TEST_MODE": "1",
        "MULTIRIG_RIGCTL_PORT": "4534", # Why 4534? JS config said 4534, but rigctld is on 4532?
                                        # Ah, maybe MultiRig connects to 4532?
                                        # Config default is 4532.
                                        # JS Config env: MULTIRIG_RIGCTL_PORT: '4534'
                                        # BUT JS Config rigctld: port 4532.
                                        # This implies MultiRig might NOT be connecting to this dummy rig by default?
                                        # Or mismatch? 
                                        # I'll stick to 4532 for rigctld and remove the env var override unless needed.
                                        # Wait, ui.spec.js configures rig on 4532.
                                        # So MultiRig server default rigctl params matter less if we configure explicitly.
                                        # But let's copy the ENV vars just in case.
        "MULTIRIG_RIGCTL_HOST": "127.0.0.1",
        "OPEN_BROWSER": "0",
        "PORT": "8001",
    })
    
    # run.sh uses uvicorn. We can call uv run directly to avoid shell script parsing issues if env vars tricky
    # But run.sh is simple.
    print(f"Starting MultiRig on 8001...")
    multirig = subprocess.Popen(
        ["./run.sh"],
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    processes.append(multirig)
    
    # Wait for services
    def wait_for(url, timeout=10):
        start = time.time()
        while time.time() - start < timeout:
            try:
                requests.get(url, timeout=1)
                return True
            except requests.ConnectionError:
                time.sleep(0.5)
        return False

    if not wait_for("http://127.0.0.1:9000/api/proxies", 10):
        print("Netmind failed to start")
    
    # Rigctld doesn't have HTTP, check port? Or assume it starts fast.
    time.sleep(1) 

    if not wait_for(f"{base_url}/api/status", 15):
        # Dump stderr if failed
        if multirig.poll() is not None:
            print("MultiRig failed to start.")
            print(multirig.stderr.read().decode())
        raise RuntimeError("MultiRig server failed to start on 8001")

    yield

    # Cleanup
    print("Stopping test services...")
    for p in processes:
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill()


@pytest.fixture
def profile_manager(page):
    return ProfileManager(page.request)

@pytest.fixture
def api_manager(playwright, base_url):
    # Fixture for API-only tests without browser overhead
    api_request_context = playwright.request.new_context(base_url=base_url)
    yield ProfileManager(api_request_context)
    api_request_context.dispose()
