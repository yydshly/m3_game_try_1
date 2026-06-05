# PLAN_文字UI.md — 纯文字选项式游戏界面

> 给执行模型（M3）的施工文档。本次做**界面**，但**零美术**——不画图、不画地图、不放立绘。
> 游戏感全部来自：选项按钮、氛围排版、配色、打字节奏、转场。对标 Disco Elysium / 80 Days 的文字界面。
>
> **前置依赖**：必须先完成 `PLAN_UI重构.md`（已提供 `available_actions` 和 `/api/action`）。没完成不要做本文。
>
> **纪律**：按 Step 顺序做，每步出可见效果给设计师看。不许加图片/canvas/外部 UI 框架。

---

## 0. 设计目标（必读，决定一切）

把现在"聊天框 + 打字命令"的 `index.html`，改造成**点击式文字冒险界面**：

- 玩家**不再打字输命令**，而是**点屏幕上的选项按钮**（按钮来自后端 `available_actions`）。
- 唯一需要打字的地方：和 NPC 对话时输入要问的话（可选，也可做成预设问题按钮）。
- 整个屏幕像一本"会呼吸的悬疑小说"：暗色调、衬线/等宽混排、文字逐字浮现、场景切换有淡入。

**技术约束**：纯原生 HTML/CSS/JS（不引入 React/Vue）。复用现有 `static/index.html` 的配色变量，别推倒重来。

---

## 1. 界面布局（三段式，定死）

```
┌─────────────────────────────────────────────┐
│  顶栏: 标题 · 时段 · 阶段徽章 · 当前位置        │  ← 已有，微调
├─────────────────────────────────────────────┤
│                                               │
│   叙事/对话流（主区，占大头）                   │  ← 已有 logPanel，保留
│   - 旁白：斜体、左边竖线、蓝灰色                 │
│   - NPC 说话：名字 + 气泡                       │
│   - 玩家：右对齐气泡                            │
│   - 系统：暗色小字                              │
│                                               │
├─────────────────────────────────────────────┤
│  动作区（核心新增）：                           │
│  [盘问 陈伯] [前往 书房] [调查 大厅] [推进时段] │  ← 按钮来自 available_actions
└─────────────────────────────────────────────┘
```

右侧证据/状态侧栏：**保留现有的**，无需大改。

---

## ⭐ Step 1：动作按钮区（替换打字输入）

把底部的"打字输入框 + 发送按钮"换成**动态按钮区**。

1. 每次收到后端响应（`/api/action` 或 `/api/session` 返回里带 `available_actions`），
   清空动作区，按列表渲染按钮：
   ```js
   function renderActions(actions) {
     const bar = document.getElementById('actionBar');
     bar.innerHTML = '';
     for (const a of actions) {
       const btn = document.createElement('button');
       btn.className = 'action-btn' + (a.enabled ? '' : ' disabled');
       btn.textContent = a.label;
       btn.disabled = !a.enabled;
       if (!a.enabled && a.hint) btn.title = a.hint;
       btn.onclick = () => doAction(a);   // 见 Step 2
       bar.appendChild(btn);
     }
   }
   ```
2. 按钮分组显示（视觉清晰）：对话类一组、移动类一组、其它（调查/推进/指认）一组。用小标题或分隔。
3. 样式：复用 `--gold` / `--surface2` / `--border`。hover 高亮，disabled 置灰。

**验收**：开局界面底部出现一排可点按钮（不再是输入框），灰掉的"指认"按钮 hover 显示"需先进入对峙阶段"。

---

## ⭐ Step 2：点击动作 → 调结构化 API

```js
async function doAction(a) {
  // talk 需要玩家输入要问的话；其余动作直接执行
  let text = null;
  if (a.type === 'talk') {
    text = await askQuestion(a.target);   // 见 Step 3
    if (text === null) return;            // 玩家取消
  }
  const r = await fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sessionId, type: a.type, target: a.target, text})
  });
  const d = await r.json();
  if (d.state) {
    updateState(d.state);
    renderActions(d.state.available_actions || []);  // 刷新按钮
  }
}
```

叙事/对话内容仍走 **SSE**（已有 `streamNarrator` / `streamNPCReply`），本步不动 SSE。

**验收**：点"前往 书房"→ 顶栏位置变书房，按钮区刷新出现"调查 书房"；点"调查 书房"→ 叙事区出现获得证据的消息，右侧证据栏 +1。

---

## ⭐ Step 3：对话输入（轻量弹层）

点"盘问 陈伯"时，弹出一个小输入层（不是浏览器原生 prompt，要好看）：

- 半透明遮罩 + 居中卡片，标题"盘问 陈伯"。
- 一个输入框 + "发问"/"取消"两个按钮。
- **进阶（可选，强烈建议）**：在输入框上方放 3-4 个**预设问题按钮**（如"你昨晚在哪？""茶杯的事你知道吗？"），点了直接填入。这一步让玩家"开口"零门槛，是游戏感的关键。

```js
function askQuestion(npcName) {
  return new Promise(resolve => { /* 显示弹层，确认 resolve(text)，取消 resolve(null) */ });
}
```

**验收**：点"盘问 陈伯"弹出输入层，输入问题→发问→陈伯气泡流式回复；点取消则什么都不发生。

---

## ⭐ Step 4：氛围打磨（让它"像游戏"）

零成本，纯 CSS/JS：

1. **场景转场**：移动到新地点时，主区淡出→淡入，顶部短暂显示大字"书房 · 凌晨3点"，1.5 秒后淡去。
2. **打字机节奏**：旁白逐字、NPC 逐字（已有 `streamText`，确认手感：每字 40-70ms，标点处停顿更久）。
3. **进入新阶段的仪式感**：dinner→investigation 等阶段切换时，全屏压暗 + 居中大字提示阶段名，再继续。
4. **配色情绪**：不同阶段可微调背景色温（晚宴偏暖金、对峙偏冷红）。用 `body` 上加 class 控制即可。

**验收**：移动、对话、阶段推进都有视觉反馈，整体"有氛围"，不再像聊天软件。

---

## ⭐ Step 5：开局与结局页

1. **开局**：保留现有 onboarding，但把命令说明换成"点击下方选项进行调查"（因为不再打字）。
2. **结局**：保留现有 gameover 弹层；结局文案用打字机效果浮现，增加"侦探小说揭晓"的仪式感。

**验收**：从开局到结局完整跑一局，全程只靠点击（除对话输入），体验连贯。

---

## 本次完成的判定（交付给设计师）

```
纯文字UI 完成 ✅
- 底部为动态动作按钮区，不再需要打字输命令
- 点击动作走 /api/action，按钮随状态刷新
- 对话有弹层输入（含预设问题）
- 场景转场/打字节奏/阶段仪式感已加
- 全程点击可通关
请设计师试玩，决定是否进入"音效氛围层"或"AI立绘"。
```

---

## ❌ 本次明确不做

- 不引入 React/Vue/任何前端框架（保持原生）。
- 不画任何图：不放背景图、不放立绘、不用 canvas、不画地图。
- 不加音效（那是下一份 `PLAN_氛围层.md`）。
- 不改后端逻辑/规则（后端只在 `_world_to_dict` 里带上 `available_actions`，那已在 UI 重构里做了）。
- 不动 `map.html`（建议直接删除）。
```
