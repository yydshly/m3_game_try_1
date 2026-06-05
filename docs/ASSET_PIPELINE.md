# ASSET_PIPELINE.md — 视觉资产管线设计

## 1. 为什么需要真实视觉资产

当前 UI 使用 CSS 模拟（颜色块、字母头像），已验证了布局和交互逻辑。

当产品方向从"MVP 功能验证"转向"沉浸式体验"时，CSS 模拟成为体验上限。真实美术资源能提供：
- 场景氛围感（暴风雨夜的古堡、昏暗书房的光影）
- 人物辨识度（立绘 > 字母头像）
- 证据质感（道具图标 > emoji）

本管线为真实资源的接入提供结构化路径，**无需改动前端代码**即可替换资源。

## 2. 为什么 MiniMax-M3 不负责最终美术生成

MiniMax-M3 是语言模型，适合生成推理剧情、NPC 对话、结局裁判。它不擅长：
- 精细的视觉构图（光影、色彩平衡）
- 保持风格一致性（跨场景、跨人物）
- 输出稳定分辨率的图片

美术资源应由专门的图像生成模型（如 Stable Diffusion、Midjourney、MiniMax 图像模型）负责，或由人类画师绘制。

## 3. 为什么当前采用离线静态资产

当前阶段：
- 不接入任何在线生图 API（避免额外依赖和成本）
- 不做运行时实时生图（延迟影响体验）
- 资产预先生成、离线存储、直接加载

这样设计的好处：
- **可预测的性能**：无网络延迟，资源加载速度稳定
- **可校验的质量**：上线前可人工审核每一张图
- **可维护的结构**：manifest 控制映射，替换不影响代码
- **可为未来扩展留接口**：真实 API 接入时，只需改 `asset_mode` 和 manifest 结构

## 4. assets 目录结构

```
static/assets/
├── scenes/           场景背景图（16:9，推荐 webp）
├── characters/        人物立绘（2:3，透明背景 webp）
├── evidence/          证据图标（1:1，webp）
├── endings/           结局插图（16:9，webp）
├── placeholders/      SVG 占位图（轻量、临时）
├── manifest.json      资源索引
└── README.md          命名规范
```

## 5. 命名规范

详见 `static/assets/README.md`，核心规则：

- 文件名格式：`{type}_{id}_v{number}.{ext}`
- 场景：`scene_{location}_v1.webp`
- 人物：`char_{name}_v1.webp`
- 证据：`ev_{evidence_id}_v1.webp`
- 占位图：`scene_hall.placeholder.svg`（固定 `.placeholder.svg` 后缀）

## 6. manifest 工作机制

`manifest.json` 是资源的唯一真相源：

```json
{
  "version": 1,
  "asset_mode": "offline_static",
  "scenes": {
    "大厅": {
      "image": "/static/assets/scenes/scene_hall_v1.webp",
      "placeholder": "/static/assets/placeholders/scene_hall.placeholder.svg",
      "description": "..."
    }
  },
  "characters": { ... },
  "evidence": { ... },
  "endings": { ... }
}
```

前端加载流程：
1. `index.html` 加载时调用 `loadAssetManifest()`
2. `updateState()` 根据当前地点/NPC/证据调用 `resolveSceneAsset()` / `resolveCharacterAsset()` / `resolveEvidenceAsset()`
3. 解析出 `image/portrait/icon` 和对应的 `placeholder`
4. 调用 `setImageWithFallback(img, primary, fallback)` 按优先级设置

## 7. fallback 机制

```
真实资源 (manifest.image / portrait / icon)
        ↓ 加载失败（404 / 网络错误）
placeholder (manifest.placeholder)
        ↓ 加载失败
CSS fallback（保持现有 CSS 颜色/文字行为）
        ↓
页面不崩溃，保证基础可用
```

三层保障确保页面永不长白屏。

## 8. 资源替换流程

**不需要改代码**。只需：

1. 将新图片放入对应目录（替换同名文件，或新建版本号）
2. 更新 `manifest.json` 中的路径（如果文件名变了）
3. 运行 `python scripts/validate_assets.py` 验证
4. 提交推送

## 9. 后续如何接入生图模型

预留接口：

- `asset_mode` 字段支持扩展为 `api_generated`
- manifest 可扩展 `prompt` 字段存储生图提示词
- 前端可扩展 `loadAssetFromAPI()` 函数
- API Key 通过 `.env` 管理，不进入代码仓库

当决定接入生图 API 时：
1. 在 `manifest.json` 中为需要生成的资源添加 `prompt` 字段
2. 实现 `generateAsset(prompt)` 调用生图 API
3. 将生成的图片保存到对应目录并更新 manifest
4. 运行时可选择"按需生成"或"批量预生成"

## 10. 为什么当前不做运行时实时生图

- **延迟**：生图通常需要 5-30 秒，影响交互体验
- **成本**：每次场景切换生成图片会产生 API 调用费用
- **一致性**：实时生图难以保持跨场景风格统一
- **调试**：静态资源问题可复现，动态生成问题难追踪

推荐做法：**预生成 + 离线存储 + CDN 分发**。MiniMax-M3 仍负责语言/推理部分，不介入视觉生成。

## 11. 验证命令

```bash
# 验证资源完整性
python scripts/validate_assets.py

# 运行冒烟测试
python scripts/smoke_test.py

# 启动 Web 服务器
python web_main.py
```
