# 《孤岛晚宴》— AI 多 Agent 文字推理游戏

一个用 MiniMax M3 驱动的多 Agent 文字推理游戏。6 个 NPC 各是独立 Agent，有自己的目标和秘密，剧情是博弈的涌现结果。

## 项目当前阶段

MVP 验证后期 / 架构稳定期。游戏可完整跑通：对话→调查→对峙→结局。

## 核心玩法

玩家是私人侦探，被困在暴风雨中的孤岛别墅。岛主周慎之死于书房，茶杯里有异常。天亮前找出真凶。

通过与 NPC 对话、调查现场、收集证据，最终在对峙阶段指认凶手。证据链是否充分影响结局。

## 技术栈

- Python 3.11+，httpx，FastAPI（Web），标准库 dataclasses
- LLM：MiniMax-M3（仅通过 `game/llm.py` 调用）
- 前端：原生 HTML/CSS/JS，无任何 UI 框架

## 环境变量配置

复制 `.env.example` 为 `.env`，填入真实 API Key：

```bash
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY
```

`.env` 内容：
```
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M3
```

**⚠️ 禁止将 `.env` 提交到 Git。**

## CLI 运行

```bash
pip install -r requirements.txt
python main.py
```

## Web 运行

```bash
pip install -r requirements.txt
python web_main.py
# 浏览器打开 http://localhost:8000
```

## 常用命令（CLI）

| 命令 | 说明 |
|------|------|
| `跟 <NPC> 说: <话>` | 与 NPC 对话 |
| `移动到 <地点>` | 前往某地 |
| `调查` | 在当前地点搜集证据 |
| `推进时段` | 时间推进，播报场景 |
| `查看状态` | 显示当前状态 |
| `存档` / `读档` | 保存/加载进度 |
| `指认 <NPC>` | 在对峙阶段指认凶手 |
| `退出` | 退出游戏 |

## 架构

```
main.py / web_main.py
        ↓
game/web_api.py
        ↓
game/actions.py  ← 统一动作入口（PlayerAction / dispatch / available_actions）
        ↓
game/rules.py  +  game/agents.py  +  game/state.py
        ↓
game/llm.py  →  MiniMax-M3
```

## 关键模块

| 模块 | 职责 |
|------|------|
| `game/state.py` | WorldState / PlayerState / NPCState 数据结构 |
| `game/rules.py` | 规则层：时段/阶段推进、调查、NPC 位置 |
| `game/agents.py` | Agent 层：NPCDialogueAgent / NPCDecisionAgent / NarratorAgent / DirectorAgent |
| `game/actions.py` | 统一动作层：PlayerAction / dispatch / available_actions |
| `game/llm.py` | 唯一 M3 调用入口 |
| `game/persistence.py` | 存档/读档 |
| `game/scenario_data.py` | 初始世界构建 |

## 当前已知限制

- 存档为单文件（`saves/save.json`），不支持多存档槽位
- NPC 决策（NPCDecisionAgent）触发依赖证据暴露条件，非随时可触发
- 林婉作为真凶，其"销毁证据"行为是规则层预设，非 AI 自由决策

## 后续计划

- 音效/氛围层（`PLAN_氛围层.md`）
- AI 立绘（可选，非必须）
- 对话历史摘要压缩（Phase 2）

---

**⚠️ 安全提醒**
- 不要提交 `.env`、API Key、Token 到 Git
- 不要提交 `logs/` 目录
- 不要在代码里硬编码任何密钥
