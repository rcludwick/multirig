#!/usr/bin/env python3
import sys
import shutil
from pathlib import Path

try:
    import rjsmin
    import rcssmin
except ImportError:
    print("Minification libraries not found. Run 'pip install multirig[dev]' or manually install rjsmin and rcssmin.")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "multirig" / "static"

def minify_js(path: Path):
    print(f"Minifying {path.name}...")
    with open(path, "r") as f:
        content = f.read()
    minified = rjsmin.jsmin(content)
    dest = path.with_suffix(".min.js")
    with open(dest, "w") as f:
        f.write(minified)
    print(f"Created {dest.name}")

def minify_css(path: Path):
    print(f"Minifying {path.name}...")
    with open(path, "r") as f:
        content = f.read()
    minified = rcssmin.cssmin(content)
    dest = path.with_suffix(".min.css")
    with open(dest, "w") as f:
        f.write(minified)
    print(f"Created {dest.name}")

def main():
    if not STATIC.exists():
        print(f"Static directory not found at {STATIC}")
        sys.exit(1)

    for js_file in STATIC.glob("*.js"):
        if js_file.name.endswith(".min.js"):
            continue
        minify_js(js_file)

    for css_file in STATIC.glob("*.css"):
        if css_file.name.endswith(".min.css"):
            continue
        minify_css(css_file)

    print("Minification complete.")

if __name__ == "__main__":
    main()
