# 《孤岛晚宴》— AI 多 Agent 推理游戏

一个用 MiniMax M3 驱动的多 Agent 文字推理游戏。6 个 NPC 各是独立 Agent，有自己的目标和秘密，剧情是博弈的涌现结果。

## 给执行模型的开工指令（复制给 M3 / Claude Code）

> 阅读 `docs/AGENTS.md`、`docs/ARCHITECTURE.md`、`docs/PLAN.md`、`docs/SCENARIO.md`。
> 严格按 `docs/PLAN.md` 的 **Phase 1** 施工，只做 Phase 1 列出的内容，不要超前。
> 完成后运行 Phase 1 验收命令，输出"Phase 1 完成"并停下等确认。

## 文档导航

| 文件 | 作用 | 谁能改 |
|------|------|--------|
| `docs/ARCHITECTURE.md` | 系统架构、数据结构、M3 调用边界 | 仅总设计师 |
| `docs/SCENARIO.md` | 场景与 6 个 NPC 设定（内容真相源）| 仅总设计师 |
| `docs/PLAN.md` | 分阶段施工计划 | 仅总设计师 |
| `docs/AGENTS.md` | 执行模型的工作规则 | 仅总设计师 |
| `prompts/*.txt` | M3 prompt 模板 | 执行模型可实现/调优 |
| `game/*.py` | 代码实现 | 执行模型 |

## 设计哲学

充分利用 M3，但不无脑用它。M3 只出现在需要"判断力和语言生成"的地方（对话、决策、裁判、叙事），其余一律用确定性规则。详见 ARCHITECTURE.md 第 5 节。
