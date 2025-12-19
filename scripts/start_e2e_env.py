#!/usr/bin/env python3
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
import httpx
import yaml

# Constants
NETMIND_PORT = 8002
RIG1_PORT = 4534  # Rig 1 (Model 1)
RIG2_PORT = 4535  # Rig 2 (Model 6)

# NetMind Proxies
PROXY_RIG1_PORT = 9001
PROXY_RIG2_PORT = 9002
PROXY_MULTIRIG_PORT = 9003

MULTIRIG_SERVER_PORT = 4532  # Default Multirig rigctl server port

# Paths
ROOT_DIR = Path(__file__).parent.parent.resolve()
EXT_DIR = ROOT_DIR / "ext"
NETMIND_DIR = EXT_DIR / "netmind"
RIGCTLD_PATH = EXT_DIR / "hamlib" / "prefix" / "bin" / "rigctld"

# Config output
CONFIG_DIR = ROOT_DIR / "multirig.config.profiles"
CONFIG_FILE = CONFIG_DIR / "netmind_e2e.yaml"

# Daemon files
PID_FILE = ROOT_DIR / "e2e_env.pid"
LOG_FILE = ROOT_DIR / "e2e_env.log"


def check_prereqs():
    if not RIGCTLD_PATH.exists():
        print(f"Error: rigctld not found at {RIGCTLD_PATH}")
        print("Please run 'make hamlib-install' first.")
        sys.exit(1)


def daemonize():
    """
    Detach from the terminal and run in the background.
    Double-fork mechanism.
    """
    # Flush current I/O before forking
    sys.stdout.flush()
    sys.stderr.flush()

    # Fork 1
    try:
        pid = os.fork()
        if pid > 0:
            # Parent returns immediately
            # We wait for the second fork to print the PID? 
            # Actually, standard is parent exits. 
            # We can rely on the first child to print the PID of the second child.
            os.waitpid(pid, 0)
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #1 failed: {e}\n")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)

    # Fork 2
    try:
        pid = os.fork()
        if pid > 0:
            # First child prints the PID of the daemon (second child) then exits
            print(f"Background process started. PID: {pid}")
            print(f"Logs redirected to: {LOG_FILE}")
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"fork #2 failed: {e}\n")
        sys.exit(1)

    # Write PID to file (from the daemon process)
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    si = open(os.devnull, 'r')
    so = open(LOG_FILE, 'a+')
    se = open(LOG_FILE, 'a+')

    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


async def wait_for_port(port, timeout=5):
    start = time.time()
    while time.time() - start < timeout:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.1)
    return False


async def start_netmind():
    print(f"[*] Starting NetMind on port {NETMIND_PORT}...")
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(NETMIND_DIR)
    
    # Use the python executable from the netmind venv if it exists
    netmind_python = NETMIND_DIR / ".venv" / "bin" / "python"
    if not netmind_python.exists():
        netmind_python = NETMIND_DIR / ".venv" / "Scripts" / "python.exe"
    
    python_exe = str(netmind_python) if netmind_python.exists() else sys.executable
    cmd = [python_exe, "-m", "netmind.app", "--port", str(NETMIND_PORT)]
    
    proc = subprocess.Popen(
        cmd, 
        cwd=NETMIND_DIR, 
        env=env, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        text=True
    )
    
    if await wait_for_port(NETMIND_PORT):
        print("[*] NetMind started.")
        return proc
    else:
        print("[!] NetMind failed to start.")
        stdout, stderr = proc.communicate(timeout=1)
        print("NetMind STDOUT:", stdout)
        print("NetMind STDERR:", stderr)
        proc.kill()
        sys.exit(1)


def start_rigctld(port, model):
    print(f"[*] Starting rigctld (Model {model}) on port {port}...")
    
    proc = subprocess.Popen(
        [str(RIGCTLD_PATH), "-m", str(model), "-t", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return proc


async def configure_netmind_proxies():
    print("[*] Configuring NetMind proxies...")
    async with httpx.AsyncClient() as client:
        base_url = f"http://127.0.0.1:{NETMIND_PORT}"
        
        proxies = [
            {
                "name": "Rig 1 (Model 1)",
                "local_port": PROXY_RIG1_PORT,
                "target_host": "127.0.0.1",
                "target_port": RIG1_PORT,
                "protocol": "hamlib"
            },
            {
                "name": "Rig 2 (Model 6)",
                "local_port": PROXY_RIG2_PORT,
                "target_host": "127.0.0.1",
                "target_port": RIG2_PORT,
                "protocol": "hamlib"
            },
            {
                "name": "Multirig Server",
                "local_port": PROXY_MULTIRIG_PORT,
                "target_host": "127.0.0.1",
                "target_port": MULTIRIG_SERVER_PORT,
                "protocol": "hamlib"
            }
        ]
        
        for p in proxies:
            try:
                resp = await client.post(f"{base_url}/api/proxies", json=p)
                resp.raise_for_status()
                print(f"    + Added proxy: {p['name']} ({p['local_port']} -> {p['target_port']})")
            except Exception as e:
                print(f"    ! Failed to add proxy {p['name']}: {e}")


def generate_multirig_config():
    print(f"[*] Generating Multirig config at {CONFIG_FILE}...")
    config = {
        "rigs": [
            {
                "name": "NetMind Rig 1",
                "connection_type": "rigctld",
                "host": "127.0.0.1",
                "port": PROXY_RIG1_PORT, 
                "enabled": True,
                "follow_main": True
            },
            {
                "name": "NetMind Rig 2",
                "connection_type": "rigctld",
                "host": "127.0.0.1",
                "port": PROXY_RIG2_PORT, 
                "enabled": True,
                "follow_main": True
            }
        ],
        "rigctl_listen_host": "0.0.0.0",
        "rigctl_listen_port": MULTIRIG_SERVER_PORT,
        "sync_enabled": True,
        "poll_interval_ms": 500
    }
    
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f)


async def start_multirig():
    print(f"[*] Starting Multirig with profile {CONFIG_FILE.name}...")
    
    active_profile_path = ROOT_DIR / "multirig.config.active_profile"
    
    if active_profile_path.exists() or active_profile_path.is_symlink():
        try:
            os.remove(active_profile_path)
        except OSError:
            pass
            
    with open(active_profile_path, "w") as f:
        f.write(CONFIG_FILE.stem)
        
    cmd = [sys.executable, "-m", "multirig"]
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        env=env,
        stdout=sys.stdout, # Already redirected to log file in daemon
        stderr=sys.stderr
    )
    
    if await wait_for_port(MULTIRIG_SERVER_PORT, timeout=10):
        print(f"[*] Multirig started on port {MULTIRIG_SERVER_PORT}.")
        return proc
    else:
        print("[!] Multirig failed to start (or timed out waiting for port).")
        proc.kill()
        return None


async def main():
    import sys
    do_verify = "--verify" in sys.argv

    check_prereqs()
    
    procs = []
    
    # Signal handling for graceful shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        print("\n[*] Signal received, shutting down...")
        shutdown_event.set()

    loop.add_signal_handler(signal.SIGTERM, signal_handler)
    loop.add_signal_handler(signal.SIGINT, signal_handler)

    try:
        # 1. Start NetMind
        netmind_proc = await start_netmind()
        procs.append(netmind_proc)
        
        # 2. Start Rigs
        rig1 = start_rigctld(RIG1_PORT, 1)
        procs.append(rig1)
        rig2 = start_rigctld(RIG2_PORT, 6)
        procs.append(rig2)
        
        # Give them a moment
        await asyncio.sleep(1)
        
        # 3. Configure Proxies
        await configure_netmind_proxies()
        
        # 4. Generate Config & Start Multirig
        generate_multirig_config()
        multirig_proc = await start_multirig()
        if multirig_proc:
            procs.append(multirig_proc)
        else:
            raise RuntimeError("Multirig failed")
        
        print("\n" + "="*60)
        print(f"ENVIRONMENT READY")
        print("="*60)
        
        if do_verify:
            print("[*] Running verification (debug_wsjtx.py)...")
            await asyncio.sleep(2) 
            
            debug_script = ROOT_DIR / "scripts" / "debug_wsjtx.py"
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(debug_script), "127.0.0.1", str(PROXY_MULTIRIG_PORT),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            print(stdout.decode())
            if stderr:
                print("STDERR:", stderr.decode())
            
            print("[*] Verification finished.")
            # We exit after verification? Or stay running?
            # Originally it returned, meaning it would hit finally and cleanup.
            # So verification implies running then stopping.
            return

        # Open browser to NetMind and Multirig
        # Since we are daemonized, this might open in the user's session if display is set, 
        # or fail silently. We'll try.
        try:
            print("[*] Opening browsers...")
            webbrowser.open(f"http://127.0.0.1:{NETMIND_PORT}")
            webbrowser.open(f"http://127.0.0.1:8000")
        except Exception:
            pass

        print("Daemon running. Send SIGTERM to stop.")
        
        # Wait until shutdown signal
        await shutdown_event.wait()
            
    except Exception as e:
        print(f"[!] Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[*] Stopping services...")
        for p in procs:
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                p.kill()
        
        # Clean up PID file
        if PID_FILE.exists():
            PID_FILE.unlink()
            
        print("[*] Cleanup complete.")

if __name__ == "__main__":
    # Check if we should verify or just run
    # If verify is passed, we still daemonize? 
    # Usually verification runs in foreground to see output.
    # But the instruction was "modify ... to completely fork off".
    # I will stick to daemonizing unless --foreground is explicitly added (not requested) 
    # or if the user wants verification output on stdout.
    
    # If --verify is present, maybe we shouldn't fork?
    # The prompt didn't specify exceptions. I'll fork. Verification output goes to log.
    
    daemonize()
    asyncio.run(main())