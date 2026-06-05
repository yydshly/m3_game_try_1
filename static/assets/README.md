# 视觉资产目录 /static/assets/

本目录存放游戏的真实视觉资源（场景、人物、证据、结局图）。

## 目录结构

```
static/assets/
├── scenes/           场景背景图，建议 16:9，webp/png
├── characters/       人物立绘，建议 2:3，透明背景 webp/png
├── evidence/         证据图标，建议 1:1，webp/png
├── endings/           结局插图，建议 16:9，webp/png
├── placeholders/      缺图 fallback（轻量 SVG）
├── manifest.json      资源索引（资源映射 + 元数据）
└── README.md          本文件
```

## 资源加载优先级

```
真实资源 image / portrait / icon
        ↓ 加载失败 / 不存在
placeholder
        ↓ 加载失败
CSS fallback / 文本 fallback
```

## 命名规范

### 场景（scenes/）

```
scene_hall_v1.webp       古堡大厅
scene_study_v1.webp       周慎之书房
scene_kitchen_v1.webp     厨房
scene_dining_v1.webp      餐厅
scene_corridor_v1.webp    走廊
scene_security_v1.webp    保安室
scene_linwan_room_v1.webp 林婉房间
scene_chenbo_room_v1.webp 陈伯房间
scene_susu_room_v1.webp   苏苏房间
scene_wangzong_room_v1.webp 王总房间
scene_self_room_v1.webp   侦探房间（自己房间）
```

### 人物（characters/）

```
char_chenbo_v1.webp       陈伯
char_linwan_v1.webp       林婉
char_susu_v1.webp         苏苏
char_wangzong_v1.webp     王总
char_afu_v1.webp          阿福（厨师）
char_xiaozhang_v1.webp    小张（保安）
```

### 证据（evidence/）

```
ev_teacup_v1.webp          异常的茶杯残留
ev_will_v1.webp            新遗嘱草稿
ev_medical_note_v1.webp    林婉的病历笔记
ev_debt_note_v1.webp       借据
ev_chef_testimony_v1.webp   厨师阿福的证词
```

### 结局（endings/）

```
ending_culprit_caught_v1.webp    真凶落网
ending_culprit_escape_v1.webp   真凶逃脱
ending_wrong_accuse_v1.webp     错误指认
```

## 版本号规则

文件命名中的 `_v1` 表示版本。替换资源时：
- 小幅更新（如色彩修正）：`_v2`
- 全新美术方向：`_v2`（旧文件可删除或归档）

## 替换流程

1. 将新图片放入对应目录
2. 更新 `manifest.json` 中的路径（或保持路径不变，直接替换文件）
3. 运行 `python scripts/validate_assets.py` 验证
4. 无需修改前端代码

## 占位图说明

`placeholders/` 下的 SVG 文件是临时占位图，不是最终美术。它们的存在确保：
- 页面不会白屏
- 布局不会出现断层
- AI 生图时可通过提示词参照这些轮廓感

当真实图片接入后，placeholder 自动降级为备用，不影响主流程。
