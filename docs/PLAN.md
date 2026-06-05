# PLAN.md —《孤岛晚宴》分阶段执行计划

> 给执行模型（M3）的施工顺序。**必须按 Phase 顺序执行，每个 Phase 跑通验收后才进入下一个。** 不许跳跃、不许提前做后面 Phase 的功能。

> 总设计师（架构）已定，你（M3）只负责实现。每完成一个任务，运行验收命令确认通过。

---

## ⭐ Phase 1：最小可运行（目标：今天跑通）

**验收标准：在命令行里，玩家能和 2 个 NPC 对话，NPC 基于各自秘密给出合理回应，对话被记入各自的私有记忆。**

只做这些，不要多做：

1. **`game/state.py`** — 实现 ARCHITECTURE.md 第 4 节的全部 dataclass。
2. **`game/llm.py`** — 封装 MiniMax M3 调用。一个函数 `call_m3(system: str, user: str) -> str`，带重试和 token 日志。从 `.env` 读 `MINIMAX_API_KEY`。
3. **`game/scenario_data.py`** — 把 SCENARIO.md 的 6 个 NPC 转成初始 `WorldState`（Phase 1 先只激活管家陈伯和侄女苏苏 2 人即可）。
4. **`prompts/npc_dialogue.txt`** — NPC 对话 prompt 模板（见下方"Prompt 模板规范"）。
5. **`game/agents.py`** — 只实现 `NPCDialogueAgent`。
6. **`main.py`** — 命令行循环：玩家输入 `跟 陈伯 说: 你昨晚在哪`，系统调用对应 NPC 的 DialogueAgent，打印回应，更新该 NPC 的 memory。

**验收命令：**
```bash
python main.py
# 然后输入：跟 陈伯 说: 周先生昨晚看起来怎么样？
# 期望：陈伯以忠诚、留三分的口吻回应，且不会主动说出"私生子"等核心秘密
```

❌ Phase 1 **不做**：NPC 决策、主控裁判、叙事、阶段推进、Web 界面、存档。

---

## Phase 2：完整对话 + 叙事 + 存档

1. 激活全部 6 个 NPC。
2. 实现 `NarratorAgent`（每个时段开始生成氛围描写）。
3. 实现 `rules.py` 的时段推进（纯计数器，不调 M3）。
4. 实现存档：`WorldState` ←→ JSON 文件。
5. 玩家可以"移动到某地点""调查物品"（规则层，获得 inventory）。

**验收：完整玩一局对话流程，退出后能存档、重进能续上。**

---

## Phase 3：多 Agent 博弈核心

1. 实现 `NPCDecisionAgent`：林婉在"病历可能暴露"时触发销毁证据。
2. 实现 `rules.py` 的触发条件判断（查 revealed_to / inventory / clock）。
3. NPC 之间的关系变化会影响后续对话。

**验收：玩家把"林婉知道绝症"的线索透露给别人后，林婉的 DecisionAgent 被触发并采取行动，且该行动产生一条公共/私有事件。**

---

## Phase 4：主控裁判 + 结局

1. 实现 `DirectorAgent`：阶段推进判断、结局生成。
2. 实现 `confrontation` 指认机制和多种结局（指认正确/错误/真凶逃脱）。

**验收：能完整通关，且至少跑出 2 种不同结局。**

---

## Phase 5（可选，商业化前）：FastAPI + SSE + 多用户

复用 Video Radar 的后端经验。此阶段才考虑 UI 和部署。

---

## Prompt 模板规范（所有 Phase 通用）

- Prompt 模板放在 `prompts/*.txt`，用 `{变量名}` 占位，代码层用 `.format()` 填充。**禁止把 prompt 硬编码在 .py 里。**
- 每个 NPC 对话 prompt 必须包含且**仅包含**该 NPC 的 secrets，绝不能拼入其他 NPC 的秘密或全局真相。
- 要求 JSON 输出的 prompt，末尾必须明确："只返回 JSON，不要任何解释、不要 markdown 代码块。"

---

## 给执行模型的纪律

1. 每个 Phase 完成后**停下来**，输出"Phase N 完成，验收命令：xxx"，等人工确认。
2. 遇到架构层面的疑问，**停下来问**，不要自己改 ARCHITECTURE.md 定义的结构。
3. 不要为了"功能更全"提前实现后续 Phase 的东西——过度实现是本项目最大的风险。
