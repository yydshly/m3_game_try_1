"""
game/rules.py — 规则层

Phase 2+3 实现内容:
- 时段推进(纯计数器,不调 M3)
- 阶段(phase)推进条件判断
- 预设巡逻表(NPC 日常位置移动)
- 调查规则(物品 → 玩家 inventory)
- Phase 3: NPC 决策触发条件、NPC 间关系变化
"""

from __future__ import annotations

from dataclasses import dataclass

from game.state import (
    PHASE_CONFRONTATION,
    PHASE_DINNER,
    PHASE_ENDING,
    PHASE_INVESTIGATION,
    WorldState,
)

# ============================================================
# 阶段推进条件
# ============================================================

DINNER_MIN_TALKS: int = 5
INVESTIGATION_MIN_EVIDENCE: int = 2
CONFRONTATION_CLOCK_DAWN: int = 8


def count_player_talks(world: WorldState) -> int:
    return len(world.player.revealed_to)


def count_player_evidence(world: WorldState) -> int:
    return len(world.player.inventory)


def check_phase_transition(world: WorldState) -> str | None:
    phase = world.phase

    if phase == PHASE_DINNER:
        if count_player_talks(world) >= DINNER_MIN_TALKS:
            return PHASE_INVESTIGATION

    elif phase == PHASE_INVESTIGATION:
        if count_player_evidence(world) >= INVESTIGATION_MIN_EVIDENCE:
            return PHASE_CONFRONTATION

    elif phase == PHASE_CONFRONTATION:
        if world.clock >= CONFRONTATION_CLOCK_DAWN:
            return PHASE_ENDING

    return None


def advance_phase(world: WorldState) -> str:
    from game.state import Event

    next_phase = check_phase_transition(world)
    if next_phase is None:
        return world.phase

    old_phase = world.phase
    world.phase = next_phase

    world.public_events.append(
        Event(
            clock=world.clock,
            description=f"【阶段推进】{old_phase} → {next_phase}",
            visible_to=["all"],
        )
    )
    return next_phase


# ============================================================
# 时段推进
# ============================================================

CLOCK_NAMES: dict[int, str] = {
    0: "深夜 0:00",
    1: "凌晨 1:00",
    2: "凌晨 2:00",
    3: "凌晨 3:00",
    4: "凌晨 4:00",
    5: "凌晨 5:00",
    6: "清晨 6:00",
    7: "清晨 7:00",
    8: "早晨 8:00 (渡船到达)",
}
MAX_CLOCK: int = 8


def advance_clock(world: WorldState) -> int:
    if world.clock >= MAX_CLOCK:
        return world.clock
    world.clock += 1
    return world.clock


def clock_name(clock: int) -> str:
    return CLOCK_NAMES.get(clock, f"时段 {clock}")


# ============================================================
# NPC 巡逻表
# ============================================================

_NPC_LOCATIONS: dict[str, dict[int, str]] = {
    "陈伯": {0: "书房", 1: "书房", 2: "走廊", 3: "自己房间", 4: "厨房", 5: "厨房", 6: "大厅", 7: "大厅", 8: "大厅"},
    "苏苏": {0: "餐厅", 1: "自己房间", 2: "自己房间", 3: "自己房间", 4: "走廊", 5: "厨房", 6: "大厅", 7: "大厅", 8: "大厅"},
    "林婉": {0: "书房", 1: "走廊", 2: "自己房间", 3: "自己房间", 4: "走廊", 5: "大厅", 6: "大厅", 7: "大厅", 8: "大厅"},
    "王总": {0: "餐厅", 1: "书房", 2: "书房", 3: "自己房间", 4: "走廊", 5: "大厅", 6: "大厅", 7: "大厅", 8: "大厅"},
    "阿福": {0: "厨房", 1: "厨房", 2: "厨房", 3: "厨房", 4: "厨房", 5: "厨房", 6: "厨房", 7: "大厅", 8: "大厅"},
    "小张": {0: "保安室", 1: "保安室", 2: "走廊", 3: "走廊", 4: "保安室", 5: "保安室", 6: "大厅", 7: "大厅", 8: "大厅"},
}


def npc_location_at(npc_name: str, clock: int) -> str:
    if npc_name not in _NPC_LOCATIONS:
        return "未知"
    locs = _NPC_LOCATIONS[npc_name]
    for c in range(clock, -1, -1):
        if c in locs:
            return locs[c]
    return "大厅"


def all_npc_locations(world: WorldState) -> dict[str, str]:
    return {name: npc_location_at(name, world.clock) for name in world.npcs}


# ============================================================
# 调查规则
# ============================================================

INVESTIGATION_SPOTS: dict[str, list[str]] = {
    "书房": ["新遗嘱草稿"],
    "厨房": [],
    "大厅": [],
    "保安室": [],
    "陈伯房间": [],
    "苏苏房间": [],
    "林婉房间": ["林婉的病历笔记"],
    "王总房间": [],
    "餐厅": [],
    "走廊": [],
    "自己房间": [],
}

KEY_EVIDENCE: set[str] = {
    "异常的茶杯残留",
    "新遗嘱草稿",
    "林婉的病历笔记",
    "借据",
    "厨师阿福的证词",
}

# 证据元数据（UI展示用，不影响游戏规则）
EVIDENCE_METADATA: dict[str, dict] = {
    "异常的茶杯残留": {"source": "书房", "points_to": "投毒", "level": "关键", "icon": "🧪"},
    "新遗嘱草稿":   {"source": "书房", "points_to": "动机", "level": "重要", "icon": "📄"},
    "林婉的病历笔记": {"source": "林婉房间", "points_to": "知情", "level": "重要", "icon": "💊"},
    "借据":         {"source": "书房", "points_to": "动机", "level": "线索", "icon": "📋"},
    "厨师阿福的证词": {"source": "厨房", "points_to": "女性凶手", "level": "线索", "icon": "🍳"},
}

# 地点主题（UI 场景配色用）
LOCATION_THEMES: dict[str, dict] = {
    "大厅":    {"theme": "hall",    "mood": "庄重", "color": "#c9a227"},
    "书房":    {"theme": "study",   "mood": "压抑", "color": "#b87333"},
    "厨房":    {"theme": "kitchen", "mood": "紧张", "color": "#4a7c59"},
    "餐厅":    {"theme": "dining",   "mood": "混乱", "color": "#8b3a3a"},
    "保安室":  {"theme": "security", "mood": "冷寂", "color": "#3a5a8b"},
    "走廊":    {"theme": "corridor", "mood": "空旷", "color": "#5a5a6e"},
    "陈伯房间":  {"theme": "room",    "mood": "简朴", "color": "#7a6a3a"},
    "苏苏房间":  {"theme": "room",    "mood": "私密", "color": "#7a3a6a"},
    "林婉房间":  {"theme": "room",    "mood": "消毒感", "color": "#3a6a7a"},
    "王总房间":  {"theme": "room",    "mood": "商务感", "color": "#3a4a7a"},
    "自己房间":  {"theme": "room",    "mood": "临时感", "color": "#4a5a5a"},
}

# 地点场景描写(规则层,不需要 M3)
LOCATION_DESCRIPTIONS: dict[str, str] = {
    "大厅": "古堡大厅,水晶吊灯发出昏黄的光。窗外暴风雨呼啸,海浪拍打着礁石。",
    "书房": "周慎之的书房。书架林立,书桌上散落着文件和一支钢笔。空气中有淡淡的药味。",
    "厨房": "别墅厨房,灶台上还有余温。阿福一个人坐在角落,神情不安。",
    "餐厅": "长餐桌上摆着吃了一半的晚宴菜肴,酒杯东倒西歪,像是匆忙离席。",
    "保安室": "监控室,几块屏幕闪烁着。大部分时间,这里只有小张一个人。",
    "走廊": "长长的走廊,墙上挂着几幅人物油画。脚步声在空旷中回响。",
    "陈伯房间": "老管家的房间,简朴整洁。床头放着一张褪色的老照片。",
    "苏苏房间": "苏苏的卧室,化妆台上堆满了化妆品,角落里有个未寄出的信封。",
    "林婉房间": "林婉的房间,医学书籍堆在桌上,空气中有消毒水的气味。",
    "王总房间": "王总的房间,行李箱敞开着,里面是各类商业文件。",
    "自己房间": "临时客房,布置简单。窗外能听到海浪拍岸的声音。",
}


def get_location_description(location: str, world: WorldState) -> str:
    """获取地点的氛围描写,含当前时段在场的 NPC。"""
    base = LOCATION_DESCRIPTIONS.get(location, f"{location},昏暗不明。")

    # 找出当前时段在此地点的 NPC
    locs = all_npc_locations(world)
    present = [name for name, loc in locs.items() if loc == location]

    if present:
        names = "、".join(present)
        return f"{base}\n在这里的人: {names}。"
    return base


def can_investigate(location: str) -> bool:
    return location in INVESTIGATION_SPOTS


def investigate(world: WorldState, location: str) -> list[str]:
    """调查当前地点,返回获得的物品列表(可能为空)。

    特殊获取逻辑:
    - 书房: 借据(需先和王总说过话,暗示你知道保险柜的事)
    - 书房: 茶杯残留(需先和陈伯说过话)
    - 厨房: 阿福证词(需和阿福对话至少2次)
    """
    gained: list[str] = []

    # === 书房: 借据 + 茶杯残留 ===
    if location == "书房":
        # 借据: 需先和王总说过话,暗示你知道保险柜的事
        if "王总" in world.player.revealed_to and "借据" not in world.player.inventory:
            gained.append("借据")

        # 茶杯残留: 需先和陈伯说过话
        if "陈伯" in world.player.revealed_to and "异常的茶杯残留" not in world.player.inventory:
            gained.append("异常的茶杯残留")

        # 书房固定物品
        for item in INVESTIGATION_SPOTS.get("书房", []):
            if item not in ("借据", "异常的茶杯残留") and item not in world.player.inventory:
                gained.append(item)

    # === 厨房: 阿福证词 ===
    elif location == "厨房":
        # 阿福证词: 需和阿福对话至少2次
        afu_talks = len(world.player.revealed_to.get("阿福", []))
        if afu_talks >= 2 and "厨师阿福的证词" not in world.player.inventory:
            gained.append("厨师阿福的证词")

    # === 其他地点固定物品 ===
    else:
        for item in INVESTIGATION_SPOTS.get(location, []):
            if item not in world.player.inventory:
                gained.append(item)

    # 写入 inventory
    for item in gained:
        world.player.inventory.append(item)

    # 记公共事件
    if gained:
        from game.state import Event

        world.public_events.append(
            Event(
                clock=world.clock,
                description=f"【调查】在 {location} 发现了: {', '.join(gained)}",
                visible_to=["all"],
            )
        )
        _check_linwan_trigger(world, f"调查{location}获得{gained}")

    return gained


def move_to(world: WorldState, location: str) -> str:
    """移动到地点,返回场景氛围描写。"""
    world.player.location = location
    return get_location_description(location, world)


# ============================================================
# Phase 3: NPC 决策触发条件
# ============================================================

@dataclass
class DecisionTrigger:
    """一个决策触发器。"""
    npc_name: str           # 触发的 NPC
    condition_func: str      # 条件函数名(用于日志)
    description: str         # 描述(用于日志)


def _linwan_evidence_exposed(world: WorldState) -> bool:
    """林婉触发条件:玩家的证据可能暴露她知道绝症。"""
    # 玩家获得了新遗嘱草稿（暗示动机）
    if "新遗嘱草稿" in world.player.inventory:
        return True
    # 玩家获得了林婉的病历笔记（直接证明她知情）
    if "林婉的病历笔记" in world.player.inventory:
        return True
    return False


def _check_linwan_trigger(world: WorldState, reason: str) -> None:
    """检查林婉是否应该触发 DecisionAgent。"""
    if world.npcs["林婉"].alive and _linwan_evidence_exposed(world):
        # 标记林婉需要做决策，下一个时段她会行动
        # 在 Phase 3 实现中，我们在 rules 层记录这个触发
        from game.state import Event

        world.public_events.append(
            Event(
                clock=world.clock,
                description=f"【触发】林婉感到不安——{reason}",
                visible_to=["all"],
            )
        )


# Phase 3: 关键证据出现时自动触发的 NPC 行为
# 这些是规则层可以直接执行的效果，不需要 M3

LINWAN_DESTROY_ACTIONS: dict[str, str] = {
    "林婉的病历笔记": "林婉悄悄潜回房间，发现病历笔记被人动过，立刻将其烧毁。",
    "新遗嘱草稿": "林婉在走廊徘徊，若有所思地看向书房方向。",
}


def check_npc_triggered_actions(world: WorldState) -> list[str]:
    """
    检查哪些 NPC 的自动触发行为应该执行。
    返回描述列表。
    """
    results: list[str] = []
    linwan = world.npcs.get("林婉")
    if not linwan or not linwan.alive:
        return results

    if _linwan_evidence_exposed(world):
        # 林婉发现病历笔记可能暴露，采取行动
        if "林婉的病历笔记" in world.player.inventory:
            # 病历笔记被玩家获得后，林婉会立刻去烧毁
            # 笔记仍然在玩家手里，但林婉已经行动了
            results.append(
                "【林婉行动】林婉趁人不备潜回自己房间，将剩余的病历资料烧毁。"
            )
            from game.state import Event
            world.public_events.append(
                Event(
                    clock=world.clock,
                    description="【林婉行动】销毁了剩余的病历资料。",
                    visible_to=["all"],
                )
            )
    return results


# ============================================================
# Phase 3: NPC 关系变化
# ============================================================

# 关系变化规则:基于玩家行为
RELATIONSHIP_CHANGES: dict[tuple[str, str], int] = {
    # (npc_name, event_type) -> relationship_delta
    # Phase 3 实现基础版本
}


def apply_relationship_change(
    world: WorldState,
    npc_name: str,
    delta: int,
) -> None:
    """对 NPC 施加关系变化， clamped 到 -100~100。"""
    if npc_name not in world.npcs:
        return
    npc = world.npcs[npc_name]
    current = npc.relationships.get("玩家", 0)
    new_val = max(-100, min(100, current + delta))
    npc.relationships["玩家"] = new_val


def change_suspicion(world: WorldState, npc_name: str, delta: int) -> None:
    """对 NPC 施加对玩家怀疑度变化， clamped 到 0~100。"""
    if npc_name not in world.npcs:
        return
    npc = world.npcs[npc_name]
    current = npc.suspicion_of_player
    new_val = max(0, min(100, current + delta))
    npc.suspicion_of_player = new_val


# 当玩家从某 NPC 处套到关键信息，该 NPC 对玩家的警惕上升
def on_secret_exposed(world: WorldState, npc_name: str) -> None:
    """NPC 发现玩家可能套话，警惕上升。"""
    change_suspicion(world, npc_name, +15)
    # 关系略微下降
    apply_relationship_change(world, npc_name, -5)


# ============================================================
# Phase 3: 时段推进时 NPC 自动行为
# ============================================================

def on_clock_advance(world: WorldState) -> list[str]:
    """
    时段推进时，各 NPC 的自动行为（规则层决定，不调 M3）。
    返回描述列表。
    """
    events: list[str] = []

    # 林婉在证据暴露后，每到深夜时段可能采取行动
    if _linwan_evidence_exposed(world) and world.clock >= 2:
        triggered = check_npc_triggered_actions(world)
        events.extend(triggered)

    return events
