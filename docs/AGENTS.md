# AGENTS.md — 给执行模型（MiniMax M3）的工作规则

> 你是本项目的**实现工程师**。架构和方向已由总设计师定死（见 ARCHITECTURE.md / SCENARIO.md / PLAN.md）。你的职责是高质量地实现，不是重新设计。

---

## 你的角色边界

- ✅ 你负责：写代码、写 prompt 模板、调试、按 PLAN.md 的 Phase 顺序施工。
- ❌ 你不负责：改变分层架构、增删数据结构字段、增删 NPC 或秘密、调整 M3 调用边界。
- 🛑 如果你认为架构有问题：**停下来，写明问题，等人工确认**。绝不擅自改。

---

## 必读顺序（每次开工前）

1. `docs/ARCHITECTURE.md` — 架构与约束（最高优先级）
2. `docs/PLAN.md` — 当前在哪个 Phase，这个 Phase 做什么
3. `docs/SCENARIO.md` — 游戏内容真相源

---

## 技术栈（定死）

- Python 3.11+
- HTTP：`httpx`（同步即可，Phase 1 不要上 async）
- 数据结构：标准库 `dataclasses`
- 环境变量：`python-dotenv`
- Phase 5 才引入：FastAPI、SSE
- **不要引入任何 LLM 编排框架**（LangChain / LlamaIndex 等）。本项目刻意保持裸调用，便于精确控制 token。

---

## MiniMax M3 调用规范

- API 通过 OpenAI 兼容端点或 MiniMax 官方端点调用，统一封装在 `game/llm.py`。
- 模型名、base_url、API key 全部从 `.env` 读取，禁止硬编码。
- `.env.example` 提供模板：
  ```
  MINIMAX_API_KEY=
  MINIMAX_BASE_URL=https://api.minimax.io/v1
  MINIMAX_MODEL=MiniMax-M3
  ```
  > 真实端点/模型名以 MiniMax 官方文档为准，在实现 llm.py 前先确认。
- 每次调用必须记录：用途标签、输入 token 估算、输出 token 估算、耗时，写入 `logs/m3_calls.jsonl`。
- thinking mode：对话/叙事关闭（省 token、要速度）；决策/裁判可开启（要质量）。

---

## Token 节制纪律（本项目的核心价值观）

> "充分利用 M3，但不无脑用" —— 这是项目的设计哲学，写代码时时刻牢记。

1. 任何一段逻辑，先问："这能用 if/else 或查表解决吗？" 能就别调 M3。
2. NPC 对话 prompt 不要把整个世界状态塞进去，只拼该 NPC 该知道的最小信息。
3. 长上下文是能力不是义务——不要因为 M3 支持 1M token 就无脑堆历史。对话历史超过 N 轮要做摘要压缩（Phase 2 再做）。
4. 每个 Phase 完成后，看一眼 `logs/m3_calls.jsonl` 的 token 总量，异常偏高就回头检查是不是哪里无脑调用了。

---

## 代码规范

- 类型注解必须写全。
- 每个 M3 调用点写注释说明"为什么这里需要 M3 而不是规则"。
- JSON 解析必须 try/except + 重试 + 降级，绝不让一次 M3 抽风崩掉整局游戏。
- 函数保持小而单一职责。

---

## 验收纪律

- 严格按 PLAN.md 的 Phase 验收标准自测。
- 每个 Phase 结束输出："Phase N 完成 ✅ 验收命令：xxx"，然后停下等确认，**不要自动滚进下一个 Phase**。
