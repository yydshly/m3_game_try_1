# 孤岛晚宴 — AI 多 Agent 文字推理游戏

一个以用户 UI 操作为主入口，由 MiniMax-M3 参与角色演绎、剧情推动、关键决策和结局裁判的 AI 互动推理游戏原型。

## 当前阶段

MVP 验证后期 / 架构稳定期。游戏核心闭环已通，可完整跑通：对话 → 调查集证 → 对峙指认 → 结局。

## 核心玩法

玩家是私人侦探，被困在暴风雨中的孤岛别墅。岛主周慎之死于书房，茶杯里有异常。天亮前找出真凶。

通过与 NPC 对话、调查现场、收集证据，最终在对峙阶段指认凶手。证据链是否充分影响结局。

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

如果 8000 端口被占用，修改 `config/server.toml` 中的 `port` 即可：

```toml
port = 8001
```

然后重新启动服务即可生效。

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

## Web UI 现状与目标

Web UI 已从"调试页面"升级为**沉浸式游戏主界面原型**：

- **顶部 Header**：时段 + 阶段徽章 + 地点 + 证据数 + 对话数
- **时间线栏**：时段节点进度 + 阶段进程 + 事件/证据/对话统计
- **左侧场景舞台**：地点主题渐变背景 + 左侧彩色竖线区分场景氛围
- **左侧 NPC 卡片**：在场高亮 / 已对话标记 / 警觉度进度条 / 字母头像 + 颜色区分角色
- **中央剧情区**：旁白斜体 / NPC气泡 / 系统小字 / 调查卡片，消息类型视觉分层
- **右侧证据板**：证据卡片（图标+来源+指向+重要性标签），空状态显示引导文案
- **右侧事件日志**：公共事件记录面板
- **底部动作栏**：按移动/盘问/调查/推进/指认分组，按钮 loading 防护

详见 [`docs/UI_REDESIGN.md`](docs/UI_REDESIGN.md)。

## 当前已知限制

- 存档为单文件（`saves/save.json`），不支持多存档槽位
- NPC 决策（NPCDecisionAgent）触发依赖证据暴露条件，非随时可触发
- 林婉作为真凶，其"销毁证据"行为是规则层预设，非 AI 自由决策
- 当前只支持《孤岛晚宴》固定剧本

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
