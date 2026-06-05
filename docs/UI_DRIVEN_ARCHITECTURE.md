# UI_DRIVEN_ARCHITECTURE.md — UI 驱动架构定义

> 本文档定义 UI 如何作为游戏主入口，以及数据在前后端之间的流动方式。

---

## 1. UI 是主入口

用户不应该主要靠记忆命令来玩，而应该通过界面看到并操作：

```
当前地点
当前时间
当前阶段
在场 NPC
可行动作按钮（来自 available_actions）
证据背包
公共事件记录
NPC 对话区
旁白区
指认入口
```

界面呈现的状态来自 `WorldState`，由后端 `_world_to_dict()` 序列化后通过 `/api/state` 或 `/api/action` 响应返回。

---

## 2. UI 到后端的数据流

```
UI button / form
    ↓
POST /api/action  { session_id, type, target?, text? }
    ↓
ActionRequest (FastAPI Pydantic Model)
    ↓
PlayerAction { type, target, text }
    ↓
dispatch(world, action) → ActionResult { ok, events, error }
    ↓
rules.py / agents.py (修改 WorldState)
    ↓
ActionResult.events + WorldState
    ↓
前端渲染新的叙事/状态/按钮
```

---

## 3. UI 不直接操纵 WorldState

```
前端不能直接修改 phase、clock、inventory、npc memory。
前端只能发送动作。
所有状态变化必须由 dispatch()、rules.py、agents.py 完成。
```

违反此原则的例子（禁止）：
- 前端直接 `fetch('/api/state', {method:'PATCH', body: {...}}` 修改状态
- 前端本地计算后直接覆盖 `world.player.inventory`

---

## 4. /api/command 的定位

```
/api/command 只是兼容旧文本命令入口。
长期主入口是 /api/action。
/api/command 不允许重新实现游戏规则，只能 parse command → PlayerAction → dispatch。
```

当前 `web_api.py` 中 `/api/command` 已统一走 `dispatch()`，不再复制规则逻辑。

---

## 5. MiniMax-M3 与 UI 的关系

```
UI 负责呈现选择和结果。
M3 负责生成 NPC 语言、叙事、关键决策、结局。
M3 不直接控制 UI。
M3 不直接写数据库。
M3 不绕过 rules.py 修改状态。
```

M3 调用链：
```
dispatch() → agents.py → llm.py → MiniMax-M3 API
                        ↓
              返回文本，更新 WorldState（通过 WorldState 写回）
```

---

## 6. 未来 UI 方向

| 阶段 | 内容 |
|------|------|
| P1 | 保留简单 Web 页面，稳定 /api/action |
| P2 | 重构首页为游戏主界面：左侧剧情，中间行动，右侧状态 |
| P3 | 证据板 / 人物关系板 |
| P4 | 剧本生成器页面（设计时 Agent 参与） |
| P5 | 多剧本选择 |

**当前阶段：P1 末期，P2 筹备中。**

---

## 7. 关键架构约束（来自 ARCHITECTURE.md）

- **唯一真相源**：`WorldState` 是游戏状态的唯一真相，前端展示的状态必须来自 `_world_to_dict(world)`
- **唯一 API 入口**：`game/llm.py` 是所有 M3 调用的唯一入口
- **唯一动作入口**：`game/actions.py` 的 `dispatch()` 是所有玩家动作的入口
- **信息隔离**：NPC 的 secrets 只出现在自己的 NPCDialogueAgent prompt 中，不出现在其他 NPC 或全局状态中
