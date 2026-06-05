"""
game/persistence.py — 存档与读档

将 WorldState 序列化为 JSON 文件存储,支持中断后继续游戏。
Phase 2 仅实现基础版本:完整序列化和反序列化。

设计要点(见 docs/ARCHITECTURE.md 第 4 节):
- WorldState 是"单一真相源",存档=磁盘上的 JSON 副本。
- 反序列化后得到一个新的 WorldState 对象,原对象可丢弃。
- Phase 2 暂不处理并发写入或版本迁移。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from game.state import (
    Event,
    NPCState,
    PlayerState,
    WorldState,
)

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
SAVE_DIR: Path = _PROJECT_ROOT / "saves"
SAVE_FILE: Path = SAVE_DIR / "save.json"


# ============================================================
# 序列化(WorldState → dict)
# ============================================================

def _event_to_dict(e: Event) -> dict[str, Any]:
    return {
        "clock": e.clock,
        "description": e.description,
        "visible_to": e.visible_to,
    }


def _player_to_dict(p: PlayerState) -> dict[str, Any]:
    return {
        "location": p.location,
        "inventory": list(p.inventory),
        "revealed_to": {k: list(v) for k, v in p.revealed_to.items()},
    }


def _npc_to_dict(n: NPCState) -> dict[str, Any]:
    return {
        "name": n.name,
        "public_role": n.public_role,
        "hidden_goal": n.hidden_goal,
        "secrets": list(n.secrets),
        "personality": n.personality,
        "memory": list(n.memory),
        "relationships": {k: v for k, v in n.relationships.items()},
        "alive": n.alive,
        "suspicion_of_player": n.suspicion_of_player,
    }


def world_to_dict(world: WorldState) -> dict[str, Any]:
    """将 WorldState 转为可 JSON 序列化的字典。"""
    return {
        "scene": world.scene,
        "phase": world.phase,
        "clock": world.clock,
        "turn_count": world.turn_count,
        "player": _player_to_dict(world.player),
        "npcs": {name: _npc_to_dict(npc) for name, npc in world.npcs.items()},
        "public_events": [_event_to_dict(e) for e in world.public_events],
    }


# ============================================================
# 反序列化(dict → WorldState)
# ============================================================

def _dict_to_event(d: dict[str, Any]) -> Event:
    return Event(
        clock=d["clock"],
        description=d["description"],
        visible_to=list(d["visible_to"]),
    )


def _dict_to_player(d: dict[str, Any]) -> PlayerState:
    return PlayerState(
        location=d["location"],
        inventory=list(d.get("inventory", [])),
        revealed_to={k: list(v) for k, v in d.get("revealed_to", {}).items()},
    )


def _dict_to_npc(d: dict[str, Any]) -> NPCState:
    return NPCState(
        name=d["name"],
        public_role=d["public_role"],
        hidden_goal=d["hidden_goal"],
        secrets=list(d["secrets"]),
        personality=d.get("personality", ""),
        memory=list(d.get("memory", [])),
        relationships={k: v for k, v in d.get("relationships", {}).items()},
        alive=d.get("alive", True),
        suspicion_of_player=d.get("suspicion_of_player", 0),
    )


def world_from_dict(d: dict[str, Any]) -> WorldState:
    """从字典反序列化回 WorldState。"""
    return WorldState(
        scene=d["scene"],
        phase=d["phase"],
        clock=d["clock"],
        turn_count=d.get("turn_count", 0),
        player=_dict_to_player(d["player"]),
        npcs={name: _dict_to_npc(nd) for name, nd in d["npcs"].items()},
        public_events=[_dict_to_event(e) for e in d.get("public_events", [])],
    )


# ============================================================
# 文件 I/O
# ============================================================

def save_game(world: WorldState, path: Path | str | None = None) -> Path:
    """
    将 world 保存为 JSON 文件。

    参数:
        world: 要保存的世界状态
        path: 保存路径,默认使用 SAVE_FILE

    返回实际保存的路径。
    """
    if path is None:
        path = SAVE_FILE
    path = Path(path)
    SAVE_DIR.mkdir(parents=True, exist_ok=True)

    data = world_to_dict(world)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return path


def load_game(path: Path | str | None = None) -> WorldState:
    """
    从 JSON 文件加载 WorldState。

    参数:
        path: 存档路径,默认使用 SAVE_FILE

    返回反序列化后的 WorldState。

    Raises:
        FileNotFoundError: 存档不存在
        ValueError: JSON 格式错误
    """
    if path is None:
        path = SAVE_FILE
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"存档不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"存档格式错误,期望 dict,得到 {type(data).__name__}")

    return world_from_dict(data)


def has_save(path: Path | str | None = None) -> bool:
    """检查存档文件是否存在。"""
    if path is None:
        path = SAVE_FILE
    return Path(path).exists()
