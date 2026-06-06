#!/usr/bin/env python3
"""
Stop local dev server occupying a TCP port.

Usage:
  python scripts/stop_dev_server.py
  python scripts/stop_dev_server.py --port 8000
  python scripts/stop_dev_server.py --port 8000 --dry-run

Default port is read from config/server.toml.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Set

ROOT = Path(__file__).resolve().parents[1]


def _load_default_port() -> int:
    try:
        sys.path.insert(0, str(ROOT))
        from game.server_config import load_server_config
        return load_server_config().port
    except Exception:
        return 8000


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, shell=False)


def _find_pids_windows(port: int) -> Set[int]:
    pids: Set[int] = set()
    proc = _run(["netstat", "-ano", "-p", "tcp"])
    if proc.returncode != 0:
        return pids

    # Example line:
    # TCP    0.0.0.0:8000    0.0.0.0:0    LISTENING    12345
    pattern = re.compile(rf"^\s*TCP\s+\S+:{port}\s+\S+\s+LISTENING\s+(\d+)\s*$", re.I)
    for line in proc.stdout.splitlines():
        m = pattern.match(line)
        if m:
            pids.add(int(m.group(1)))
    return pids


def _find_pids_posix(port: int) -> Set[int]:
    pids: Set[int] = set()

    # Try lsof first (works on macOS and most Linux)
    lsof_proc = _run(["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"])
    if lsof_proc.returncode == 0:
        for line in lsof_proc.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))

    if pids:
        return pids

    # Fallback to ss on Linux
    ss_proc = _run(["ss", "-ltnp"])
    if ss_proc.returncode == 0:
        for line in ss_proc.stdout.splitlines():
            if f":{port}" not in line:
                continue
            for pid in re.findall(r"pid=(\d+)", line):
                pids.add(int(pid))

    return pids


def find_pids(port: int) -> Set[int]:
    if platform.system().lower().startswith("win"):
        return _find_pids_windows(port)
    return _find_pids_posix(port)


def stop_pid(pid: int, dry_run: bool) -> None:
    if dry_run:
        print(f"[DRY-RUN] would stop PID {pid}")
        return

    if platform.system().lower().startswith("win"):
        print(f"[STOP] taskkill /PID {pid} /T /F")
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        print(f"[STOP] SIGTERM PID {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> int:
    default_port = _load_default_port()
    parser = argparse.ArgumentParser(description="Stop the local dev server on a given TCP port.")
    parser.add_argument(
        "--port", type=int, default=None,
        help=f"TCP port to free (default: {default_port} from config/server.toml)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Only print what would be stopped, don't actually stop it"
    )
    args = parser.parse_args()

    port = args.port if args.port is not None else default_port

    pids = find_pids(port)
    if not pids:
        print(f"[OK] no listening process found on port {port}")
        return 0

    print(f"[INFO] found {len(pids)} process(es) on port {port}: {sorted(pids)}")
    for pid in sorted(pids):
        stop_pid(pid, args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
