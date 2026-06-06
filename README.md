# 孤岛晚宴 — AI 多 Agent 文字推理游戏

一个以用户 UI 操作为主入口，由 MiniMax-M3 参与角色演绎、剧情推动、关键决策和结局裁判的 AI 互动推理游戏原型。

## 当前阶段

可玩 MVP 闭环验证阶段。

主流程已具备：进入游戏、侦探助手引导、移动、调查、盘问、连续追问、证据收集、推进阶段、对峙指认、结局展示。

当前仍是固定剧本原型，不是多剧本平台。

## 核心玩法

玩家是私人侦探，被困在暴风雨中的孤岛别墅。岛主周慎之死于书房，茶杯里有异常。天亮前找出真凶。

通过与 NPC 对话、调查现场、收集证据，最终在对峙阶段指认凶手。证据链是否充分影响结局。

## 推荐游玩路径

1. 启动 Web 服务并打开 `/`
2. 点击"开始调查"
3. 优先跟随"侦探助手"的建议行动
4. 晚宴阶段：盘问至少 5 名 NPC
5. 使用"推进时段"进入调查阶段
6. 调查书房、厨房、林婉房间等地点收集证据
7. 收集足够证据后进入对峙阶段
8. 指认嫌疑人，查看结局

当前固定剧本中，侦探助手会尝试带玩家完成一局。

## 技术栈

- Python 3.11+，httpx，FastAPI（Web），标准库 dataclasses
- LLM：MiniMax-M3（仅通过 `game/llm.py` 调用）
- 前端：原生 HTML/CSS/JS，无任何 UI 框架

## MiniMax-M3 的作用

| 用途 | Agent |
|------|-------|
| NPC 对话生成 | `NPCDialogueAgent` |
| 场景旁白 | `NarratorAgent` |
| NPC 关键决策 | `NPCDecisionAgent` |
| 结局裁判 | `DirectorAgent` |

## 环境变量配置

```bash
cp .env.example .env
# 填入 ANTHROPIC_API_KEY
```

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M3
```

**⚠️ 安全提醒：不要提交 .env，不要提交 logs/，不要在代码里硬编码 API Key。**

## 快速启动（推荐）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入：

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_BASE_URL=https://api.minimaxi.com/anthropic
ANTHROPIC_MODEL=MiniMax-M3
```

### 3. 启动 Web 游戏

推荐使用启动脚本（自动检测端口、打开浏览器）：

```bash
python scripts/start_dev_server.py
```

启动后浏览器会自动打开 `http://localhost:8000`（默认）。

常用参数：

```bash
python scripts/start_dev_server.py --no-open       # 不自动打开浏览器
python scripts/start_dev_server.py --port 8001     # 指定端口
python scripts/start_dev_server.py --stop-existing # 端口被占用时先停旧进程
python scripts/start_dev_server.py --reload        # 启用代码热重载
```

#### Windows 一键启动

双击运行或从命令行运行：

```bat
scripts\start_web.bat
```

停止服务：

```bat
scripts\stop_web.bat
```

### 4. 页面入口

- 主游戏入口：`http://localhost:8000/`（端口以 `config/server.toml` 为准）
- 地图实验页：`http://localhost:8000/map`（Canvas 早期实验，仅供验证）

### 5. Web 服务配置

默认配置文件：`config/server.toml`

```toml
[server]
host = "127.0.0.1"
port = 8000
open_host = "localhost"
auto_open = true
```

#### 修改默认端口

编辑：

```text
config/server.toml
```

例如：

```toml
[server]
host = "127.0.0.1"
port = 8001
open_host = "localhost"
auto_open = true
```

然后执行：

```bash
python scripts/start_dev_server.py
```

访问：

```text
http://localhost:8001
```

#### 临时覆盖端口

```bash
M3_GAME_PORT=8001 python scripts/start_dev_server.py
```

PowerShell：

```powershell
$env:M3_GAME_PORT=8001
python scripts/start_dev_server.py
```

**配置优先级**：

```
CLI 参数 > 环境变量 > config/server.toml > 内置默认值
```

**环境变量覆盖**：

```bash
M3_GAME_HOST=0.0.0.0          # uvicorn 监听地址
M3_GAME_PORT=8001             # uvicorn 监听端口
M3_GAME_OPEN_HOST=localhost    # 浏览器打开使用的 host
M3_GAME_AUTO_OPEN=false        # 禁用自动打开浏览器
M3_GAME_BASE_URL=http://...    # E2E/测试脚本使用的基址
```

Windows PowerShell：

```powershell
$env:M3_GAME_PORT=8001
python scripts/start_dev_server.py
```

### 手动启动

仍可使用原始方式：

```bash
python web_main.py
# 浏览器打开 http://localhost:8000（以 config/server.toml 为准）
```

或 CLI 入口（无 Web UI，纯文字）：

```bash
python main.py
```

## 冒烟测试

```bash
python scripts/smoke_test.py
```

## 常用脚本

| 脚本 | 作用 | 常用命令 |
|---|---|---|
| `scripts/start_dev_server.py` | 启动 Web 服务 | `python scripts/start_dev_server.py` |
| `scripts/stop_dev_server.py` | 停止占用配置端口的服务 | `python scripts/stop_dev_server.py` |
| `scripts/start_web.bat` | Windows 一键启动 | `scripts\start_web.bat` |
| `scripts/stop_web.bat` | Windows 一键停止 | `scripts\stop_web.bat` |
| `scripts/smoke_test.py` | 后端规则与 API 冒烟测试 | `python scripts/smoke_test.py` |
| `scripts/e2e_main_gameplay.py` | 主流程 HTTP E2E | `python scripts/e2e_main_gameplay.py` |
| `scripts/validate_assets.py` | 验证视觉资产 manifest | `python scripts/validate_assets.py` |

## 验证方式

轻量规则测试：

```bash
python scripts/smoke_test.py
```

完整 HTTP 主流程测试：

```bash
python scripts/e2e_main_gameplay.py
```

资产验证：

```bash
python scripts/validate_assets.py
```

一般规则：

- 只改文档：不需要跑测试
- 改后端规则：跑 `py_compile` + `smoke_test`
- 改主流程：跑 E2E
- 改资产：跑 `validate_assets`

## 项目文档入口

| 文档 | 作用 |
|------|------|
| `docs/README.md` | 项目简介和技术细节 |
| `docs/PROJECT_CONTROL.md` | 项目管控规则、AI Agent 纪律 |
| `docs/PRODUCT_GOAL.md` | 产品目标、M3 定位、MVP 边界 |
| `docs/UI_DRIVEN_ARCHITECTURE.md` | UI 驱动架构、数据流、API 边界 |
| `docs/UI_REDESIGN.md` | Web UI 重构说明、页面结构、区域说明 |
| `docs/SCENARIO.md` | 场景与 NPC 设定（真相源）|
| `docs/ARCHITECTURE.md` | 系统架构、数据结构、约束 |

## Web UI 现状

当前 `/` 主入口采用三栏结构：

- **左侧视觉舞台**：展示当前地点、场景背景、在场 NPC 立绘/头像
- **中间主叙事区**：展示案情简报、当前场景说明、玩家操作记录、盘问对话、连续追问输入区、侦探助手建议
- **右侧行动与案件区**：展示当前状态、行动面板、案件进展、持有证据、公共事件
- **顶部状态栏**：展示时间、阶段、位置、证据数、盘问数
- **侦探助手**：基于当前 WorldState 给出下一步建议，不调用大模型，所有建议动作仍通过 `/api/action` 执行

`/map` 是早期 Canvas 地图实验页，不代表当前主体验。

## 常见问题排查

### 端口被占用

```bash
python scripts/stop_dev_server.py
```

或修改：

```text
config/server.toml
```

把 `port = 8000` 改成其他端口。

### 页面打不开

确认服务已启动：

```bash
python scripts/start_dev_server.py
```

确认访问地址与 `config/server.toml` 中的 `port` 一致。

### 修改前端后页面没变化

浏览器强制刷新：

```text
Ctrl + F5
```

### NPC 不回复或一直显示"正在回忆"

检查浏览器 Network 中 `/api/action` 是否返回 `events`，其中应包含：

```json
{"kind": "npc", "speaker": "...", "text": "..."}
```

如果 `/api/action` 一直 pending，通常是 LLM 调用慢或外部接口不可用。

### MiniMax / API Key 未配置

检查 `.env`：

```env
ANTHROPIC_API_KEY=...
ANTHROPIC_BASE_URL=...
ANTHROPIC_MODEL=MiniMax-M3
```

不要把 `.env` 提交到 Git。

## 当前已知限制

- 当前只支持《孤岛晚宴》固定剧本
- 侦探助手是规则引导，不调用大模型
- 对峙阶段当前仍偏固定剧本逻辑，后续可根据证据动态推荐嫌疑人
- NPC 对话依赖 MiniMax-M3，接口慢或失败时会影响盘问体验
- 存档为单文件，不支持多存档槽位
- `/map` 是早期实验页，不代表最终 UI
- 当前没有账号系统、数据库、多剧本编辑器

## 视觉资产管线

游戏已建立真实视觉资产接入管线，真实图片放入 `static/assets/` 目录，manifest 控制资源映射，缺图 fallback 到 placeholder。

- 资源目录：`static/assets/`（scenes / characters / evidence / endings / placeholders）
- 资源索引：`static/assets/manifest.json`
- 占位图：SVG 格式，缺图时自动 fallback，不影响页面功能
- 资源验证：`python scripts/validate_assets.py`
- 详细设计：参见 [`docs/ASSET_PIPELINE.md`](docs/ASSET_PIPELINE.md)
- 生图提示词：参见 [`docs/IMAGE_PROMPTS.md`](docs/IMAGE_PROMPTS.md)

**结局画面**使用结构化 `ending_key` 映射视觉资源，不再依赖 verdict 文案匹配：
- `culprit_caught` → 真凶落网（正确指认）
- `wrong_accuse` → 错误指认（错误指认）
- `culprit_escape` → 真凶逃脱（时间耗尽）
- 旧版 `verdict` 关键词匹配仅作兼容 fallback

## 禁止事项

- 不要提交 `.env`、logs/、API Key 到 Git
- 不要引入数据库、账号系统、支付
- 不要引入 React/Vue/任何前端 UI 框架
- 不要替换 MiniMax-M3 调用方案

## 下一阶段规划

优先级建议：

1. 侦探助手带路完整人工通关验收
2. 嫌疑人线索板：展示每个嫌疑人与证据的关系
3. 证据指向关系：解释每条证据为什么重要
4. 结局前推理确认面板：指认前展示当前证据链
5. 对峙阶段动态推荐：不再硬编码嫌疑人，而是根据证据计算嫌疑程度
6. 固定剧本抽象：为后续多剧本做数据结构准备
