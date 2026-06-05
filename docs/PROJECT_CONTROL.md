# PROJECT_CONTROL.md — 项目管控规则

> 本文档是项目的基本规则手册，供后续接手 AI Agent 参考执行。
> 不是愿景文档，不写空泛目标，只写可执行的边界和纪律。

---

## 1. 项目当前阶段

MVP 验证后期 / 架构稳定期。
游戏核心闭环已通，但 UI、存档槽位、Agent 调优仍有迭代空间。

---

## 2. 核心目标（定死）

- 保持游戏可完整跑通：对话 → 调查集证 → 对峙指认 → 结局
- 统一动作入口：`game/actions.py`（PlayerAction / dispatch / available_actions）
- 统一 LLM 入口：`game/llm.py`
- 不破坏已有剧情和人物设定

---

## 3. 当前不做什么

- 不引入数据库、多用户系统、登录
- 不引入 React/Vue/任何前端 UI 框架
- 不做大模型替换（保持 MiniMax-M3）
- 不做复杂 AI Agent（当前 4 个 Agent 已够用）
- 不做地图/立绘/音效（除非单独出了 PLAN_氛围层）
- 不做 Phase 5+ 的复杂 SSE 多人联机

---

## 4. 模块边界

| 模块 | 能做什么 | 不能做什么 |
|------|---------|-----------|
| `game/llm.py` | 唯一 M3 调用入口 | 不允许其他模块直接调 MiniMax API |
| `game/actions.py` | 动作分发 + 可用动作生成 | 不写新的游戏规则，只调用 rules/agents |
| `game/rules.py` | 规则层（时段/阶段/调查/位置）| 不直接调 M3 |
| `game/agents.py` | NPC对话/决策/叙事/裁判 | 不写游戏流程控制 |
| `game/state.py` | 数据结构定义 | 不包含业务逻辑 |
| `game/persistence.py` | 存档/读档 | 不做版本迁移 |
| `main.py` | CLI 入口 | 只做命令解析 + dispatch 调用 |
| `web_api.py` | Web API 入口 | 命令解析统一走 dispatch |

---

## 5. Agent 使用边界

| Agent | 用途 | 禁止 |
|-------|------|------|
| `NPCDialogueAgent` | NPC 对话生成 | 不做决策、不做裁判 |
| `NPCDecisionAgent` | NPC 关键时刻决策（如林婉的证据销毁判断）| 不做结局裁判 |
| `NarratorAgent` | 氛围场景描写 | 不做游戏逻辑判断 |
| `DirectorAgent` | 结局裁判（judge）| 不做 NPC 决策、不做对话 |

**关键原则**：`NPCDecisionAgent.decide()` 只用于 NPC 自主决策；`DirectorAgent.judge()` 只用于结局判定。两者职责不得混用。

---

## 6. LLM 调用边界

- 所有 M3 调用必须经过 `game/llm.py`
- 每次调用必须记录：用途标签、输入 token、输出 token、耗时 → `logs/m3_calls.jsonl`
- 对话/叙事类：关闭 thinking（省 token）
- 决策/裁判类：可开启 thinking（要质量）
- Phase 1-3 克制用 M3，优先查表和 if/else

---

## 7. Web / CLI 入口边界

- **CLI**：`main.py` 负责命令解析，调用 `dispatch()`，打印 `ActionResult.events`
- **Web**：`web_api.py` 负责接收请求，调用 `dispatch()`，推送 SSE
- 两者共享同一套 `dispatch()`，规则必须一致
- 不允许在 `web_api.py` 里单独重写游戏规则（禁止重复逻辑）

---

## 8. 存档规则

- 存档文件路径：`saves/save.json`
- `save_game(world)` → 序列化 world 到 JSON
- `load_game()` → 从 JSON 反序列化，返回**新** WorldState 对象
- load 后 caller 必须**替换**自己的 world 引用，不允许在 dispatch 内部替换

---

## 9. 当前 P0 / P1 / P2 任务

### P0（阻断性，必须立即修）

（已清空，本轮 P0 全部修复）

### P1（重要，本轮已做）

- ✅ P1-1：添加 `docs/PROJECT_CONTROL.md`
- ✅ P1-2：补全 `docs/README.md` 配置/运行说明
- ✅ P1-3：创建 `scripts/smoke_test.py`

### P2（可做可不做）

- P2-1：移除 `web_api.py` 中不再使用的重复 import
- P2-2：考虑移除 `cmd_narrate` / `cmd_accuse` 等 main.py 中的冗余函数（已不再被主循环调用）
- P2-3：`map.html` 建议删除（依赖美术资源，方向错误）

---

## 10. 验收标准（每次修改后必做）

1. `python -m py_compile main.py web_main.py game/*.py` 不报错
2. `python scripts/smoke_test.py` 全通过
3. CLI 完整流程能跑通（对话→调查→推进→指认）
4. Web 能正常启动，`/api/action` 和 `/api/command` 行为一致
5. 不调用真实 M3 API 的测试必须能离线运行

---

## 11. 后续迭代规则

- 新增功能前先读 ARCHITECTURE.md 和 PLAN.md
- 每次迭代输出《执行报告》，包含：修改了什么、风险、下一轮建议
- 禁止一次性大提交，按模块分步提交
- API Key / Token 绝不进 Git

---

## 12. 项目纪律（禁止事项）

1. 不删除已有剧情文件（docs/）
2. 不删除 prompts/
3. 不删除 static 页面（map.html 除外）
4. 不引入数据库
5. 不改成 React/Vue/Next
6. 不替换 M3 调用方案
7. 不新增付费/登录/用户系统
8. 不把项目变成大而全游戏框架
9. 不提交 .env、logs/、__pycache__/、.venv/
10. 不为了测试真实调用 M3（smoke_test 禁止调用 M3）
