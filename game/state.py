"""
game/state.py — 世界状态数据结构

严格对应 docs/ARCHITECTURE.md 第 4 节定义,禁止增删字段名。
所有 Agent / 规则层 / 接口层都围绕这些结构读写。

设计要点:
- WorldState 是"单一真相源",M3 调用是无状态的:每次拼 prompt 时从这里取片段,
  返回后再写回这里。
- NPCState.secrets 与 hidden_goal 是该 NPC 的私有信息,绝不能拼进其他 NPC 的 prompt。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# Phase 的合法取值(供 DirectorAgent 输出校验时引用,Phase 1 暂不强制)
PHASE_DINNER = "dinner"
PHASE_INVESTIGATION = "investigation"
PHASE_CONFRONTATION = "confrontation"
PHASE_ENDING = "ending"
LEGAL_PHASES: tuple[str, ...] = (
    PHASE_DINNER,
    PHASE_INVESTIGATION,
    PHASE_CONFRONTATION,
    PHASE_ENDING,
)


@dataclass
class Event:
    """一条事件记录。visible_to 决定哪些人能看到它。"""

    clock: int
    description: str
    visible_to: list[str]  # 角色名列表;["all"] 表示公开事件


@dataclass
class PlayerState:
    """玩家状态。"""

    location: str
    inventory: list[str] = field(default_factory=list)
    # 玩家向某个 NPC 透露过的秘密/线索清单:{npc名: [秘密文本, ...]}
    revealed_to: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class NPCState:
    """单个 NPC 的状态。所有秘密信息只在该 NPC 自己的 prompt 里出现。"""

    name: str
    public_role: str
    hidden_goal: str
    secrets: list[str] = field(default_factory=list)
    personality: str = ""
    # 私有记忆:与玩家/其他 NPC 的互动记录(每条是一段自然语言)
    memory: list[str] = field(default_factory=list)
    # 对其他角色的好感度,范围 -100 ~ 100,key 是对方名字
    relationships: dict[str, int] = field(default_factory=dict)
    alive: bool = True
    # 对玩家的怀疑度,0 ~ 100
    suspicion_of_player: int = 0


@dataclass
class WorldState:
    """游戏的全局状态对象。"""

    scene: str  # 当前场景描述,例如 "古堡大厅,深夜"
    phase: str  # 见 LEGAL_PHASES
    clock: int  # 逻辑时间,单位"时段",从 0 起步
    player: PlayerState
    npcs: dict[str, NPCState]  # key = NPC 名字
    public_events: list[Event] = field(default_factory=list)
    turn_count: int = 0
