#!/usr/bin/env python3
"""
Generate a JSON file containing all Hamlib-supported rig models.
Reads from rigctl --list output and creates multirig/static/rig_models.json
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_rigctl_list(rigctl_path: str) -> list:
    """Parse rigctl --list output and return list of rig models."""
    try:
        result = subprocess.run(
            [rigctl_path, "--list"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running rigctl: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: rigctl not found at {rigctl_path}", file=sys.stderr)
        sys.exit(1)

    models = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("Rig #"):
            continue

        # Parse the fixed-width columns
        # Format: Rig #  Mfg  Model  Version  Status  Macro
        parts = line.split()
        if len(parts) < 4:
            continue

        try:
            rig_id = int(parts[0])
        except ValueError:
            continue

        # Find the manufacturer (starts at column 7-8)
        # Find the model (typically after manufacturer)
        # This is a bit tricky with variable spacing, so we'll use a heuristic

        # Skip the ID and find manufacturer and model
        rest = line[line.find(parts[0]) + len(parts[0]):].strip()

        # Split by multiple spaces to find columns
        import re
        columns = re.split(r'\s{2,}', rest)

        if len(columns) < 2:
            continue

        manufacturer = columns[0].strip()
        model = columns[1].strip()

        models.append({
            "id": rig_id,
            "manufacturer": manufacturer,
            "model": model,
            "label": f"{manufacturer} {model} ({rig_id})"
        })

    return models


def _parse_bool_flag(v: str) -> bool:
    v = (v or "").strip().upper()
    return v in {"Y", "E"}


def _parse_mode_list(rest: str) -> list:
    rest = (rest or "").strip()
    if not rest or rest.startswith("None"):
        return []
    out = []
    seen = set()
    for tok in rest.split():
        t = tok.strip().rstrip(",;:")
        t = t.rstrip(".")
        if not t:
            continue
        if t == "None":
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def parse_dump_caps(text: str) -> tuple[dict, list]:
    caps: dict = {}
    modes: list = []
    modes_seen = set()
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("Mode list:"):
            _, rest = s.split(":", 1)
            for m in _parse_mode_list(rest):
                if m not in modes_seen:
                    modes_seen.add(m)
                    modes.append(m)
        if not s.startswith("Can "):
            continue
        if ":" not in s:
            continue
        key, rest = s.split(":", 1)
        flag = rest.strip()[:1]
        if key == "Can set Frequency":
            caps["freq_set"] = _parse_bool_flag(flag)
        elif key == "Can get Frequency":
            caps["freq_get"] = _parse_bool_flag(flag)
        elif key == "Can set Mode":
            caps["mode_set"] = _parse_bool_flag(flag)
        elif key == "Can get Mode":
            caps["mode_get"] = _parse_bool_flag(flag)
        elif key == "Can set VFO":
            caps["vfo_set"] = _parse_bool_flag(flag)
        elif key == "Can get VFO":
            caps["vfo_get"] = _parse_bool_flag(flag)
        elif key == "Can set PTT":
            caps["ptt_set"] = _parse_bool_flag(flag)
        elif key == "Can get PTT":
            caps["ptt_get"] = _parse_bool_flag(flag)
    return caps, modes


def query_model_caps(rigctl_path: str, model_id: int, timeout_s: float = 1.0) -> dict:
    try:
        result = subprocess.run(
            [rigctl_path, "-m", str(model_id), "-u"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            return {}
        caps, modes = parse_dump_caps(result.stdout)
        info: dict = {}
        if caps:
            info["caps"] = caps
        if modes:
            info["modes"] = modes
        return info
    except Exception:
        return {}


def main():
    if len(sys.argv) < 3:
        print("Usage: generate_rig_list.py <rigctl_path> <output_json_path>", file=sys.stderr)
        sys.exit(1)

    rigctl_path = sys.argv[1]
    output_path = Path(sys.argv[2])

    models = parse_rigctl_list(rigctl_path)

    # Best-effort caps probing. This can take a while on large Hamlib installs.
    # Concurrency and timeouts keep this bounded.
    timeout_s = float(os.getenv("MULTIRIG_RIGCAP_TIMEOUT_S", "1.0"))
    max_workers = int(os.getenv("MULTIRIG_RIGCAP_WORKERS", str(min(16, (os.cpu_count() or 4) * 2))))

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(query_model_caps, rigctl_path, m["id"], timeout_s): m for m in models
        }
        for fut in as_completed(futures):
            m = futures[fut]
            try:
                info = fut.result()
            except Exception:
                info = {}
            if info.get("caps"):
                m["caps"] = info["caps"]
            if info.get("modes"):
                m["modes"] = info["modes"]

    # Sort by manufacturer, then model
    models.sort(key=lambda x: (x["manufacturer"].lower(), x["model"].lower()))

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON
    with output_path.open("w") as f:
        json.dump(models, f, indent=2)

    print(f"Generated {len(models)} rig models -> {output_path}")


if __name__ == "__main__":
    main()

