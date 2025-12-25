import json
from playwright.sync_api import APIRequestContext, APIResponse
from typing import Optional, List, Any, Dict

class ProfileManager:
    def __init__(self, request: APIRequestContext):
        self.request = request

    def _json_or_text(self, res: APIResponse) -> Any:
        try:
            return res.json()
        except Exception:
            try:
                return {"error": res.text()}
            except Exception:
                return {"error": ""}

    def list_profiles(self) -> List[str]:
        res = self.request.get("/api/config/profiles")
        if not res.ok:
            body = self._json_or_text(res)
            # Try to distinguish error
            raise RuntimeError(body.get("error") or f"failed to list profiles ({res.status})")
        data = res.json()
        return [str(p) for p in data.get("profiles", [])]

    def ensure_profile_exists(
        self, 
        name: str, 
        allow_create: bool = True, 
        config_yaml: Optional[str] = None
    ) -> None:
        profiles = self.list_profiles()
        if name in profiles:
            return

        if not allow_create:
            raise RuntimeError(f"profile not found: {name}")
        if not config_yaml:
            raise RuntimeError(f"profile missing and no config provided: {name}")

        cfg_obj = None
        try:
            cfg_obj = json.loads(config_yaml)
        except Exception:
            pass

        applied = False
        if cfg_obj and isinstance(cfg_obj, dict):
            res = self.request.post("/api/config", data=cfg_obj)
            if res.ok:
                applied = True

        if not applied:
            import_res = self.request.post(
                "/api/config/import", 
                data=config_yaml,
                headers={"Content-Type": "text/yaml"}
            )
            if not import_res.ok:
                body = self._json_or_text(import_res)
                raise RuntimeError(body.get("error") or f"failed to apply config (import) ({import_res.status})")

        save_res = self.request.post(f"/api/config/profiles/{name}")
        if not save_res.ok:
            body = self._json_or_text(save_res)
            raise RuntimeError(body.get("error") or f"failed to save profile ({save_res.status})")

        if name not in self.list_profiles():
            raise RuntimeError(f"profile save did not persist: {name}")

    def load_profile(self, name: str) -> None:
        res = self.request.post(f"/api/config/profiles/{name}/load")
        if not res.ok:
            body = self._json_or_text(res)
            raise RuntimeError(body.get("error") or f"failed to load profile ({res.status})")
        
        json_body = res.json()
        if json_body.get("status") != "ok":
            raise RuntimeError(json_body.get("error") or "failed to load profile")

    def delete_profile(self, name: str) -> bool:
        res = self.request.delete(f"/api/config/profiles/{name}")
        if not res.ok:
            if res.status == 404:
                return False
            body = self._json_or_text(res)
            raise RuntimeError(body.get("error") or f"failed to delete profile ({res.status})")
        
        json_body = res.json()
        if json_body.get("status") != "ok":
            raise RuntimeError(json_body.get("error") or "failed to delete profile")
        return True

    def create_proxy(self, proxy_data: Dict[str, Any]) -> APIResponse:
        local_port = proxy_data["local_port"]
        try:
            self.request.delete(f"http://127.0.0.1:9000/api/proxies/{local_port}")
        except Exception:
            pass
        
        res = self.request.post("http://127.0.0.1:9000/api/proxies", data=proxy_data)
        return res

    def delete_proxy(self, local_port: int) -> None:
        try:
            self.request.delete(f"http://127.0.0.1:9000/api/proxies/{local_port}")
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        res = self.request.get("/api/status")
        if not res.ok:
            return {}
        return res.json()

    def wait_for_status(self, condition_fn, timeout: float = 10, interval: float = 0.2) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            status = self.get_status()
            if status and condition_fn(status):
                return True
            time.sleep(interval)
        return False

    def wait_for_profile_load(self, name: str, timeout: float = 10) -> bool:
        return self.wait_for_status(lambda s: s.get("active_profile") == name, timeout=timeout)

    def wait_for_ready(self, profile_name: str, rig_count: int = 2, timeout: float = 10) -> bool:
        """Wait for profile to be active and rigs to be connected."""
        return self.wait_for_status(
            lambda s: s.get("active_profile") == profile_name and 
                      len(s.get("rigs", [])) >= rig_count and
                      all(r.get("connected") for r in s.get("rigs")[:rig_count]),
            timeout=timeout
        )

    def wait_for_caps(self, rig_index: int = 0, timeout: float = 10) -> bool:
        """Wait for capabilities to be detected for a rig."""
        return self.wait_for_status(
            lambda s: len(s.get("rigs", [])) > rig_index and 
                      s["rigs"][rig_index].get("caps") is not None,
            timeout=timeout
        )

    def wait_for_netmind_history(self, proxy_name: str, condition_fn, limit: int = 500, timeout: int = 10) -> bool:
        start = time.time()
        while time.time() - start < timeout:
            try:
                res = self.request.get(f"http://127.0.0.1:9000/api/history", params={"limit": limit, "proxy_name": proxy_name})
                if res.ok:
                    history = res.json()
                    match = next((p for p in history if condition_fn(p)), None)
                    if match:
                        return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

import socket
import threading
import time

class FakeRigctld:
    def __init__(self, frequency=14074000, mode="USB", passband=2400):
        self.freq = frequency
        self.mode = mode
        self.passband = passband
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1', 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self.running = True
        self.thread = threading.Thread(target=self._run)
        self.thread.start()

    def _run(self):
        while self.running:
            try:
                self.sock.settimeout(1.0)
                try:
                    conn, _ = self.sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                
                with conn:
                    conn.settimeout(None)
                    buf = b''
                    while self.running:
                        data = conn.recv(1024)
                        if not data: break
                        buf += data
                        if b'\n' in buf:
                            lines = buf.split(b'\n')
                            buf = lines[-1] # process last partial line later
                            for line in lines[:-1]:
                                msg = line.decode('utf-8', errors='ignore').strip()
                                self._handle_command(conn, msg)
            except Exception:
                pass

    def _handle_command(self, conn, cmd):
        # Handle dump_caps
        if '\\dump_caps' in cmd or 'dump_caps' in cmd:
            # Return capability dump
            resp = [
                'Model Name', 'Fake',
                'Model ID', '9999',
                'Can set Frequency', 'Y',
                'Can get Frequency', 'Y',
                'Can set Mode', 'Y',
                'Can get Mode', 'Y',
                'Can set PTT', 'Y',
                'Can get PTT', 'Y',
                'Preamp', '0',
                'Attenuator', '0',
                'Max RIT', '0',
                'Max XIT', '0',
                'Max IF Shift', '0',
                'Has Tuning Step', 'Y',
                'Has Tuning Step', 'Y', # Matches dump_caps logic usually
                'Filters', 
                '2400',
                'End Filters',
                'Frequency Ranges',
                '100000 30000000 0x1', # HF
                '144000000 148000000 0x2', # 2m
                'End Frequency Ranges',
                'RPRT 0',
                ''
            ]
            conn.sendall('\n'.join(resp).encode())
            return

        if '\\dump_state' in cmd or 'dump_state' in cmd:
             resp = [
                'dump_state:',
                'stub',
                'stub',
                '1000000 2000000000',
                '1000000 2000000000',
                'RPRT 0',
                ''
             ]
             conn.sendall('\n'.join(resp).encode())
             return

        if cmd == 'f':
             conn.sendall(f'Frequency: {self.freq}\nRPRT 0\n'.encode())
             return
        if cmd == 'm':
             conn.sendall(f'Mode: {self.mode}\nPassband: {self.passband}\nRPRT 0\n'.encode())
             return
             
        conn.sendall(b'RPRT -1\n')

    def stop(self):
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        self.sock.close()
        self.thread.join()
