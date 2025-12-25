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
