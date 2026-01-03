from __future__ import annotations
import asyncio
import os
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict, Any

import yaml
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
try:
    import orjson
    from fastapi.responses import ORJSONResponse
except ImportError:
    ORJSONResponse = JSONResponse
from fastapi.templating import Jinja2Templates

from .config import AppConfig, save_config, _migrate_config
from .core import apply_config, ensure_default_profile

router = APIRouter(default_response_class=ORJSONResponse)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Pages
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request, "assets_ts": int(time.time() * 1000), "app_version": getattr(request.app, "version", ""),
    })

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request, "config": request.app.state.config, "assets_ts": int(time.time() * 1000), "app_version": getattr(request.app, "version", ""),
    })

# API
@router.get("/api/config")
async def get_config(request: Request):
    return request.app.state.config

@router.post("/api/config")
async def update_config(request: Request, cfg: AppConfig):
    await apply_config(request.app, cfg)
    return {"status": "ok"}

@router.get("/api/config/export")
async def export_config(request: Request):
    content = yaml.safe_dump(request.app.state.config.model_dump(), sort_keys=False)
    return Response(content=content, media_type="text/yaml")

@router.post("/api/config/import")
async def import_config(request: Request):
    try:
        body = await request.body()
        data = yaml.safe_load(body)
        if not isinstance(data, dict):
            return ORJSONResponse({"status": "error", "error": "Invalid YAML: expected dictionary"}, status_code=400)
        cfg = AppConfig.model_validate(_migrate_config(data))
        await apply_config(request.app, cfg)
        return {"status": "ok"}
    except Exception as e:
        return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

@router.get("/api/config/profiles")
async def list_config_profiles(request: Request):
    ensure_default_profile(request.app)
    return {"status": "ok", "profiles": request.app.state.profiles.list_names()}

@router.get("/api/config/active_profile")
async def get_active_profile(request: Request):
    ensure_default_profile(request.app)
    return {"status": "ok", "name": getattr(request.app.state, "active_profile_name", "")}

@router.post("/api/config/profiles/{name}/create")
async def create_config_profile(request: Request, name: str):
    if not request.app.state.profiles.is_valid_name(name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    if request.app.state.profiles.exists(name):
        return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
    request.app.state.profiles.save_data(name, request.app.state.config.model_dump())
    return {"status": "ok"}

@router.post("/api/config/profiles/{name}/rename")
async def rename_config_profile(request: Request, name: str, payload: dict):
    new_name = str((payload or {}).get("new_name") or "").strip()
    if not request.app.state.profiles.is_valid_name(name) or not request.app.state.profiles.is_valid_name(new_name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    if name == new_name: return {"status": "ok"}
    try:
        request.app.state.profiles.rename(name, new_name)
    except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
    except FileExistsError: return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
    if getattr(request.app.state, "active_profile_name", "") == name:
        request.app.state.active_profile_name = new_name
        request.app.state.profiles.persist_active_name(request.app.state.active_profile_name)
    return {"status": "ok"}

@router.post("/api/config/profiles/{name}/duplicate")
async def duplicate_config_profile(request: Request, name: str, payload: dict):
    new_name = str((payload or {}).get("new_name") or "").strip()
    if not request.app.state.profiles.is_valid_name(name) or not request.app.state.profiles.is_valid_name(new_name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    if request.app.state.profiles.exists(new_name):
        return ORJSONResponse({"status": "error", "error": "profile already exists"}, status_code=409)
    try:
        data = request.app.state.profiles.load_data(name)
        request.app.state.profiles.save_data(new_name, data)
        return {"status": "ok"}
    except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)

@router.post("/api/config/profiles/{name}")
async def save_config_profile(request: Request, name: str):
    if not request.app.state.profiles.is_valid_name(name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    request.app.state.profiles.save_data(name, request.app.state.config.model_dump())
    return {"status": "ok"}

@router.get("/api/config/profiles/{name}/export")
async def export_config_profile(request: Request, name: str):
    if not request.app.state.profiles.is_valid_name(name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    try:
        data = request.app.state.profiles.load_data(name)
        return Response(content=yaml.safe_dump(data, sort_keys=False), media_type="text/yaml")
    except FileNotFoundError: return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
    except Exception as e: return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

@router.post("/api/config/profiles/{name}/load")
async def load_config_profile(request: Request, name: str):
    if not request.app.state.profiles.is_valid_name(name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    try:
        data = request.app.state.profiles.load_data(name)
        cfg = AppConfig(**data)
        await apply_config(request.app, cfg)
        request.app.state.active_profile_name = name
        request.app.state.profiles.persist_active_name(name)
        return {"status": "ok"}
    except Exception as e:
        return ORJSONResponse({"status": "error", "error": str(e)}, status_code=400)

@router.delete("/api/config/profiles/{name}")
async def delete_config_profile(request: Request, name: str):
    if not request.app.state.profiles.is_valid_name(name):
        return ORJSONResponse({"status": "error", "error": "invalid profile name"}, status_code=400)
    was_active = getattr(request.app.state, "active_profile_name", "") == name
    if not request.app.state.profiles.delete(name):
        return ORJSONResponse({"status": "error", "error": "profile not found"}, status_code=404)
    if was_active:
        request.app.state.active_profile_name = ""
        request.app.state.profiles.persist_active_name("")
    ensure_default_profile(request.app)
    if was_active:
        try:
            next_name = str(getattr(request.app.state, "active_profile_name", "") or "").strip()
            if next_name:
                data = request.app.state.profiles.load_data(next_name)
                cfg = AppConfig.model_validate(_migrate_config(data))
                await apply_config(request.app, cfg)
        except Exception: pass
    return {"status": "ok"}

@router.get("/api/rigctl_listener")
async def rigctl_listener_status(request: Request):
    return {"host": request.app.state.rigctl_server.host, "port": request.app.state.rigctl_server.port}

@router.get("/api/debug/server")
async def debug_server(request: Request):
    return {"events": request.app.state.debug.server.snapshot()}

@router.get("/api/debug/rig/{idx}")
async def debug_rig(request: Request, idx: int):
    log = request.app.state.debug.rig(idx)
    return {"events": log.snapshot() if log else []}

@router.post("/api/rig/{idx}/enabled")
async def set_rig_enabled(request: Request, idx: int, payload: dict):
    if idx < 0 or idx >= len(request.app.state.config.rigs):
        return {"status": "error", "error": "rig index out of range"}
    enabled = bool(payload.get("enabled", True))
    request.app.state.config.rigs[idx].enabled = enabled
    try: 
        request.app.state.rigs[idx].cfg.enabled = enabled
        if not enabled:
            asyncio.create_task(request.app.state.rigs[idx].close())
    except Exception: pass
    save_config(request.app.state.config, request.app.state.config_path)
    return {"status": "ok", "enabled": enabled}

@router.post("/api/rig/{idx}/follow_main")
async def set_rig_follow_main(request: Request, idx: int, payload: dict):
    if idx < 0 or idx >= len(request.app.state.config.rigs):
        return {"status": "error", "error": "rig index out of range"}
    follow_main = bool(payload.get("follow_main", True))
    request.app.state.config.rigs[idx].follow_main = follow_main
    try: request.app.state.rigs[idx].cfg.follow_main = follow_main
    except Exception: pass
    save_config(request.app.state.config, request.app.state.config_path)
    return {"status": "ok", "follow_main": follow_main}

@router.post("/api/rig/{idx}/caps")
async def refresh_rig_caps(request: Request, idx: int):
    if idx < 0 or idx >= len(request.app.state.rigs):
        return {"status": "error", "error": "rig index out of range"}
    rig = request.app.state.rigs[idx]
    if not (await rig.status()).connected:
        return {"status": "error", "error": "rig not connected"}
    try:
        return {"status": "ok", **(await rig.refresh_caps())}
    except Exception as e: return {"status": "error", "error": str(e)}

@router.post("/api/rig/enabled_all")
async def set_all_rigs_enabled(request: Request, payload: dict):
    enabled = bool(payload.get("enabled", True))
    for r in request.app.state.config.rigs: r.enabled = enabled
    for rig in getattr(request.app.state, "rigs", []):
        try: rig.cfg.enabled = enabled
        except Exception: pass
    save_config(request.app.state.config, request.app.state.config_path)
    return {"status": "ok", "enabled": enabled}

@router.post("/api/rig/{idx}/sync_from_source")
async def sync_rig_from_source(request: Request, idx: int):
    if idx < 0 or idx >= len(request.app.state.rigs):
        return {"status": "error", "error": "rig index out of range"}
    src_idx = getattr(request.app.state.sync_service, 'source_index', 0)
    src, dst = request.app.state.rigs[src_idx], request.app.state.rigs[idx]
    st = await src.status()
    if not st.connected or st.frequency_hz is None:
        return {"status": "error", "error": "source rig not connected"}
    freq_ok = await dst.set_frequency(st.frequency_hz)
    mode_ok = await dst.set_mode(st.mode, st.passband) if st.mode else True
    return {"status": "ok", "freq_ok": freq_ok, "mode_ok": mode_ok}

@router.post("/api/rig/sync_all_once")
async def sync_all_once(request: Request):
    if not request.app.state.rigs: return {"status": "error", "error": "no rigs"}
    src_idx = max(0, min(getattr(request.app.state.sync_service, 'source_index', 0), len(request.app.state.rigs) - 1))
    src = request.app.state.rigs[src_idx]
    st = await src.status()
    if not st.connected or st.frequency_hz is None:
        return {"status": "error", "error": "source rig not connected"}
    results = []
    for i, rig in enumerate(request.app.state.rigs):
        if i == src_idx or not getattr(rig.cfg, "enabled", True) or not getattr(rig.cfg, "follow_main", True):
            continue
        freq_ok = await rig.set_frequency(st.frequency_hz)
        mode_ok = await rig.set_mode(st.mode, st.passband) if st.mode else True
        results.append({"index": i, "freq_ok": freq_ok, "mode_ok": mode_ok})
    return {"status": "ok", "results": results}

@router.get("/api/bind_addrs")
async def get_bind_addrs(request: Request):
    addrs = {"127.0.0.1", "0.0.0.0"}
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if ip: addrs.add(ip)
    except Exception: pass
    try:
        out = subprocess.check_output(["ifconfig"], text=True, stderr=subprocess.DEVNULL)
        for m in re.finditer(r"\binet\s+(\d+\.\d+\.\d+\.\d+)", out):
            if m.group(1): addrs.add(m.group(1))
    except Exception: pass
    return sorted(addrs)

@router.get("/api/status")
async def get_status(request: Request):
    rigs = [await r.safe_status() for r in request.app.state.rigs]
    for idx, r in enumerate(rigs): r["index"] = idx
    result = {
        "rigs": rigs,
        "active_profile": getattr(request.app.state, "active_profile_name", ""),
        "sync_enabled": request.app.state.sync_service.enabled,
        "sync_source_index": request.app.state.sync_service.source_index,
        "rigctl_to_main_enabled": getattr(request.app.state.config, "rigctl_to_main_enabled", True),
        "all_rigs_enabled": bool(rigs) and all(r.get("enabled", True) is not False for r in rigs),
    }
    if hasattr(request.app.state.sync_service, '_task'):
        result["sync_service_running"] = request.app.state.sync_service._task is not None and not request.app.state.sync_service._task.done()
    return result

@router.post("/api/sync")
async def set_sync(request: Request, payload: dict):
    if "enabled" in payload:
        request.app.state.sync_service.enabled = bool(payload["enabled"])
        request.app.state.config.sync_enabled = request.app.state.sync_service.enabled
    if "source_index" in payload:
        try: request.app.state.sync_service.source_index = int(payload["source_index"])
        except Exception: pass
        request.app.state.config.sync_source_index = request.app.state.sync_service.source_index
    save_config(request.app.state.config, request.app.state.config_path)
    return {"status": "ok", "enabled": request.app.state.sync_service.enabled, "sync_source_index": request.app.state.sync_service.source_index}

@router.post("/api/rigctl_to_main")
async def set_rigctl_to_main(request: Request, payload: dict):
    enabled = bool(payload.get("enabled", True))
    request.app.state.config.rigctl_to_main_enabled = enabled
    save_config(request.app.state.config, request.app.state.config_path)
    return {"status": "ok", "enabled": enabled}

@router.post("/api/rig/{which}/set")
async def set_rig(request: Request, which: str, payload: dict):
    idx = {"a": 0, "b": 1}.get(which.lower())
    if idx is None:
        try: idx = int(which)
        except ValueError: return {"status": "error", "error": "invalid rig index"}
    if idx < 0 or idx >= len(request.app.state.rigs):
        return {"status": "error", "error": "rig index out of range"}
    
    rig, res = request.app.state.rigs[idx], {}
    freq, mode, pb, vfo = payload.get("frequency_hz"), payload.get("mode"), payload.get("passband"), payload.get("vfo")
    
    if freq is not None:
        hz = int(freq)
        if not getattr(rig.cfg, "allow_out_of_band", False):
            presets = [p for p in getattr(rig.cfg, "band_presets", []) if getattr(p, "enabled", True) is not False]
            ranges = [(getattr(p, "lower_hz", None), getattr(p, "upper_hz", None)) for p in presets]
            if any(r[0] is not None and r[1] is not None for r in ranges):
                if not any(r[0] is not None and r[1] is not None and hz >= int(r[0]) and hz <= int(r[1]) for r in ranges):
                    return {"status": "error", "error": "frequency out of configured band ranges", "frequency_hz": hz}
        res["freq_ok"] = await rig.set_frequency(hz)
    if mode is not None: res["mode_ok"] = await rig.set_mode(str(mode), pb)
    if vfo is not None: res["vfo_ok"] = await rig.set_vfo(str(vfo))
    return {"status": "ok", **res}

@router.post("/api/test-rig")
async def test_rig_connection(request: Request, rig_config: dict):
    from .config import RigConfig, parse_dump_state_ranges, detect_bands_from_ranges
    from .rig import RigClient
    try:
        cfg = RigConfig.model_validate(rig_config)
        test_rig = RigClient(cfg)
        try:
            status = await test_rig.safe_status()
            detected_bands = []
            try:
                lines = await test_rig.dump_state()
                if lines:
                    detected_bands = [{"label": p.label, "frequency_hz": p.frequency_hz, "enabled": p.enabled, "lower_hz": p.lower_hz, "upper_hz": p.upper_hz} 
                                     for p in detect_bands_from_ranges(parse_dump_state_ranges(lines))]
            except Exception: pass
            caps = await test_rig.refresh_caps() if status.get("connected") else None
            await test_rig.close()
            if status.get("error"): return {"status": "error", "message": f"Connection failed: {status['error']}", "details": status}
            
            msg = f"Connected successfully! Frequency: {status['frequency_hz']} Hz, Mode: {status.get('mode', 'unknown')}."
            if detected_bands: msg += f" Detected {len(detected_bands)} supported bands."
            return {"status": "success", "message": msg, "details": status, "detected_bands": detected_bands, "caps": (caps or {}).get("caps", {}), "modes": (caps or {}).get("modes", [])}
        except Exception as e:
            await test_rig.close()
            return {"status": "error", "message": f"Connection test failed: {str(e)}", "details": {"error": str(e)}}
    except Exception as e: return {"status": "error", "message": f"Invalid configuration: {str(e)}", "details": {"error": str(e)}}

@router.get("/api/serial-ports")
async def list_serial_ports(request: Request):
    try:
        import serial.tools.list_ports
        return {"status": "ok", "ports": [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in serial.tools.list_ports.comports()]}
    except ImportError: return {"status": "error", "message": "pyserial not installed.", "ports": []}
    except Exception as e: return {"status": "error", "message": str(e), "ports": []}

@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        # We need app from ws.app or similar? WebSocket has app via scope?
        # ws.app doesn't exist directly usually, but ws.scope['app'] does?
        # Actually starlette WebSocket exposes .app property.
        
        # Helper to get status using app attached to WS
        async def get_app_status():
            rigs = [await r.safe_status() for r in ws.app.state.rigs]
            for idx, r in enumerate(rigs): r["index"] = idx
            result = {
                "rigs": rigs,
                "active_profile": getattr(ws.app.state, "active_profile_name", ""),
                "sync_enabled": ws.app.state.sync_service.enabled,
                "sync_source_index": ws.app.state.sync_service.source_index,
                "rigctl_to_main_enabled": getattr(ws.app.state.config, "rigctl_to_main_enabled", True),
                "all_rigs_enabled": bool(rigs) and all(r.get("enabled", True) is not False for r in rigs),
            }
            if hasattr(ws.app.state.sync_service, '_task'):
                result["sync_service_running"] = ws.app.state.sync_service._task is not None and not ws.app.state.sync_service._task.done()
            return result

        await ws.send_json(await get_app_status())
        while True:
            interval = max(0.1, ws.app.state.config.poll_interval_ms / 1000.0)
            await asyncio.sleep(interval)
            await ws.send_json(await get_app_status())
    except (WebSocketDisconnect, Exception): pass
