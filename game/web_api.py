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
    import game.rules as rules

    # -- npcs: per-NPC structured data for UI
    npc_locations = all_npc_locations(world)
    talked_set = set(world.player.revealed_to.keys())
    npcs = []
    for name, npc in world.npcs.items():
        loc = npc_locations.get(name, "未知")
        suspicion = getattr(npc, "suspicion_of_player", 0)
        npcs.append({
            "name": name,
            "public_role": npc.public_role,
            "location": loc,
            "alive": npc.alive,
            "talked": name in talked_set,
            "present": loc == world.player.location,
            "suspicion_of_player": suspicion,
        })

    # -- current_location
    loc_name = world.player.location
    loc_meta = rules.LOCATION_THEMES.get(loc_name, {"theme": "room", "mood": "", "color": "#5a5a6e"})
    present_npcs = [n for n, loc in npc_locations.items() if loc == loc_name]
    current_location = {
        "name": loc_name,
        "description": rules.LOCATION_DESCRIPTIONS.get(loc_name, f"{loc_name}，昏暗不明。"),
        "theme": loc_meta["theme"],
        "mood": loc_meta["mood"],
        "color": loc_meta["color"],
        "present_npcs": present_npcs,
    }

    # -- evidence_details
    evidence_details = []
    for ev_name in world.player.inventory:
        meta = rules.EVIDENCE_METADATA.get(ev_name, {"source": "未知", "points_to": "?", "level": "?", "icon": "🔍"})
        evidence_details.append({
            "name": ev_name,
            "source": meta["source"],
            "points_to": meta["points_to"],
            "level": meta["level"],
            "icon": meta["icon"],
        })

    # -- progress
    progress = {
        "evidence_count": len(world.player.inventory),
        "talked_count": len(talked_set),
        "npc_count": len(world.npcs),
        "clock": world.clock,
        "max_clock": rules.MAX_CLOCK,
        "phase": world.phase,
        "event_count": len(world.public_events),
    }

    return {
        "phase": world.phase,
        "clock": world.clock,
        "clock_name": clock_name(world.clock),
        "player_location": world.player.location,
        "inventory": world.player.inventory,
        "npc_locations": npc_locations,
        "talked_npcs": list(talked_set),
        "public_events": [e.description for e in world.public_events[-8:]],
        "turn_count": world.turn_count,
        "game_over": world.phase == "ending",
        "available_actions": [
            {"type": a.type, "target": a.target, "label": a.label, "enabled": a.enabled, "hint": a.hint}
            for a in available_actions(world)
        ],
        # new UI-friendly fields
        "npcs": npcs,
        "current_location": current_location,
        "evidence_details": evidence_details,
        "progress": progress,
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
# 侦探助手引导 API
# ============================================================

# 推荐问题映射（不使用大模型）
GUIDE_QUESTIONS: dict[str, str] = {
    "陈伯": "你昨晚在哪？",
    "林婉": "你和周老爷是什么关系？",
    "王总": "你昨晚去了哪里？",
    "苏苏": "昨晚你听到了什么？",
    "阿福": "你昨晚看到了什么？",
    "小张": "你昨晚巡逻了吗？",
}


def _guide_talk_or_move(
    world: WorldState,
    npc_name: str,
    question: str,
    reason_when_here: str,
    reason_when_away: str,
) -> dict[str, Any]:
    """
    Return a talk action if npc_name is at player's location, otherwise a move action.
    All guide recommendations for talk must go through this helper to stay legal.
    """
    import game.rules as rules

    npc_loc = rules.npc_location_at(npc_name, world.clock)
    player_loc = world.player.location

    if npc_loc == player_loc:
        return {
            "title": "建议下一步",
            "reason": reason_when_here,
            "action": {"type": "talk", "target": npc_name, "text": question},
            "label": f"盘问 {npc_name}",
            "confidence": "high",
        }

    return {
        "title": "建议下一步",
        "reason": f"{reason_when_away} {npc_name} 当前在 {npc_loc}，请先前往那里。",
        "action": {"type": "move", "target": npc_loc, "text": None},
        "label": f"前往 {npc_loc}",
        "confidence": "high",
    }


def _build_guide(world: WorldState) -> dict[str, Any]:
    """
    Deterministic guide — does NOT call M3, does NOT modify world.
    Returns a guide dict with title, reason, action, label, confidence.
    """
    import game.rules as rules

    phase = world.phase
    clock = world.clock
    player_loc = world.player.location
    talked = set(world.player.revealed_to.keys())
    evidence_count = len(world.player.inventory)
    afu_talks = len(world.player.revealed_to.get("阿福", []))

    # Helper: find alive NPCs at a given location using shared rules
    def npcs_at(loc: str):
        return [n for n in world.npcs if rules.npc_location_at(n, clock) == loc and world.npcs[n].alive]

    # Helper: find a location with un-talked NPCs
    def location_with_untalked_npcs():
        for loc in ("大厅", "书房", "厨房", "餐厅", "保安室", "走廊",
                    "陈伯房间", "林婉房间", "苏苏房间", "王总房间", "自己房间"):
            present = npcs_at(loc)
            if present and any(n not in talked for n in present):
                return loc, present
        return None, []

    # ── Ending ────────────────────────────────────────
    if phase == rules.PHASE_ENDING:
        return {
            "title": "案件结束",
            "reason": "当前游戏已结束，可以重新开始。",
            "action": None,
            "label": "",
            "confidence": "high",
        }

    # ── Dinner phase ──────────────────────────────────
    if phase == rules.PHASE_DINNER:
        # Check NPCs at current location
        present = npcs_at(player_loc)
        untalked_present = [n for n in present if n not in talked]

        if untalked_present:
            target = untalked_present[0]
            question = GUIDE_QUESTIONS.get(target, "你知道什么线索？")
            return _guide_talk_or_move(
                world, target, question,
                f"晚宴阶段需要先盘问 {rules.DINNER_MIN_TALKS} 名人物。当前 {player_loc} 有 {target}，建议先盘问。",
                f"需要盘问 {target} 来推进晚宴阶段，但该NPC不在当前地点。",
            )

        talked_count = len(talked)
        if talked_count >= rules.DINNER_MIN_TALKS:
            return {
                "title": "建议下一步",
                "reason": f"已盘问 {talked_count} 名人物，满足进入调查阶段的条件。使用「推进时段」进入调查。",
                "action": {"type": "advance", "target": None, "text": None},
                "label": "推进时段",
                "confidence": "high",
            }

        # Try to find another location with un-talked NPCs
        loc, _ = location_with_untalked_npcs()
        if loc:
            return {
                "title": "建议下一步",
                "reason": f"当前 {player_loc} 没有可盘问的对象。建议前往 {loc}，那里有未盘问的嫌疑人。",
                "action": {"type": "move", "target": loc, "text": None},
                "label": f"前往 {loc}",
                "confidence": "medium",
            }

        return {
            "title": "建议下一步",
            "reason": "晚宴阶段需要先盘问 5 名人物，建议移动到有人的房间继续。",
            "action": {"type": "move", "target": "大厅", "text": None},
            "label": "前往大厅",
            "confidence": "low",
        }

    # ── Investigation phase ────────────────────────────
    if phase == rules.PHASE_INVESTIGATION:
        if evidence_count >= rules.INVESTIGATION_MIN_EVIDENCE:
            return {
                "title": "建议下一步",
                "reason": f"已收集 {evidence_count} 条证据，满足对峙条件。使用「推进时段」进入对峙阶段。",
                "action": {"type": "advance", "target": None, "text": None},
                "label": "推进时段",
                "confidence": "high",
            }

        # 1. 新遗嘱草稿：书房固定物品，直接调查书房即可获得
        if "新遗嘱草稿" not in world.player.inventory:
            if player_loc != "书房":
                return {
                    "title": "建议下一步",
                    "reason": "书房里有新遗嘱草稿，是关键证据。建议直接前往书房调查。",
                    "action": {"type": "move", "target": "书房", "text": None},
                    "label": "前往书房",
                    "confidence": "high",
                }
            return {
                "title": "建议下一步",
                "reason": "你现在在书房，可以调查获取新遗嘱草稿。",
                "action": {"type": "investigate", "target": None, "text": None},
                "label": "调查书房",
                "confidence": "high",
            }

        # 2. 异常的茶杯残留：需先和陈伯说过话，再调查书房
        if "异常的茶杯残留" not in world.player.inventory:
            if "陈伯" not in talked:
                return _guide_talk_or_move(
                    world, "陈伯", GUIDE_QUESTIONS.get("陈伯", "你昨晚在哪？"),
                    f"书房里的茶杯残留需要先和陈伯交谈才能发现。当前 {player_loc} 有陈伯，建议先盘问。",
                    "需要先盘问陈伯来解锁茶杯残留线索。",
                )
            if player_loc != "书房":
                return {
                    "title": "建议下一步",
                    "reason": "已和陈伯谈过，现在可以前往书房调查获取茶杯残留证据。",
                    "action": {"type": "move", "target": "书房", "text": None},
                    "label": "前往书房",
                    "confidence": "high",
                }
            return {
                "title": "建议下一步",
                "reason": "你现在在书房，可以调查获取茶杯残留证据。",
                "action": {"type": "investigate", "target": None, "text": None},
                "label": "调查书房",
                "confidence": "high",
            }

        # 3. 借据：需先和王总说过话，再调查书房
        if "借据" not in world.player.inventory:
            if "王总" not in talked:
                return _guide_talk_or_move(
                    world, "王总", GUIDE_QUESTIONS.get("王总", "你昨晚去了哪里？"),
                    f"书房的借据需要先和王总交谈才能发现。当前 {player_loc} 有王总，建议先盘问。",
                    "需要先盘问王总来解锁借据线索。",
                )
            if player_loc != "书房":
                return {
                    "title": "建议下一步",
                    "reason": "已和王总谈过，现在可以前往书房调查获取借据。",
                    "action": {"type": "move", "target": "书房", "text": None},
                    "label": "前往书房",
                    "confidence": "high",
                }
            return {
                "title": "建议下一步",
                "reason": "你现在在书房，可以调查获取借据。",
                "action": {"type": "investigate", "target": None, "text": None},
                "label": "调查书房",
                "confidence": "high",
            }

        # 4. 厨师阿福的证词：需和阿福对话至少2次，再调查厨房
        if "厨师阿福的证词" not in world.player.inventory:
            if afu_talks < 2:
                return _guide_talk_or_move(
                    world, "阿福", GUIDE_QUESTIONS.get("阿福", "你昨晚看到了什么？"),
                    f"厨房的证词需要盘问阿福至少2次才能获得（已 {afu_talks} 次）。当前 {player_loc} 有阿福，建议继续盘问。",
                    "需要盘问阿福至少2次来解锁证词。",
                )
            if player_loc != "厨房":
                return {
                    "title": "建议下一步",
                    "reason": "已盘问阿福多次，可以前往厨房调查获取证词。",
                    "action": {"type": "move", "target": "厨房", "text": None},
                    "label": "前往厨房",
                    "confidence": "high",
                }
            return {
                "title": "建议下一步",
                "reason": "你现在在厨房，可以调查获取厨师阿福的证词。",
                "action": {"type": "investigate", "target": None, "text": None},
                "label": "调查厨房",
                "confidence": "high",
            }

        # 5. 林婉的病历笔记：调查林婉房间
        if "林婉的病历笔记" not in world.player.inventory:
            if player_loc != "林婉房间":
                return {
                    "title": "建议下一步",
                    "reason": "林婉房间有她的病历笔记，是重要证据。建议前往调查。",
                    "action": {"type": "move", "target": "林婉房间", "text": None},
                    "label": "前往林婉房间",
                    "confidence": "high",
                }
            return {
                "title": "建议下一步",
                "reason": "你现在在林婉房间，可以调查获取病历笔记。",
                "action": {"type": "investigate", "target": None, "text": None},
                "label": "调查林婉房间",
                "confidence": "high",
            }

        # All evidence found but somehow count is low — shouldn't normally happen
        return {
            "title": "建议下一步",
            "reason": "证据收集完成，可以使用「推进时段」进入对峙阶段。",
            "action": {"type": "advance", "target": None, "text": None},
            "label": "推进时段",
            "confidence": "high",
        }

    # ── Confrontation phase ────────────────────────────
    if phase == rules.PHASE_CONFRONTATION:
        return {
            "title": "建议下一步",
            "reason": "对峙阶段：结合已有证据，选择你认为最可疑的人完成指认。林婉因医疗知情、遗嘱动机和案发机会最可疑。",
            "action": {"type": "accuse", "target": "林婉", "text": None},
            "label": "指认林婉",
            "confidence": "high",
        }

    # Fallback
    return {
        "title": "建议下一步",
        "reason": "继续当前阶段，推进调查。",
        "action": None,
        "label": "",
        "confidence": "low",
    }


@app.get("/api/guide/{session_id}")
async def get_guide(session_id: str):
    """返回当前状态的侦探引导建议（确定性规则，不调用大模型）。"""
    session = get_session(session_id)
    guide = _build_guide(session.world)
    return guide


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
