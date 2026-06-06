# DEVELOPMENT_WORKFLOW.md — 分层验证策略

> 本文档定义不同类型改动的验证范围，避免小修复跑全量测试，提升开发迭代效率。

---

## 1. 必做轻量检查

每轮任务开始前至少执行：

```bash
git pull
git status
git log --oneline --decorate -5
```

目的：

- 确认当前分支
- 确认远端最新提交
- 确认工作区是否干净
- 避免覆盖未提交内容

---

## 2. 纯前端小修

**适用范围：**

- `static/index.html` 中的 CSS 小修
- `static/index.html` 中的 JS 小修
- 首屏样式
- 按钮绑定
- 弹层显示
- loading 状态
- 非主流程 UI 调整

**验证要求：**

- 不默认跑完整 E2E
- 不默认跑 `validate_assets`
- 优先浏览器手动验证
- Console 必须无 JS error
- 对应入口必须可点击
- 必要时执行一次移动 / 调查 / 盘问

**可选验证：**

```bash
python scripts/smoke_test.py
```

---

## 3. 后端或状态机修改

**适用范围：**

- `game/*.py`
- `web_main.py`
- `main.py`
- `/api/action`
- `available_actions`
- phase transition
- evidence / accuse / ending
- `WorldState`

**验证要求：**

```bash
python -m py_compile main.py web_main.py game/*.py
python scripts/smoke_test.py
```

如果影响主流程，再追加：

```bash
python scripts/e2e_main_gameplay.py
```

---

## 4. 主流程修改

**适用范围：**

- 进入游戏
- 移动
- 调查
- 盘问
- 推进时段
- 进入对峙
- 指认凶手
- 结局展示

**验证要求：**

```bash
python scripts/e2e_main_gameplay.py
```

并补充手动验证：

- 至少从 `/` 页面确认主入口可用

---

## 5. 资产修改

**适用范围：**

- `static/assets`
- `manifest.json`
- `ASSET_CREDITS.json`
- 图片路径
- 角色立绘
- 场景图
- 证据图
- 结局图

**验证要求：**

```bash
python scripts/validate_assets.py
```

必要时浏览器确认图片显示。

---

## 6. 纯文档修改

**适用范围：**

- README
- `docs/*`
- 任务说明
- 报告模板
- 规划文档

**验证要求：**

- 只检查 `git diff`
- 不跑自动测试
- 不跑 E2E
- 不跑 `validate_assets`

---

## 7. 禁止默认全量测试

明确规则：

- **不要因为测试脚本存在，就每轮默认执行完整 E2E。**
- **不要让 accuse / LLM 路径成为所有任务的默认验证。**
- **不要为了 CSS、文案、按钮绑定小修跑完整主流程。**
- **只有影响主流程状态机或阶段性稳定收口时，才跑完整 E2E。**

---

## 8. 验证层级速查表

| 改动类型 | 必做验证 | 选做验证 | 禁止默认 |
|---|---|---|---|
| 前端 CSS/JS 小修 | 浏览器手动验证 | `smoke_test.py` | 完整 E2E |
| 后端状态机修改 | `py_compile` + `smoke_test.py` | E2E（影响主流程时） | - |
| 主流程修改 | E2E + 手动验证 | - | - |
| 资产/图片修改 | `validate_assets.py` | 浏览器确认 | E2E |
| 纯文档修改 | `git diff` | - | 任何自动测试 |
