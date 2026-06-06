"""game/actions.py — 结构化动作层

职责（仅此三件，不写游戏规则）:
1. 定义玩家动作的结构化协议（ActionType / PlayerAction）。
2. dispatch(): 把一个结构化动作分发到已有的 rules/agents 函数，返回结构化结果。
3. available_actions(): 给定 WorldState，返回玩家此刻可执行的动作列表（前端据此渲染按钮）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# 动作类型（玩家能发起的所有动作，定死）
ACTION_TALK = "talk"            # 和某 NPC 对话      需要 target=NPC名, text=话
ACTION_MOVE = "move"            # 移动到某地点       需要 target=地点名
ACTION_INVESTIGATE = "investigate"  # 在当前地点调查  无需参数
ACTION_ADVANCE = "advance"      # 推进时段          无需参数
ACTION_ACCUSE = "accuse"        # 指认凶手          需要 target=NPC名
ACTION_STATUS = "status"        # 查看状态          无需参数
ACTION_SAVE = "save"
ACTION_LOAD = "load"

LEGAL_ACTION_TYPES: tuple[str, ...] = (
    ACTION_TALK, ACTION_MOVE, ACTION_INVESTIGATE, ACTION_ADVANCE,
    ACTION_ACCUSE, ACTION_STATUS, ACTION_SAVE, ACTION_LOAD,
)


def _investigate_empty_hint(world, loc: str) -> str:
    """Return a location-specific hint when investigate finds nothing new."""
    if loc == "大厅":
        return "你仔细检查了大厅，没有发现新的物证。这里更像是通往各处的集散点，建议前往书房、厨房或有人的房间继续调查。"
    if loc == "书房":
        return "你重新检查了书房，目前没有新的发现。有些线索需要先盘问陈伯或王总后才会显现。"
    if loc == "厨房":
        return "你检查了厨房，暂时没有新的物证。若想获得厨师相关证词，需要多盘问阿福。"
    if loc == "餐厅":
        return "餐厅没有新的物证，但这里能帮助还原昨夜晚宴关系。建议盘问在场人物或前往书房。"
    return f"你调查了{loc}，暂时没有新的发现。建议移动到有人的地点盘问，或查看右侧建议下一步。"


@dataclass
class PlayerAction:
    """前端发来的一个结构化动作。"""
    type: str                       # 见 LEGAL_ACTION_TYPES
    target: str | None = None       # NPC名 或 地点名（视 type 而定）
    text: str | None = None         # 对话内容（仅 talk 用）


@dataclass
class ActionResult:
    """一个动作执行后的结构化结果。前端据此渲染。"""
    ok: bool
    # 产生的"对话/叙事/系统"消息片段，按发生顺序
    events: list[dict[str, Any]] = field(default_factory=list)
    # 错误信息（ok=False 时）
    error: str = ""


@dataclass
class AvailableAction:
    """一个'此刻可执行'的动作（前端渲染成按钮/选项）。"""
    type: str
    target: str | None = None
    label: str = ""                 # 按钮上显示的文字，如 "盘问 陈伯"
    enabled: bool = True            # 是否可点（不满足条件时灰掉）
    hint: str = ""                  # 灰掉时的提示，如 "需先进入对峙阶段"


# ============================================================
# 可用动作生成
# ============================================================

def _build_advance_action(world):
    """返回 (label, enabled, hint) 三元组，按当前阶段和完成度生成。"""
    import game.rules as rules
    from game.state import PHASE_DINNER, PHASE_INVESTIGATION, PHASE_CONFRONTATION

    pending = rules.check_phase_transition(world)

    if world.phase == PHASE_DINNER:
        if pending:
            return ("进入调查阶段", True, "已完成足够盘问，可以进入正式调查")
        talks = rules.count_player_talks(world)
        remain = max(0, rules.DINNER_MIN_TALKS - talks)
        return ("进入调查阶段", False, f"还需盘问 {remain} 名人物才能进入调查")

    if world.phase == PHASE_INVESTIGATION:
        if pending:
            return ("进入对峙阶段", True, "证据已足够，可以进入对峙")
        ev_count = rules.count_player_evidence(world)
        remain = max(0, rules.INVESTIGATION_MIN_EVIDENCE - ev_count)
        return ("进入对峙阶段", False, f"还需获得 {remain} 条证据才能进入对峙")

    if world.phase == PHASE_CONFRONTATION:
        return ("等待渡船", False, "当前应先指认嫌疑人")

    return ("推进时段", False, "当前无法推进")


# 合法地点表（与 main.py 的 VALID_LOCATIONS 统一）
VALID_LOCATIONS: list[str] = [
    "书房", "厨房", "大厅", "保安室",
    "陈伯房间", "苏苏房间", "林婉房间", "王总房间",
    "餐厅", "走廊", "自己房间",
]


def available_actions(world) -> list[AvailableAction]:
    """
    给定 WorldState，返回玩家此刻可执行的动作列表。
    规则（全部查 WorldState + 调用已有 rules 函数，不调 M3）：
    - talk: 与玩家同地点的、alive 的 NPC，每人一个
    - move: 所有合法地点（排除当前所在地）
    - investigate: 当前地点 can_investigate() 为真
    - advance: 按当前阶段条件动态启用；未满足条件时 enabled=False + hint
    - accuse: 仅 phase == confrontation 时，对每个存活 NPC 一个；其余阶段 enabled=False + hint
    """
    from game.rules import can_investigate, npc_location_at
    from game.state import PHASE_CONFRONTATION

    actions: list[AvailableAction] = []
    here = world.player.location

    # 1. 对话：只能和"同地点且存活"的 NPC 说话
    for name, npc in world.npcs.items():
        if npc.alive and npc_location_at(name, world.clock) == here:
            actions.append(AvailableAction(
                type="talk", target=name, label=f"盘问 {name}"))

    # 2. 移动
    for loc in VALID_LOCATIONS:
        if loc != here:
            actions.append(AvailableAction(
                type="move", target=loc, label=f"前往 {loc}"))

    # 3. 调查
    if can_investigate(here):
        actions.append(AvailableAction(
            type="investigate", label=f"调查 {here}"))

    # 4. 推进时段（按阶段条件动态生成 enabled/hint）
    advance_label, advance_enabled, advance_hint = _build_advance_action(world)
    actions.append(AvailableAction(
        type="advance", label=advance_label, enabled=advance_enabled, hint=advance_hint
    ))

    # 5. 指认（仅对峙阶段可用）
    in_confront = world.phase == PHASE_CONFRONTATION
    for name, npc in world.npcs.items():
        if npc.alive:
            actions.append(AvailableAction(
                type="accuse", target=name, label=f"指认 {name}",
                enabled=in_confront,
                hint="" if in_confront else "需先进入对峙阶段"))

    return actions


# ============================================================
# 动作分发
# ============================================================

def dispatch(world, action: PlayerAction) -> ActionResult:
    """
    把一个结构化动作分发到已有的 rules/agents 函数，返回结构化结果。

    复用已有的 investigate / move_to / advance_clock / advance_phase /
    NPCDialogueAgent.respond / NarratorAgent.narrate / DirectorAgent，
    不重写规则。

    events 里每条是 {"kind": "...", "speaker": "...", "text": "..."}，
    kind ∈ {"narrator","npc","system","investigate","clock","game_over"}。
    """
    from game.agents import DirectorAgent, NPCDecisionAgent, NPCDialogueAgent, NarratorAgent
    import game.rules as rules

    if action.type not in LEGAL_ACTION_TYPES:
        return ActionResult(ok=False, error=f"非法动作: {action.type}")

    events: list[dict[str, Any]] = []

    # ---- talk ----
    if action.type == ACTION_TALK:
        npc_name = action.target or ""
        message = action.text or ""

        if not npc_name:
            return ActionResult(ok=False, error="对话需要指定 NPC 名")

        if npc_name not in world.npcs:
            return ActionResult(ok=False, error=f"'{npc_name}' 不存在")

        # 地点校验：NPC 必须在玩家所在地点
        npc_loc = rules.npc_location_at(npc_name, world.clock)
        if npc_loc != world.player.location:
            return ActionResult(ok=False, error=f"{npc_name}不在这里（TA在{npc_loc}）")

        # 记录对话
        if npc_name not in world.player.revealed_to:
            world.player.revealed_to[npc_name] = []
        world.player.revealed_to[npc_name].append(message)

        npc = world.npcs[npc_name]
        reply = NPCDialogueAgent.respond(npc=npc, world=world, player_message=message)
        events.append({"kind": "npc", "speaker": npc_name, "text": reply})
        world.turn_count += 1

        # 阶段推进检测
        pending = rules.check_phase_transition(world)
        if pending and pending != world.phase:
            events.append({"kind": "system", "speaker": "", "text": f"已满足 {pending} 阶段进入条件，使用「推进时段」即可进入。"})

        return ActionResult(ok=True, events=events)

    # ---- move ----
    if action.type == ACTION_MOVE:
        loc = action.target or ""
        if not loc:
            return ActionResult(ok=False, error="移动需要指定地点")
        if loc not in VALID_LOCATIONS:
            return ActionResult(ok=False, error=f"地点无效。可用地点: {', '.join(VALID_LOCATIONS)}")
        desc = rules.move_to(world, loc)
        events.append({"kind": "system", "speaker": "", "text": f"移动到: {loc}"})
        events.append({"kind": "system", "speaker": "", "text": desc})
        return ActionResult(ok=True, events=events)

    # ---- investigate ----
    if action.type == ACTION_INVESTIGATE:
        loc = world.player.location
        if not rules.can_investigate(loc):
            return ActionResult(ok=False, error=f"在 {loc} 没有可调查的物品。")
        gained = rules.investigate(world, loc)
        if gained:
            events.append({"kind": "investigate", "speaker": "", "text": f"在 {loc} 获得了: {', '.join(gained)}"})
        else:
            events.append({"kind": "investigate", "speaker": "", "text": _investigate_empty_hint(world, loc)})
        return ActionResult(ok=True, events=events)

    # ---- advance ----
    if action.type == ACTION_ADVANCE:
        pending = rules.check_phase_transition(world)
        if not pending:
            # 条件未满足，不推进 clock，也不推进 phase
            if world.phase == rules.PHASE_DINNER:
                talks = rules.count_player_talks(world)
                remain = max(0, rules.DINNER_MIN_TALKS - talks)
                return ActionResult(ok=False, error=f"还不能进入调查阶段，还需盘问 {remain} 名人物。")
            if world.phase == rules.PHASE_INVESTIGATION:
                ev_count = rules.count_player_evidence(world)
                remain = max(0, rules.INVESTIGATION_MIN_EVIDENCE - ev_count)
                return ActionResult(ok=False, error=f"还不能进入对峙阶段，还需获得 {remain} 条证据。")
            return ActionResult(ok=False, error="当前无法推进时段。")

        old_clock = world.clock
        new_clock = rules.advance_clock(world)
        rules.advance_phase(world)

        events.append({"kind": "clock", "speaker": "", "text": f"⏰ {rules.clock_name(old_clock)} → {rules.clock_name(new_clock)}"})

        # Narrator 氛围描写
        narration = NarratorAgent.narrate(world)
        events.append({"kind": "narrator", "speaker": "", "text": narration})

        # NPC 时段行为
        npc_events = rules.on_clock_advance(world)
        for ev in npc_events:
            events.append({"kind": "system", "speaker": "", "text": ev})

        # 林婉 DecisionAgent
        if rules._linwan_evidence_exposed(world):
            linwan = world.npcs.get("林婉")
            if linwan and linwan.alive:
                decision = NPCDecisionAgent.decide(linwan, world)
                act = decision.get("action", "wait")
                if act != "wait":
                    reason = decision.get("reason", "")
                    events.append({"kind": "system", "speaker": "", "text": f"【林婉的决策】{act}（原因: {reason}）"})

        # 阶段推进提示
        after_pending = rules.check_phase_transition(world)
        if after_pending and after_pending != world.phase:
            events.append({"kind": "system", "speaker": "", "text": f"已满足 {after_pending} 阶段进入条件，使用「推进时段」即可进入。"})

        # 时段到顶，自动结局
        if world.clock >= rules.MAX_CLOCK and world.phase != "ending":
            rules.advance_phase(world)
            if world.phase == "ending":
                judgment = DirectorAgent.judge(world, player_accusation=None)
                events.append({
                    "kind": "game_over",
                    "speaker": "",
                    "text": f"渡船已经靠岸！时间耗尽。结局: {judgment['verdict']}",
                    "verdict": judgment.get("verdict", ""),
                    "summary": judgment.get("summary", ""),
                    "culprit": judgment.get("culprit", ""),
                    "innocent": judgment.get("innocent", []),
                    "ending_key": "culprit_escape",
                })

        return ActionResult(ok=True, events=events)

    # ---- accuse ----
    if action.type == ACTION_ACCUSE:
        accused = action.target or ""
        if not accused:
            return ActionResult(ok=False, error="指认需要指定嫌疑人")

        if world.phase != rules.PHASE_CONFRONTATION:
            pending = rules.check_phase_transition(world)
            if pending:
                return ActionResult(ok=False, error=f"需要先进入 {pending} 阶段才能指认。")
            return ActionResult(ok=False, error="还没到对峙阶段，继续调查吧。")

        if accused not in world.npcs:
            return ActionResult(ok=False, error=f"'{accused}' 不是有效嫌疑人。")

        events.append({"kind": "system", "speaker": "", "text": f"指认: {accused}"})
        judgment = DirectorAgent.judge(world, player_accusation=accused)
        world.phase = "ending"
        ending_key = "culprit_caught" if accused == judgment.get("culprit") else "wrong_accuse"
        events.append({
            "kind": "game_over",
            "speaker": "",
            "text": f"【结局】{judgment['verdict']} - {judgment['summary']}",
            "verdict": judgment.get("verdict", ""),
            "summary": judgment.get("summary", ""),
            "culprit": judgment.get("culprit", ""),
            "innocent": judgment.get("innocent", []),
            "ending_key": ending_key,
        })
        return ActionResult(ok=True, events=events)

    # ---- status ----
    if action.type == ACTION_STATUS:
        locs = rules.all_npc_locations(world)
        lines = [
            f"时段: {rules.clock_name(world.clock)}",
            f"阶段: {world.phase}",
            f"你在: {world.player.location}",
            f"持有物品: {', '.join(world.player.inventory) or '(无)'}",
            f"已对话NPC数: {len(world.player.revealed_to)}",
            "各人位置:",
        ]
        for name, loc in locs.items():
            marker = " ←" if name in world.player.revealed_to else ""
            lines.append(f"  {name}: {loc}{marker}")
        text = "\n".join(lines)
        events.append({"kind": "system", "speaker": "", "text": text})
        return ActionResult(ok=True, events=events)

    # ---- save ----
    if action.type == ACTION_SAVE:
        from game.persistence import save_game
        try:
            path = save_game(world)
            events.append({"kind": "system", "speaker": "", "text": f"已存档: {path}"})
            return ActionResult(ok=True, events=events)
        except Exception as e:
            return ActionResult(ok=False, error=f"存档失败: {e}")

    # ---- load ----
    if action.type == ACTION_LOAD:
        from game.persistence import load_game
        try:
            world = load_game()
            events.append({"kind": "system", "speaker": "", "text": "读档成功"})
            return ActionResult(ok=True, events=events)
        except FileNotFoundError:
            return ActionResult(ok=False, error="没有找到存档")
        except Exception as e:
            return ActionResult(ok=False, error=f"读档失败: {e}")

    return ActionResult(ok=False, error=f"未知动作类型: {action.type}")
