"""
game/web_api.py — Phase 5 FastAPI 后端

API 设计:
    POST /api/session           新建游戏会话,返回 session_id
    GET  /api/state/{session_id}  获取当前世界状态
    POST /api/command           发送命令,返回 JSON 结果
    GET  /api/stream/{session_id} SSE 流式事件

SSE 事件类型:
    narrator   旁白描写(流式)
    npc_reply NPC 回复(流式)
    system    系统消息(如阶段推进、指认结果)
    game_over 游戏结束
    error     错误
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from game.agents import DirectorAgent, NPCDialogueAgent, NarratorAgent
from game.actions import PlayerAction, available_actions, dispatch
from game.rules import (
    MAX_CLOCK,
    advance_clock,
    advance_phase,
    all_npc_locations,
    can_investigate,
    check_phase_transition,
    clock_name,
    investigate,
    move_to as rule_move_to,
    on_clock_advance,
    _linwan_evidence_exposed,
)
from game.scenario_data import build_initial_world
from game.state import PHASE_CONFRONTATION, WorldState

# ============================================================
# App & CORS
# ============================================================

app = FastAPI(title="孤岛晚宴 API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# 会话管理
# ============================================================

@dataclass
class GameSession:
    world: WorldState
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    ended: bool = False


_sessions: dict[str, GameSession] = {}


def get_session(session_id: str) -> GameSession:
    if session_id not in _sessions:
        raise HTTPException(404, "会话不存在")
    return _sessions[session_id]


# ============================================================
# SSE 广播
# ============================================================

@dataclass
class SSEBroadcaster:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)

    async def put(self, event_type: str, data: str | dict) -> None:
        if isinstance(data, dict):
            data_str = json.dumps(data, ensure_ascii=False)
        else:
            data_str = data
        await self.queue.put(f"event: {event_type}\ndata: {data_str}\n\n")

    async def stream(self) -> AsyncGenerator[bytes, None]:
        while True:
            msg = await self.queue.get()
            yield msg.encode("utf-8")


# 每 session 一个广播器
_session_broadcasters: dict[str, SSEBroadcaster] = {}


def _broadcaster(session_id: str) -> SSEBroadcaster:
    if session_id not in _session_broadcasters:
        _session_broadcasters[session_id] = SSEBroadcaster()
    return _session_broadcasters[session_id]


# ============================================================
# 请求/响应模型
# ============================================================

class NewSessionResponse(BaseModel):
    session_id: str
    state: dict


class CommandRequest(BaseModel):
    session_id: str
    command: str  # 原始命令文本,同 CLI


class ActionRequest(BaseModel):
    """结构化动作请求"""
    session_id: str
    type: str
    target: str | None = None
    text: str | None = None


class CommandResponse(BaseModel):
    ok: bool
    message: str
    state: dict | None = None


# ============================================================
# 辅助: 世界状态 → dict
# ============================================================

def _world_to_dict(world: WorldState) -> dict[str, Any]:
    return {
        "phase": world.phase,
        "clock": world.clock,
        "clock_name": clock_name(world.clock),
        "player_location": world.player.location,
        "inventory": world.player.inventory,
        "npc_locations": all_npc_locations(world),
        "talked_npcs": list(world.player.revealed_to.keys()),
        "public_events": [e.description for e in world.public_events[-5:]],
        "turn_count": world.turn_count,
        "game_over": world.phase == "ending",
        "available_actions": [
            {"type": a.type, "target": a.target, "label": a.label, "enabled": a.enabled, "hint": a.hint}
            for a in available_actions(world)
        ],
    }


# ============================================================
# API 端点
# ============================================================

@app.post("/api/session", response_model=NewSessionResponse)
async def new_session():
    """新建游戏会话。"""
    world = build_initial_world()
    session = GameSession(world=world)
    _sessions[session.id] = session
    _session_broadcasters[session.id] = SSEBroadcaster()
    b = _broadcaster(session.id)
    await b.put("system", {"type": "start", "text": "游戏开始，你是私人侦探。暴风雨困住了所有人，天亮前找出真凶。"})
    return NewSessionResponse(
        session_id=session.id,
        state=_world_to_dict(world),
    )


@app.get("/api/state/{session_id}")
async def get_state(session_id: str):
    """获取当前游戏状态。"""
    session = get_session(session_id)
    return _world_to_dict(session.world)


@app.post("/api/action")
async def post_action(req: ActionRequest):
    """
    结构化动作端点。
    构造 PlayerAction → dispatch() → 推送 events → 返回最新状态(含 available_actions)。
    """
    session = get_session(req.session_id)
    if session.ended:
        return JSONResponse(ok=False, content={"error": "游戏已结束，请新建会话"})

    world = session.world
    b = _broadcaster(req.session_id)

    action = PlayerAction(type=req.type, target=req.target, text=req.text)
    result = dispatch(world, action)

    if not result.ok:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": result.error, "state": _world_to_dict(world)},
        )

    # 注意：events 直接随 HTTP 响应返回，由前端渲染（单一渲染路径）。
    # 不再重复推送到 SSE，否则前端会出现 system 类事件双重渲染。
    return {"ok": True, "events": result.events, "state": _world_to_dict(world)}


@app.get("/api/actions/{session_id}")
async def get_available(session_id: str):
    """返回当前可用动作列表。"""
    session = get_session(session_id)
    return {"actions": available_actions(session.world)}
@app.post("/api/command")
async def send_command(req: CommandRequest):
    """
    将中文命令解析为 PlayerAction，统一走 dispatch()。
    不再单独实现游戏规则。
    """
    session = get_session(req.session_id)
    if session.ended:
        return CommandResponse(ok=False, message="游戏已结束，请新建会话")

    world = session.world
    cmd = req.command.strip()

    # === 解析命令 → PlayerAction ===
    if not cmd:
        return CommandResponse(ok=False, message="空命令")

    # 退出
    if cmd in ("退出", "exit", "quit", "q"):
        session.ended = True
        return CommandResponse(ok=True, message="再见", state=_world_to_dict(world))

    # 存档
    if cmd in ("存档", "save"):
        from game.persistence import save_game
        path = save_game(world)
        return CommandResponse(ok=True, message=f"已存档: {path}", state=_world_to_dict(world))

    # 读档（直接替换 session.world，不走 dispatch）
    if cmd in ("读档", "load"):
        try:
            from game.persistence import load_game
            session.world = load_game()
            return CommandResponse(ok=True, message="读档成功", state=_world_to_dict(session.world))
        except FileNotFoundError:
            return CommandResponse(ok=False, message="没有找到存档")
        except Exception as e:
            return CommandResponse(ok=False, message=f"读档失败: {e}")

    # 解析为 PlayerAction（复用 main.py 的 parse_command 逻辑）
    parsed = _parse_command(cmd)
    if parsed is None:
        return CommandResponse(ok=False, message="无法理解命令", state=_world_to_dict(world))

    action_type, args = parsed

    if action_type == "quit":
        session.ended = True
        return CommandResponse(ok=True, message="再见", state=_world_to_dict(world))

    # 构造 PlayerAction 并走统一 dispatch
    if action_type == "talk":
        npc_name, message = args
        action = PlayerAction(type="talk", target=npc_name, text=message)
    elif action_type == "accuse":
        action = PlayerAction(type="accuse", target=args[0])
    elif action_type in ("move", "investigate", "advance", "status"):
        action = PlayerAction(type=action_type)
    else:
        return CommandResponse(ok=False, message=f"命令 '{cmd}' 暂不支持", state=_world_to_dict(world))

    result = dispatch(world, action)

    if not result.ok:
        return CommandResponse(ok=False, message=result.error, state=_world_to_dict(world))

    # events 通过 SSE 推送（前端已有 handler）
    b = _broadcaster(req.session_id)
    for ev in result.events:
        await b.put(ev.get("kind", "system"), ev)

    return CommandResponse(ok=True, message="", state=_world_to_dict(world))


def _parse_command(cmd: str):
    """
    将中文命令解析为 (action_type, args)。
    逻辑与 main.py parse_command 保持一致。
    """
    stripped = cmd.strip()
    if not stripped:
        return None

    # 跟 NPC 对话
    if stripped.startswith("跟"):
        if "说:" not in stripped:
            return None
        parts = stripped.split()
        try:
            name = parts[1]
            msg = stripped.split("说:", 1)[1].strip()
            return ("talk", [name, msg])
        except IndexError:
            return None

    # 移动
    if stripped.startswith("移动到"):
        loc = stripped[3:].strip()
        return ("move", [loc])

    # 调查
    if stripped in ("调查", "搜查", "搜"):
        return ("investigate", [])

    # 推进时段
    if stripped in ("推进时段", "推进时间", "下个时段", "时间推进"):
        return ("advance", [])

    # 状态
    if stripped in ("查看状态", "状态", "s", "查看"):
        return ("status", [])

    # 指认
    if stripped.startswith("指认"):
        target = stripped[2:].strip()
        if target:
            return ("accuse", [target])
        return None

    return None


def _stream_text(text: str) -> list[str]:
    """将文本拆分成逐句/逐段的流式片段。"""
    import re
    sentences = re.split(r"(?<=[。！？])", text)
    chunks, buffer = [], ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        buffer += s
        if len(buffer) >= 20 or len(chunks) == len(sentences) - 1:
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


# ============================================================
# SSE 流
# ============================================================

@app.get("/api/stream/{session_id}")
async def sse_stream(session_id: str):
    """SSE 流，接收该 session 的所有实时事件。"""
    session = get_session(session_id)
    b = _broadcaster(session_id)

    async def event_generator():
        # 先发一个 heartbeat 确认连接
        yield f"event: connected\ndata: {json.dumps({'session_id': session_id})}\n\n".encode()
        while True:
            try:
                msg = await asyncio.wait_for(b.queue.get(), timeout=60)
                yield msg.encode("utf-8")
            except asyncio.TimeoutError:
                # 60s 无消息，发送心跳
                yield b"event: heartbeat\ndata: {}\n\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_generator(), media_type="text/event-stream")
