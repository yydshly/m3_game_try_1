# ARCHITECTURE.md —《孤岛晚宴》系统架构

> 本文件定义系统的**不可变架构**。执行模型（MiniMax M3）必须严格遵守，不得自行更改分层、数据结构或 M3 调用边界。如认为架构有问题，停下来报告，不要擅自改动。

---

## 1. 一句话定义

一个基于多 Agent 博弈的文字推理游戏后端：6 个 NPC 各自是独立 Agent，有自己的目标和秘密；玩家通过对话与行动影响世界；剧情是多方博弈的**涌现结果**，不是预设脚本。

---

## 2. 核心设计原则（违反即架构错误）

1. **M3 是发动机，不是自动挡。** 只有需要"判断力/语言生成"的地方才调用 M3，其余一律用确定性的 Python 规则处理。详见第 5 节调用边界。
2. **世界状态是唯一真相源（Single Source of Truth）。** 所有 NPC 的记忆、关系、事件都存在一个 `WorldState` 对象里。M3 调用是无状态的——每次把需要的状态片段拼进 prompt，输出再写回 WorldState。
3. **NPC 之间不共享全知视角。** 每个 NPC 调用 M3 时，prompt 里只包含"这个 NPC 应该知道的信息"。信息隔离是玩法的核心，绝不能把全局秘密喂给单个 NPC。
4. **可重放、可调试。** 每次 M3 调用的输入/输出都记录到日志，game loop 可以从任意存档恢复。

---

## 3. 系统分层

```
┌──────────────────────────────────────────────────────────┐
│  接口层 (interface)                                          │
│    Phase 1: 命令行 CLI                                       │
│    Phase 2+: FastAPI + SSE（复用 Video Radar 经验）          │
├──────────────────────────────────────────────────────────┤
│  游戏循环层 (game_loop)        ── 纯 Python，不调 M3         │
│    解析玩家输入 → 决定触发哪些层 → 更新状态 → 返回结果         │
├──────────────────────────────────────────────────────────┤
│  Agent 层                                                    │
│    ├── NPCDialogueAgent   对话回应      ✅ 调 M3            │
│    ├── NPCDecisionAgent   重大决策      ✅ 调 M3（低频）    │
│    ├── DirectorAgent      主控裁判      ✅ 调 M3（极低频）  │
│    └── NarratorAgent      场景叙事      ✅ 调 M3（每轮一次）│
├──────────────────────────────────────────────────────────┤
│  规则层 (rules)               ── 纯 Python，绝不调 M3        │
│    时间推进 / 事件触发 / NPC 日常行动 / 触发条件判断          │
├──────────────────────────────────────────────────────────┤
│  状态层 (state)                                              │
│    WorldState（内存对象） ←→ 存档 JSON（磁盘）               │
├──────────────────────────────────────────────────────────┤
│  M3 客户端层 (llm)            ── 唯一与 MiniMax API 通信处   │
│    统一封装：调用、重试、日志、token 计数                     │
└──────────────────────────────────────────────────────────┘
```

**关键约束：除了 `llm/` 模块，其它任何地方都不许直接调 MiniMax API。**

---

## 4. 数据结构（定死，不许改字段名）

### WorldState（世界状态）

```python
@dataclass
class WorldState:
    scene: str                      # 当前场景描述，如"古堡大厅，深夜"
    phase: str                      # 游戏阶段: "dinner" | "investigation" | "confrontation" | "ending"
    clock: int                      # 逻辑时间，单位"时段"，0 起步
    player: PlayerState
    npcs: dict[str, NPCState]       # key = NPC 名字
    public_events: list[Event]      # 所有人可见的公共事件
    turn_count: int                 # 总回合数

@dataclass
class PlayerState:
    location: str
    inventory: list[str]            # 玩家持有的证据/物品
    revealed_to: dict[str, list[str]]  # {npc名: [玩家向TA透露过的秘密]}

@dataclass
class NPCState:
    name: str
    public_role: str                # 公开身份
    hidden_goal: str                # 隐藏目标（绝不直接喂给其他NPC）
    secrets: list[str]              # 知道的秘密
    personality: str                # 性格描述，影响说话风格
    memory: list[str]               # 私有记忆：和玩家/其他NPC的互动记录
    relationships: dict[str, int]   # {对方名: 好感度 -100~100}
    alive: bool
    suspicion_of_player: int        # 对玩家的怀疑度 0~100

@dataclass
class Event:
    clock: int
    description: str
    visible_to: list[str]           # 谁能看到这个事件，["all"] 表示全员
```

> 完整 6 个 NPC 的初始设定见 `docs/SCENARIO.md`。

---

## 5. M3 调用边界（最重要——这是"不无脑用"的体现）

| Agent | 触发频率 | 何时调用 | 输入（prompt 拼什么） | 输出格式 |
|-------|---------|---------|---------------------|---------|
| **NPCDialogueAgent** | 高频 | 玩家对某 NPC 说话时 | 该 NPC 的设定+私有记忆+对话历史+玩家这句话 | 纯文本（NPC的话）|
| **NPCDecisionAgent** | 低频 | 规则层判断触发条件满足时 | 该 NPC 的设定+当前局势 | JSON: `{action, target, reason}` |
| **DirectorAgent** | 极低频 | 每个 phase 结束 / 关键证据出现 | 全局世界状态摘要 | JSON: `{next_phase, trigger_events, game_over}` |
| **NarratorAgent** | 每轮一次 | 时段推进时 | 场景+最近公共事件 | 纯文本（氛围描写）|

**绝不调用 M3 的情况（必须用规则层）：**
- 时间/时段推进 → 简单计数器
- NPC 在没人互动时的"日常位置移动" → 预设巡逻表
- 判断"玩家是否持有某证据" → 查 inventory
- 触发条件判断（如"玩家是否已透露秘密 X"） → 查 revealed_to

---

## 6. 模块文件结构

```
island-dinner/
├── docs/
│   ├── ARCHITECTURE.md      # 本文件（架构，不可变）
│   ├── SCENARIO.md          # 场景与6个NPC完整设定
│   ├── PLAN.md              # 分阶段执行计划
│   └── AGENTS.md            # 给执行模型M3的工作规则
├── prompts/                 # 所有 M3 prompt 模板（与代码分离）
│   ├── npc_dialogue.txt
│   ├── npc_decision.txt
│   ├── director.txt
│   └── narrator.txt
├── game/
│   ├── state.py             # WorldState 等数据结构
│   ├── llm.py               # M3 客户端封装（唯一调API处）
│   ├── agents.py            # 4 个 Agent
│   ├── rules.py             # 规则层
│   ├── game_loop.py         # 主循环
│   └── scenario_data.py     # 6个NPC初始数据（从SCENARIO.md转译）
├── main.py                  # Phase 1 命令行入口
├── requirements.txt
└── .env.example             # MINIMAX_API_KEY=
```

---

## 7. 反作弊/反失控约束（M3 必须遵守）

- NPC 对话生成时，**禁止让 M3 凭空发明新秘密或新人物**。M3 只能基于 prompt 里给定的 secrets 发挥。
- DirectorAgent 输出的 `next_phase` 必须是第 4 节定义的合法值之一，非法值由代码层拒绝并重试。
- 所有 M3 输出若要求 JSON，必须在代码层做 `try/except` 解析，失败则重试最多 2 次，再失败则降级到规则默认值。
