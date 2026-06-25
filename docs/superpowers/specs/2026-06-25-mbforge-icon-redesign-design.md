# MBForge 图标重设计

**日期**：2026-06-25
**范围**：Tauri v2 桌面应用 + 配套移动端 (Android/iOS) 图标重绘
**作者**：brainstorming session

## 目标

替换现有图标（深色圆角方 + 3 个分子六边形）。新图标需：

- 体现 MBForge 品牌身份（分子科学/药物发现）
- 在 32px 仍可识别
- 跨平台一致（Tauri 桌面 + Android + iOS）
- 与项目 dark-first 视觉语言一致

## 设计决策（已确认）

| 维度 | 决策 |
|------|------|
| 概念方向 | 纯字标（typographic） |
| 视觉风格 | 单色/技术感（mono/technical） |
| 配色 | 纯灰度，无彩色 |
| 装饰元素 | 无分子装饰，纯字标 |
| 布局 | 堆叠 MB（M 上 B 下，方形构图） |

## 详细规格

### 1. 字符与字型

- 字标：`M` / `B` 两行，等宽 1:1 占比
- 字型：等宽无衬线（IBM Plex Mono / JetBrains Mono 风格），全大写
- 字重：Bold（700），字面 100% 实心（非描边）
- 字距：紧排（-2% ~ -4%），两字符视觉密度统一
- 字号比：M / B 各占图标高度 32%（含行距 4%），总字高 64%，居中
- 字体来源：开源等宽字体（如 JetBrains Mono Bold, OFL 协议）

### 2. 网格刻度

- 容器：圆角方形（squircle），圆角半径 = 边长 22%（macOS 风格）
- 背景色：`#0B0F14`（深石板，近黑微蓝）
- 4 角各 1 个 L 形刻度（corner ticks），描边 1.5px，颜色 `#94A3B8` @ 40% 不透明
- 刻度长度 = 边长 8%，离角 6%
- 中央主字标外侧无边框

### 3. 配色与对比

- 纯灰度，无彩色
- 背景：`#0B0F14`
- 字标：`#F1F5F9`（近白）
- 刻度：`#94A3B8` @ 40%（等效 `#3F4A5C`）
- 字标 vs 背景对比度 ≈ 14.5:1（WCAG AAA）

### 4. 缩放行为

| 尺寸 | 刻度 | 字标 | 圆角 |
|------|------|------|------|
| 1024px（主稿） | 完整 1.5px | 100% | 22% |
| 128px | 完整 1.5px | 100% | 22% |
| 64px | 1px 描边 | 100% | 22% |
| 32px | 退化或消失 | 100% | 22% |

- 单源 1024px 主稿缩放，确保几何一致
- 缩放工具：ImageMagick（高质量 Lanczos 滤镜）

### 5. 导出与平台覆盖

#### Tauri 桌面（必需）

`src-tauri/icons/`：

- `icon.png` (1024×1024，主稿)
- `32x32.png`, `128x128.png`, `128x128@2x.png` (256×256)
- `icon.ico` (多帧：16/32/48/64/128/256)
- `icon.icns` (多帧：16/32/64/128/256/512/1024)

`tauri.conf.json` `bundle.icon` 列表（已存在，路径不变）：

```
../../icons/32x32.png
../../icons/128x128.png
../../icons/128x128@2x.png
../../icons/icon.icns
../../icons/icon.ico
```

#### Android（全 6 密度）

`src-tauri/icons/android/mipmap-{m,h,xh,xxh,xxxh}dpi/`：

- `ic_launcher.png`
- `ic_launcher_foreground.png`
- `ic_launcher_round.png`

#### iOS

`src-tauri/icons/ios/`：

- AppIcon-20x20@1x/2x/2x-1/3x.png
- AppIcon-29x29@1x/2x/2x-1/3x.png
- AppIcon-40x40@1x/2x/2x-1/3x.png
- AppIcon-60x60@2x/3x.png
- AppIcon-76x76@1x/2x.png
- AppIcon-83.5x83.5@2x.png
- AppIcon-512@2x.png

#### 平台差异处理

- **iOS**：系统自动应用圆角遮罩，主稿保持方角
- **macOS**：`.icns` 自身应用圆角，导出两版
  - 方角主稿 → `icon.png`（1024）
  - 圆角 macOS 专用 → `icon.icns` 内嵌圆角帧
- **Android adaptive icon**：`ic_launcher_foreground.png` 主图，`ic_launcher.png` 完整图标含背景

### 6. 工具链

- **主稿生成**：SVG → PNG（1024×1024）
  - SVG 内嵌 `<text>` 元素，使用系统等宽字体（`JetBrains Mono Bold` / `monospace` 回退）
  - `rsvg-convert` 或 `magick input.svg -density 300 output.png` 渲染
  - 角刻度用 SVG `<path>` 绘制
- **缩放**：ImageMagick `magick input.png -resize WxH output.png`
- **.ico 多帧**：`magick 16.png 32.png 48.png 64.png 128.png 256.png output.ico`
- **.icns**：
  - macOS：`iconutil`（原生）
  - 跨平台：`png2icns`（libicns）
- **批量脚本**：`scripts/build-icons.{sh,ps1}`，幂等可重跑

**字体后备**：若 JetBrains Mono 不可用，依次回退 `IBM Plex Mono Bold` → `DejaVu Sans Mono Bold` → `monospace Bold`。

### 7. 验收标准

- [ ] 32px 灰度下 M/B 仍可分辨
- [ ] 任意密度无锯齿/模糊
- [ ] `.icns` / `.ico` 多分辨率帧齐备且有效
- [ ] `cargo tauri build` 成功，icon 资源被识别
- [ ] 旧图标（6 个分子六边形 + 渐变色）全部替换，无残留
- [ ] 所有现有 tauri.conf.json bundle.icon 引用文件存在
- [ ] Android adaptive icon 5 密度齐备
- [ ] iOS AppIcon 全尺寸齐备

## 风险与权衡

| 风险 | 缓解 |
|------|------|
| 32px 字符可读性 | 字重 700 + 紧排 + 居中保证密度 |
| 跨平台圆角差异 | iOS 系统遮罩 / macOS .icns 内嵌 / 其他保持方角 |
| 字体许可 | 使用 OFL/SIL 开源等宽字体（JetBrains Mono） |
| 主稿色与项目主题冲突 | `#0B0F14` 与现有 dark UI 一致 |

## 不在范围

- 应用内品牌元素（logo, splash screen, favicon）
- 营销物料（社交媒体头像, 文档封面）
- 应用图标动态化（macOS 动态图标）

## 下一步

1. 生成 1024×1024 主稿（Python Pillow / SVG）
2. 缩放至所有平台尺寸
3. 打包 .ico / .icns
4. 验证 `cargo tauri build` 成功
5. 删除旧图标残留
