#!/usr/bin/env python3
"""
Start the local web dev server for 孤岛晚宴.

Usage:
  python scripts/start_dev_server.py
  python scripts/start_dev_server.py --port 8001
  python scripts/start_dev_server.py --host 0.0.0.0 --port 8001
  python scripts/start_dev_server.py --stop-existing
  python scripts/start_dev_server.py --no-open
  python scripts/start_dev_server.py --reload

Configuration (config/server.toml):
  host, port, open_host, auto_open
  CLI args > environment variables > config file > defaults
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _import_stop_helpers():
    sys.path.insert(0, str(ROOT))
    from scripts.stop_dev_server import find_pids, stop_pid
    return find_pids, stop_pid


def _load_config():
    sys.path.insert(0, str(ROOT))
    from game.server_config import ServerConfig, load_server_config
    return ServerConfig, load_server_config


def _check_requirements() -> None:
    missing = []
    try:
        import fastapi  # noqa: F401
    except Exception:
        missing.append("fastapi")
    try:
        import uvicorn  # noqa: F401
    except Exception:
        missing.append("uvicorn")

    if missing:
        print("[ERROR] 缺少依赖:", ", ".join(missing))
        print("请先执行:")
        print("  pip install -r requirements.txt")
        sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="启动孤岛晚宴本地 Web 服务")
    parser.add_argument(
        "--host",
        default=None,
        help="监听地址（默认从 config/server.toml 读取）"
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="监听端口（默认从 config/server.toml 读取）"
    )
    parser.add_argument(
        "--stop-existing", action="store_true",
        help="端口被占用时先停止旧进程再启动"
    )
    parser.add_argument(
        "--no-open", action="store_true",
        help="不自动打开浏览器"
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="启用 uvicorn reload 模式（代码变更自动重载）"
    )
    args = parser.parse_args()

    os.chdir(ROOT)
    _check_requirements()

    ServerConfig, load_server_config = _load_config()
    base_cfg = load_server_config()

    # CLI args override config file
    host = args.host if args.host is not None else base_cfg.host
    port = args.port if args.port is not None else base_cfg.port
    auto_open = base_cfg.auto_open and not args.no_open
    browser_url = f"http://{base_cfg.open_host}:{port}"

    find_pids, stop_pid = _import_stop_helpers()
    pids = find_pids(port)

    if pids:
        if args.stop_existing:
            print(f"[INFO] 端口 {port} 被 PID: {sorted(pids)} 占用")
            print("[INFO] 正在停止旧进程...")
            for pid in sorted(pids):
                stop_pid(pid, dry_run=False)
            time.sleep(1.0)
        else:
            print(f"[ERROR] 端口 {port} 已被占用（PID: {sorted(pids)}）")
            print("可选择：")
            print(f"  python scripts/stop_dev_server.py --port {port}")
            print(f"  python scripts/start_dev_server.py --port {port} --stop-existing")
            print(f"  python scripts/start_dev_server.py --port 8001")
            return 1

    print("=" * 60)
    print("  《孤岛晚宴》Web 版启动中")
    print(f"  主入口: {browser_url}")
    print(f"  地图实验页: {browser_url}/map")
    print("  停止服务: Ctrl+C")
    print("=" * 60)

    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "web_main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if args.reload:
        cmd.append("--reload")

    if auto_open:

        def open_later():
            import threading

            def _open():
                time.sleep(1.2)
                webbrowser.open(browser_url)

            threading.Thread(target=_open, daemon=True).start()

        open_later()

    try:
        return subprocess.call(cmd, cwd=str(ROOT))
    except KeyboardInterrupt:
        print("\n[OK] 服务已停止")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
