# PLAN_BUG修复.md — 逻辑/配置 BUG 修复施工单

> 给执行模型（M3）的施工文档。本次**只修 BUG，不碰 UI、不碰架构**。
> 这些是"内容/逻辑"问题：游戏目前跑起来是断的（证据拿不全、API 配置错）。
>
> **纪律**：按 Bug 编号顺序做，每个修完跑验收命令。不许顺手重构、不许加新功能。

---

## 0. 本次范围（必读）

只修以下 5 个已确认的 BUG。**与 `PLAN_UI重构.md` 是两条独立施工线，不要混做。**
如果两份文档都要做，**先做本文（让游戏跑通），再做 UI 重构**。

---

## 🔴 Bug 1：API 配置 anthropic / MiniMax 不匹配（最高优先级）

**现象**：`.env` 里 `ANTHROPIC_BASE_URL=https://api.anthropic.com`，但 `ANTHROPIC_MODEL=MiniMax-M2.7-highspeed`。
URL 指向 Anthropic 官方，模型名却是 MiniMax 的——调用会失败或行为错乱。

**要查清的事（先确认再改，不要猜）**：
1. 这个项目到底用哪家 API？看 `.env` 里的 `ANTHROPIC_API_KEY` 是 MiniMax 的 key 还是 Anthropic 的 key。
2. 若用 **MiniMax**：`ANTHROPIC_BASE_URL` 应为 MiniMax 的 Anthropic 兼容端点（参考 `.env.example` 里的 `https://api.minimaxi.com/anthropic`），`ANTHROPIC_MODEL` 用 MiniMax 实际模型名。
3. 若用 **Anthropic**：`ANTHROPIC_MODEL` 改成 Anthropic 合法模型名（如 claude-xxx），不能填 MiniMax-M2.7。

**修复后必须保证 `.env`、`.env.example`、`game/llm.py` 注释三处一致。**

**验收：**
```bash
python -c "
from game.llm import call_m3
print(call_m3(system='你是测试助手', user='只回复两个字：通过', purpose='selftest', max_tokens=20))
"
# 期望：能正常返回文本，不报连接/认证错误
```

---

## 🔴 Bug 2：3/5 关键证据无法获得

**现象**：`game/rules.py` 的 `KEY_EVIDENCE` 有 5 项，但 `INVESTIGATION_SPOTS` 只能调查出 2 项。
缺失：`异常的茶杯残留`、`借据`、`厨师阿福的证词`。玩家永远集不齐证据，游戏卡死在 investigation 阶段。

**按 `docs/SCENARIO.md`「关键证据物品」表，证据获取方式是**：

| 证据 | SCENARIO 定义的获取方式 |
|------|----------------------|
| 异常的茶杯残留 | 调查书房 / 陈伯主动给 |
| 新遗嘱草稿 | 说服陈伯 / 搜书房 ✅(已实现) |
| 林婉的病历笔记 | 搜林婉房间 ✅(已实现) |
| 借据 | 打开书房保险柜 |
| 厨师阿福的证词 | 安抚阿福后获得 |

**最小修复方案（Phase 不要做复杂交互，先让证据能拿到）**：
1. `异常的茶杯残留`：加进书房的 `INVESTIGATION_SPOTS["书房"]`（调查书房即可获得，和新遗嘱一起）。
2. `借据`：加进 `INVESTIGATION_SPOTS["书房"]`，或新增"打开保险柜"的简单逻辑（建议先简单：调查书房可得）。
3. `厨师阿福的证词`：实现"与阿福对话达到 N 次后，调查厨房可得"或"与阿福对话后自动进 inventory"。最简方案：玩家跟阿福对话过 → 调查厨房可获得证词。

> 注意：`KEY_EVIDENCE` 集合里的字符串和 `INVESTIGATION_SPOTS` 里的物品名**必须完全一致**（"厨师阿福的证词" vs "厨师的证词" 这种不一致会导致判定失败）。统一名字。

**验收：**
```bash
python -c "
import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from game.rules import INVESTIGATION_SPOTS, KEY_EVIDENCE
obtainable = set()
for items in INVESTIGATION_SPOTS.values(): obtainable.update(items)
missing = KEY_EVIDENCE - obtainable
print('仍无法获得的关键证据:', missing)
assert not missing, f'还有证据拿不到: {missing}'
print('OK 所有关键证据都有获取途径')
"
```

---

## 🟡 Bug 3：对话不检查玩家与 NPC 是否同地点

**现象**：玩家在「大厅」，可以 `跟 陈伯 说: xxx`，而陈伯此刻在「书房」。不合逻辑。

> ⚠️ 如果你**同时**在做 `PLAN_UI重构.md`，此 BUG 已在那份文档 Step 3 修复，**这里就跳过，不要重复改**。
> 如果只做本文档，则在 `main.py` 和 `web_api.py` 的对话处理里加校验：

用 `game.rules.npc_location_at(npc_name, world.clock)` 判断 NPC 当前位置，
若 != `world.player.location`，提示"{name}不在这里（TA在{地点}）"，不调用 M3。

**验收：**
```bash
python -c "
import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from game.scenario_data import build_initial_world
from game.rules import npc_location_at
w = build_initial_world()
print('玩家位置:', w.player.location)
print('陈伯位置(时段0):', npc_location_at('陈伯', 0))
# 二者不同，对话应被拒绝
"
```

---

## 🟡 Bug 4：confrontation → ending 缺"玩家发起指认"条件

**现象**：`check_phase_transition()` 里，confrontation 进 ending 只判断 `clock >= 8`。
但 `SCENARIO.md` 定义是「玩家发起指认 **OR** clock 到达清晨」。

**现状**：`web_api.py` 里指认逻辑其实已存在（`指认` 命令会直接 `judge` 并设 `phase="ending"`），
所以这个更多是**语义补齐**而非阻断 BUG。

**修复**：确认指认流程会正确地把 phase 推进到 ending 并产出结局；
`check_phase_transition` 的注释里写明"指认由 accuse 动作直接触发，不在此函数判定"。**不要重复实现两套结局逻辑。**

**验收**：跑一局，进入对峙阶段后指认任意 NPC，应能产出结局（verdict + summary）。

---

## 🟢 Bug 5：清理冗余 / 配置纪律

**现象（非阻断，最后做）**：
1. `docs/npc_dialogue.txt` 与 `prompts/npc_dialogue.txt` 重复（内容相近、标点不同）。
   → 确认 `prompts/` 下的是代码实际加载的版本（`agents.py` 读 `prompts/`），把 `docs/` 下那份删除或标注为草稿。
2. `requirements.txt` 含 `fastapi/uvicorn/pydantic`——这些 Web 才需要。
   → 当前 web_api 已在用，**保留**即可（不必为纪律删，删了 web 会崩）。仅在注释里分组标注"# Web (Phase 5)"。

**验收**：`pip install -r requirements.txt` 不报错；`agents.py` 加载 prompt 正常。

---

## 本次完成的判定（交付给设计师确认）

```
BUG修复 完成 ✅
- Bug1: API 配置已统一为 <MiniMax 或 Anthropic>，自测调用通过
- Bug2: 5 项关键证据均有获取途径
- Bug3: 对话已校验同地点
- Bug4: 指认结局流程确认正常
- Bug5: 冗余文件已清理
现在可以完整跑通一局：对话→调查集齐证据→对峙→指认→结局
```

---

## ❌ 本次明确不做

- 不做 UI / 界面（那是 `PLAN_UI重构.md`）。
- 不重构 `dispatch` / 不改命令解析方式（那也是 UI 重构的事）。
- 不新增 NPC、不改秘密、不改 WorldState 字段。
- 不"顺便优化"无关代码。
</content>
