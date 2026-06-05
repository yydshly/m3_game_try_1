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
    """处理一条命令，返回结果（同步部分）。游戏结束后续通过 SSE 推送。"""
    session = get_session(req.session_id)
    if session.ended:
        return CommandResponse(ok=False, message="游戏已结束，请新建会话")

    world = session.world
    cmd = req.command.strip()
    b = _broadcaster(req.session_id)
    result_msg = ""

    # === 解析命令 ===
    if not cmd:
        return CommandResponse(ok=False, message="空命令")

    # 退出
    if cmd in ("退出", "exit", "quit", "q"):
        session.ended = True
        return CommandResponse(ok=True, message="再见", state=_world_to_dict(world))

    # 状态
    if cmd in ("查看状态", "状态", "s", "查看"):
        return CommandResponse(ok=True, message="", state=_world_to_dict(world))

    # 存档
    if cmd in ("存档", "save"):
        from game.persistence import save_game
        path = save_game(world)
        return CommandResponse(ok=True, message=f"已存档: {path}", state=_world_to_dict(world))

    # 读档
    if cmd in ("读档", "load"):
        try:
            from game.persistence import load_game
            world = load_game()
            session.world = world
            return CommandResponse(ok=True, message="读档成功", state=_world_to_dict(world))
        except Exception as e:
            return CommandResponse(ok=False, message=f"读档失败: {e}")

    # === 需要 world_state 的命令 ===
    result_msg = await _handle_game_command(world, cmd, b)

    return CommandResponse(ok=True, message=result_msg, state=_world_to_dict(world))


async def _handle_game_command(world: WorldState, cmd: str, b: SSEBroadcaster) -> str:
    """处理游戏命令，可能产生多条 SSE 事件。"""
    result = ""

    # --- 推进时段 ---
    if cmd in ("推进时段", "推进时间", "下个时段", "时间推进"):
        old_clock = world.clock
        advance_clock(world)
        advance_phase(world)
        result = f"⏰ {clock_name(old_clock)} → {clock_name(world.clock)}"
        await b.put("system", {"type": "clock", "text": result})

        # Narrator 流式播报
        narration = NarratorAgent.narrate(world)
        await b.put("narrator", _stream_text(narration))

        # NPC 时段行为
        npc_events = on_clock_advance(world)
        for ev in npc_events:
            await b.put("system", {"type": "npc_action", "text": ev})
            result += f"\n{ev}"

        # 林婉 DecisionAgent
        if _linwan_evidence_exposed(world):
            linwan = world.npcs.get("林婉")
            if linwan and linwan.alive:
                decision = DirectorAgent.decide(linwan, world)
                action = decision.get("action", "wait")
                if action != "wait":
                    reason = decision.get("reason", "")
                    text = f"【林婉的决策】{action}（原因: {reason}）"
                    await b.put("system", {"type": "npc_decision", "text": text})
                    result += f"\n{text}"

        # 检查阶段推进
        pending = check_phase_transition(world)
        if pending and pending != world.phase:
            text = f"【系统】已满足 {pending} 阶段进入条件，使用「推进时段」即可进入。"
            await b.put("system", {"type": "phase_hint", "text": text})

        # 时段到顶，自动结局
        if world.clock >= MAX_CLOCK and world.phase != "ending":
            advance_phase(world)
            await b.put("system", {"type": "boat_arrived", "text": "渡船已经靠岸！时间耗尽。"})
            judgment = DirectorAgent.judge(world, player_accusation=None)
            await b.put("game_over", judgment)
            world.phase = "ending"
            await b.put("system", {"type": "game_over", "text": f"【结局】{judgment['verdict']}"})
        return result

    # --- 移动 ---
    if cmd.startswith("移动到"):
        loc = cmd[3:].strip()
        desc = rule_move_to(world, loc)
        await b.put("system", {"type": "location", "text": desc})
        return desc

    # --- 调查 ---
    if cmd in ("调查", "搜查", "搜"):
        loc = world.player.location
        if not can_investigate(loc):
            result = f"在 {loc} 没有可调查的物品。"
        else:
            gained = investigate(world, loc)
            if gained:
                result = f"获得物品: {', '.join(gained)}"
            else:
                result = "没有获得新物品。（提示:有些证据需要先和特定NPC说过话才能获得）"
        await b.put("system", {"type": "investigate", "text": result})
        return result

    # --- 对话 ---
    if cmd.startswith("跟"):
        if "说:" not in cmd:
            return "命令格式: 跟 <NPC名> 说: <话>"
        parts = cmd.split()
        try:
            npc_name = parts[1]
            message = cmd.split("说:", 1)[1].strip()
        except IndexError:
            return "命令格式: 跟 <NPC名> 说: <话>"

        if npc_name not in world.npcs:
            return f"'{npc_name}' 不存在。可用NPC: {', '.join(world.npcs.keys())}"

        # 记录对话
        if npc_name not in world.player.revealed_to:
            world.player.revealed_to[npc_name] = []
        world.player.revealed_to[npc_name].append(message)

        # 阶段推进检测（提前提示）
        pending = check_phase_transition(world)
        if pending and pending != world.phase:
            hint = f"【系统】已满足 {pending} 阶段进入条件。"
            await b.put("system", {"type": "phase_hint", "text": hint})

        # 流式 NPC 回复
        npc = world.npcs[npc_name]
        # 先发 typing 指示，让前端立刻显示"..."动画
        await b.put("npc_typing", {"npc": npc_name})
        reply = NPCDialogueAgent.respond(npc=npc, world=world, player_message=message)
        await b.put("npc_reply", {"npc": npc_name, "text": _stream_text(reply)})
        world.turn_count += 1

        # 林婉警觉
        if npc_name == "林婉" and _linwan_evidence_exposed(world):
            await b.put("system", {"type": "linwan_alert", "text": "林婉似乎有所察觉..."})

        return f"【{npc_name}】{reply}"

    # --- 指认 ---
    if cmd.startswith("指认"):
        accused = cmd[2:].strip()
        if world.phase != PHASE_CONFRONTATION:
            pending = check_phase_transition(world)
            if pending:
                return f"需要先进入 {pending} 阶段才能指认。"
            return "还没到对峙阶段，继续调查吧。"

        if accused not in world.npcs:
            return f"'{accused}' 不是有效嫌疑人。"

        result = f"指认: {accused}"
        await b.put("system", {"type": "accusation", "text": result})
        judgment = DirectorAgent.judge(world, player_accusation=accused)
        await b.put("game_over", judgment)
        world.phase = "ending"
        result += f"\n【结局】{judgment['verdict']}\n{judgment['summary']}"
        await b.put("system", {"type": "game_over", "text": result})
        return result

    return "无法理解命令"


def _stream_text(text: str) -> list[str]:
    """将文本拆分成逐句/逐段的流式片段，模拟打字效果。"""
    # 简单按句子切分
    import re
    sentences = re.split(r"(?<=[。！？])", text)
    chunks = []
    buffer = ""
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
