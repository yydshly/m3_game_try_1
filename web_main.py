"""
web_main.py — Phase 5 Web 入口

启动方式:
    python web_main.py
    配置见 config/server.toml

FastAPI + uvicorn 自动 reload,
静态文件由 FastAPI 直接服务(不需要 nginx)。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根在 path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import uvicorn
from game.web_api import app
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from game.server_config import load_server_config

# 挂载静态文件
_STATIC = _ROOT / "static"
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

# 根路径返回 index.html（对话版）
@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = _STATIC / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h1>孤岛晚宴</h1><p>static/index.html not found</p>"

# /map 路径返回 map.html（地图版）
@app.get("/map", response_class=HTMLResponse)
async def map_page():
    map_path = _STATIC / "map.html"
    if map_path.exists():
        return map_path.read_text(encoding="utf-8")
    return "<h1>孤岛晚宴</h1><p>static/map.html not found</p>"


if __name__ == "__main__":
    cfg = load_server_config()
    print("=" * 50)
    print("  《孤岛晚宴》Web 版")
    print(f"  对话版: {cfg.browser_url}")
    print(f"  地图版: {cfg.browser_url}/map")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    uvicorn.run(
        "web_main:app",
        host=cfg.host,
        port=cfg.port,
        reload=False,
    )
