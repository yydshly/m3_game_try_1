# PLAN_UI重构.md — 从"命令行"到"游戏"的架构改造

> 给执行模型（M3）的施工文档。本次只做**架构地基**，不碰美术、不碰界面好不好看。
> 目标：让后端从"解析命令字符串"变成"结构化动作 + 可用动作列表"，为后续任何 UI（纯文字 / 立绘）打地基。
>
> **纪律重申**：严格按本文 Step 顺序做，每个 Step 跑通验收再下一个。不许提前做 UI 美化。

---

## 0. 为什么要做这次改造（背景，必读）

当前 `game/web_api.py` 和 `main.py` 都靠**解析命令字符串**驱动：

```python
if cmd.startswith("跟"):
    npc_name = parts[1]
    message = cmd.split("说:", 1)[1]
```

这导致：前端即使做成按钮，也得把按钮拼回 `"跟 陈伯 说: xxx"` 字符串发给后端——本质还是命令行，做不出"点击式"游戏交互。

**改造核心**：引入两样东西
1. **结构化动作协议**（Action）：前端发 `{type, target, text}`，后端不再 split 字符串。
2. **可用动作层**（`game/actions.py`）：给定 WorldState，返回"玩家此刻能做什么"，前端据此渲染选项/按钮。

---

## 1. 不可变约束（继承 ARCHITECTURE.md）

- 仍然 **只有 `game/llm.py` 能调 MiniMax API**。
- WorldState 仍是唯一真相源，本次**不新增、不删除 WorldState 字段**。
- 业务逻辑仍在 `game/rules.py` 和 `game/agents.py`，本次新增的 `actions.py` 只做"动作分发 + 可用动作生成"，**不写新的游戏规则**，只调用已有的 rules/agents 函数。

---

## ⭐ Step 1：定义结构化动作协议（`game/actions.py` 第一部分）

新建 `game/actions.py`。先定义动作类型常量和数据结构，**不写逻辑**。

```python
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
```

**验收：**
```bash
python -c "from game.actions import PlayerAction, ActionResult, AvailableAction, LEGAL_ACTION_TYPES; print('OK', LEGAL_ACTION_TYPES)"
```

---

## ⭐ Step 2：实现 `available_actions()`（可用动作生成）

在 `game/actions.py` 中实现。**这是整个改造的灵魂**——它把"游戏当前状态"翻译成"玩家能点的按钮"。

规则（全部查 WorldState + 调用已有 rules 函数，不调 M3）：

| 动作 | 何时可用 | label 示例 |
|------|---------|-----------|
| `talk` | 与玩家**同地点**的、`alive` 的 NPC，每人一个 | "盘问 陈伯" |
| `move` | 所有合法地点（排除当前所在地）| "前往 书房" |
| `investigate` | 当前地点 `can_investigate()` 为真 | "调查 书房" |
| `advance` | 总是可用 | "推进时段" |
| `accuse` | 仅 `phase == confrontation` 时，对每个存活 NPC 一个；其余阶段 `enabled=False` + hint | "指认 林婉" |

```python
from game.rules import can_investigate, all_npc_locations, npc_location_at
from game.state import WorldState, PHASE_CONFRONTATION

# 合法地点表（与 main.py 的 VALID_LOCATIONS 统一，建议挪到这里集中管理）
VALID_LOCATIONS: list[str] = [
    "书房", "厨房", "大厅", "保安室", "陈伯房间", "苏苏房间",
    "林婉房间", "王总房间", "餐厅", "走廊", "自己房间",
]

def available_actions(world: WorldState) -> list[AvailableAction]:
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

    # 4. 推进时段
    actions.append(AvailableAction(type="advance", label="推进时段"))

    # 5. 指认（仅对峙阶段可用）
    in_confront = world.phase == PHASE_CONFRONTATION
    for name, npc in world.npcs.items():
        if npc.alive:
            actions.append(AvailableAction(
                type="accuse", target=name, label=f"指认 {name}",
                enabled=in_confront,
                hint="" if in_confront else "需先进入对峙阶段"))

    return actions
```

**验收：**
```bash
python -c "
import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from game.scenario_data import build_initial_world
from game.actions import available_actions
w = build_initial_world()
for a in available_actions(w):
    print(a.type, a.target, a.label, a.enabled, a.hint)
"
# 期望：玩家在'大厅'，开局没有 NPC 在大厅（时段0），所以没有 talk；
#       有一堆 move；advance；6 个 accuse 但 enabled=False
```

---

## ⭐ Step 3：实现 `dispatch()`（动作分发）

把现在散在 `web_api.py / main.py` 里的 `if cmd.startswith(...)` 逻辑，**集中**到 `actions.dispatch()`。它接收 `PlayerAction`，调用已有 rules/agents，返回 `ActionResult`。

要点：
- 这里**复用**已有的 `investigate / move_to / advance_clock / advance_phase / NPCDialogueAgent.respond / NarratorAgent.narrate / DirectorAgent` 等，**不重写规则**。
- `events` 里每条是 `{"kind": "...", "speaker": "...", "text": "..."}`，`kind` ∈ `{"narrator","npc","system","investigate","clock","game_over"}`。前端只认这个结构，不再认散字符串。
- **修复对话地点校验**：`talk` 时若 target NPC 不在玩家所在地点，返回 `ok=False, error="他不在这里"`。
- **修复 revealed_to 语义**：`talk` 仍记录对话，但阶段推进的判定改为"对话过的不同 NPC 数"（保持现有行为即可，本次不动 rules）。

```python
def dispatch(world: WorldState, action: PlayerAction) -> ActionResult:
    if action.type not in LEGAL_ACTION_TYPES:
        return ActionResult(ok=False, error=f"非法动作: {action.type}")
    # ... 按 type 分发到已有函数，组装 events ...
```

**验收：**
```bash
python -c "
import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from game.scenario_data import build_initial_world
from game.actions import dispatch, PlayerAction
w = build_initial_world()
# 移动到书房 → 调查 → 应拿到'新遗嘱草稿'
print(dispatch(w, PlayerAction(type='move', target='书房')))
print(dispatch(w, PlayerAction(type='investigate')))
print('inventory:', w.player.inventory)
"
```

---

## ⭐ Step 4：Web API 改用结构化协议（改 `web_api.py`）

新增结构化端点，**保留旧的 `/api/command` 字符串端点**（向后兼容，别删，避免前端立刻崩）：

```python
class ActionRequest(BaseModel):
    session_id: str
    type: str
    target: str | None = None
    text: str | None = None

@app.post("/api/action")        # 新：结构化
async def post_action(req: ActionRequest): ...

@app.get("/api/actions/{session_id}")   # 新：返回可用动作列表
async def get_available(session_id: str): ...
```

- `/api/action` 内部：构造 `PlayerAction` → `dispatch()` → 把 `ActionResult.events` 逐条 `await b.put(...)` 推 SSE → 返回最新 `_world_to_dict(world)` + `available_actions`。
- `_world_to_dict()` 里**加一个字段** `"available_actions": [...]`，让前端每次都能拿到最新可点动作。

**验收：**
```bash
python web_main.py
# 另开终端：
curl -X POST localhost:8000/api/session
curl localhost:8000/api/actions/<刚返回的session_id>
# 期望：返回结构化的可用动作 JSON
```

---

## ⭐ Step 5：回归——确保 CLI 和旧 Web 仍能跑

- `main.py` 改为：解析命令字符串 → 构造 `PlayerAction` → 调 `dispatch()`。删掉 main.py 里重复的规则调用。
- 旧 `/api/command` 端点内部也改为走 `dispatch()`（先把字符串解析成 PlayerAction）。
- **目标：CLI 行为和改造前完全一致**，证明 dispatch() 没改变游戏逻辑，只是换了入口。

**验收：**
```bash
python main.py
# 输入：跟 陈伯 说: 你好    （注意陈伯要和你同地点，否则提示"他不在这里"——这是新修的正确行为）
# 输入：移动到 书房 → 调查 → 应获得 新遗嘱草稿
```

---

## 本次完成的判定（交付给设计师确认）

全部 5 个 Step 验收通过后，输出：
```
UI重构地基 完成 ✅
- game/actions.py 提供 PlayerAction / dispatch / available_actions
- /api/action 与 /api/actions/{id} 可用
- CLI 行为回归一致，对话地点校验已修复
下一步建议：基于 available_actions 做"纯文字版选项式 UI 原型"
```

---

## ❌ 本次明确不做（防止 M3 跑偏）

- 不做任何界面美化、不加图片/立绘/canvas。
- 不改 WorldState 字段、不改 SCENARIO 数据。
- 不新增游戏规则（证据获取、结局种类等是**另一个** PLAN，不在本次范围）。
- `map.html`（canvas 地图版）本次不维护，建议后续删除——它依赖美术资源，是错误方向。
</content>
</invoke>
