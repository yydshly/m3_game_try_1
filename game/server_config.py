"""
game/server_config.py — 统一读取 Web 服务 host / port 配置

配置来源（优先级从低到高）：
    1. 内置默认值
    2. config/server.toml
    3. 环境变量

配置字段：
    host       uvicorn 监听地址
    port       uvicorn 监听端口
    open_host  浏览器打开使用的 host（用于 browser_url）
    auto_open  启动脚本是否默认自动打开浏览器
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "server.toml"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    open_host: str = "localhost"
    auto_open: bool = True

    @property
    def browser_url(self) -> str:
        return f"http://{self.open_host}:{self.port}"

    @property
    def bind_url(self) -> str:
        return f"http://{self.host}:{self.port}"


def load_server_config(config_path: str | Path | None = None) -> ServerConfig:
    """
    读取服务配置。

    参数:
        config_path: 可选，指定配置文件路径。默认读取 config/server.toml。
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    data: dict = {}
    if path.exists():
        try:
            import tomllib
            with path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            # tomllib 不存在时忽略（Python < 3.11）
            pass

    server: dict = data.get("server", {}) if isinstance(data, dict) else {}

    host = str(server.get("host", "127.0.0.1"))
    port = int(server.get("port", 8000))
    open_host = str(server.get("open_host", "localhost"))
    auto_open = bool(server.get("auto_open", True))

    # 环境变量覆盖配置文件
    host = os.getenv("M3_GAME_HOST", host)
    port = int(os.getenv("M3_GAME_PORT", str(port)))
    open_host = os.getenv("M3_GAME_OPEN_HOST", open_host)
    auto_open = _env_bool("M3_GAME_AUTO_OPEN", auto_open)

    return ServerConfig(
        host=host,
        port=port,
        open_host=open_host,
        auto_open=auto_open,
    )
