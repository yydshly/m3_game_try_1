#!/usr/bin/env python3
"""
scripts/validate_assets.py

Validates the visual asset pipeline:
1. Loads and parses static/assets/manifest.json
2. Checks that all referenced placeholder files exist
3. Warns if real asset files are missing (does NOT fail)
4. Fails if any placeholder is missing
5. Reports asset coverage summary
"""

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
MANIFEST_PATH = PROJECT_ROOT / "static" / "assets" / "manifest.json"
ASSETS_DIR = PROJECT_ROOT / "static" / "assets"
PLACEHOLDERS_DIR = ASSETS_DIR / "placeholders"


def green(text):
    return f"\033[92m{text}\033[0m"


def yellow(text):
    return f"\033[93m{text}\033[0m"


def red(text):
    return f"\033[91m{text}\033[0m"


def bold(text):
    return f"\033[1m{text}\033[0m"


def load_manifest():
    if not MANIFEST_PATH.exists():
        print(f"[FAIL] manifest.json not found at {MANIFEST_PATH}")
        sys.exit(1)
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            data = json.load(f)
        print(f"[OK]   manifest loaded (version={data.get('version')}, asset_mode={data.get('asset_mode')})")
        return data
    except json.JSONDecodeError as e:
        print(f"[FAIL] manifest.json is not valid JSON: {e}")
        sys.exit(1)


def check_placeholder(path_str, label):
    """Check if a placeholder file exists. Returns True if found."""
    if not path_str:
        return False
    # path_str is like /static/assets/placeholders/foo.svg
    # convert to filesystem path relative to project root
    if path_str.startswith("/"):
        path_str = path_str[1:]
    full_path = PROJECT_ROOT / path_str
    return full_path.exists()


def check_real_asset(path_str, label):
    """Check if a real asset file exists. Returns True if found."""
    if not path_str:
        return False
    if path_str.startswith("/"):
        path_str = path_str[1:]
    full_path = PROJECT_ROOT / path_str
    return full_path.exists()


def validate_scenes(data):
    scenes = data.get("scenes", {})
    print(f"\n{bold('Scenes:')} {len(scenes)} defined")
    ok = 0
    warn = 0
    fail = 0
    for name, scene in scenes.items():
        ph = scene.get("placeholder", "")
        img = scene.get("image", "")
        if check_placeholder(ph, name):
            print(f"  [OK]   placeholder exists: {ph}")
            ok += 1
        else:
            print(f"  [FAIL] placeholder missing: {ph}")
            fail += 1
        if check_real_asset(img, name):
            print(f"  [OK]   real asset exists: {img}")
        else:
            print(f"  [WARN] real asset missing: {img}")
            warn += 1
    return ok, warn, fail


def validate_characters(data):
    chars = data.get("characters", {})
    print(f"\n{bold('Characters:')} {len(chars)} defined")
    ok = 0
    warn = 0
    fail = 0
    for name, ch in chars.items():
        ph = ch.get("placeholder", "")
        portrait = ch.get("portrait", "")
        if check_placeholder(ph, name):
            print(f"  [OK]   placeholder exists: {ph}")
            ok += 1
        else:
            print(f"  [FAIL] placeholder missing: {ph}")
            fail += 1
        if check_real_asset(portrait, name):
            print(f"  [OK]   real asset exists: {portrait}")
        else:
            print(f"  [WARN] real asset missing: {portrait}")
            warn += 1
    return ok, warn, fail


def validate_evidence(data):
    ev_list = data.get("evidence", {})
    print(f"\n{bold('Evidence:')} {len(ev_list)} defined")
    ok = 0
    warn = 0
    fail = 0
    for name, ev in ev_list.items():
        ph = ev.get("placeholder", "")
        icon = ev.get("icon", "")
        if check_placeholder(ph, name):
            print(f"  [OK]   placeholder exists: {ph}")
            ok += 1
        else:
            print(f"  [FAIL] placeholder missing: {ph}")
            fail += 1
        if check_real_asset(icon, name):
            print(f"  [OK]   real asset exists: {icon}")
        else:
            print(f"  [WARN] real asset missing: {icon}")
            warn += 1
    return ok, warn, fail


def validate_endings(data):
    endings = data.get("endings", {})
    print(f"\n{bold('Endings:')} {len(endings)} defined")
    ok = 0
    warn = 0
    fail = 0
    for name, ending in endings.items():
        ph = ending.get("placeholder", "")
        img = ending.get("image", "")
        if check_placeholder(ph, name):
            print(f"  [OK]   placeholder exists: {ph}")
            ok += 1
        else:
            print(f"  [FAIL] placeholder missing: {ph}")
            fail += 1
        if check_real_asset(img, name):
            print(f"  [OK]   real asset exists: {img}")
        else:
            print(f"  [WARN] real asset missing: {img}")
            warn += 1
    return ok, warn, fail


def check_placeholder_dir():
    """Verify that placeholders directory itself exists."""
    if PLACEHOLDERS_DIR.exists():
        svg_files = list(PLACEHOLDERS_DIR.glob("*.svg"))
        print(f"\n{bold('Placeholder directory:')} {PLACEHOLDERS_DIR} ({len(svg_files)} SVG files)")
        return True
    else:
        print(f"\n[FAIL] Placeholder directory missing: {PLACEHOLDERS_DIR}")
        return False


def main():
    print(f"{bold('='*50)}")
    print(f"{bold('Visual Asset Validator')}")
    print(f"{'='*50}")

    data = load_manifest()
    print()

    # Check placeholder dir exists
    has_placeholders_dir = check_placeholder_dir()

    total_ok = 0
    total_warn = 0
    total_fail = 0

    if has_placeholders_dir:
        s_ok, s_warn, s_fail = validate_scenes(data)
        c_ok, c_warn, c_fail = validate_characters(data)
        e_ok, e_warn, e_fail = validate_evidence(data)
        en_ok, en_warn, en_fail = validate_endings(data)
        total_ok = s_ok + c_ok + e_ok + en_ok
        total_warn = s_warn + c_warn + e_warn + en_warn
        total_fail = s_fail + c_fail + e_fail + en_fail

    # Check required top-level manifest fields
    print(f"\n{bold('Manifest structure:')}")
    for field in ["version", "asset_mode", "style", "scenes", "characters", "evidence", "endings"]:
        if field in data:
            print(f"  [OK]   {field}")
        else:
            print(f"  [WARN] {field} (optional, recommended)")
            total_warn += 1

    print(f"\n{'='*50}")
    print(f"{bold('Summary:')} {green(str(total_ok))} OK  {yellow(str(total_warn))} WARN  {red(str(total_fail))} FAIL")

    if total_fail > 0:
        print(f"{red('[FAIL] Asset validation FAILED — fix placeholder issues above')}")
        sys.exit(1)
    elif total_warn > 0:
        print(f"{yellow('[PASS] Asset validation PASSED with warnings — real assets can be added later')}")
        sys.exit(0)
    else:
        print(f"{green('[PASS] Asset validation PASSED — all placeholders present')}")
        sys.exit(0)


if __name__ == "__main__":
    main()
