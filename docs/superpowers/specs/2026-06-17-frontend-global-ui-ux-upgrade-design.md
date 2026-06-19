# MBForge 前端全局 UI/UX 升级设计规范

**Date:** 2026-06-17  
**Scope:** 前端全局视觉与交互升级；先在 Settings 模块（重点 AI Models）试点落地。  
**Visual direction:** 现代专业工具风（Linear / Vercel / Claude Settings 方向）。  

---

## 1. 背景与目标

### 1.1 当前问题
- 设置页视觉层级弱，AI Models 卡片与页面背景融合度高，缺乏分组感。
- 顶层 Tab 与 AI Models 内部 Tab 均使用 `variant="underline"`，易产生层级混淆。
- 表单字段宽度、对齐不一致，右侧边缘参差不齐。
- 连接状态反馈过于细微（仅 12px 小字 + 圆点），用户难以感知。
- 保存/取消等反馈远离操作区域，缺乏局部确认。
- 暗色模式只是简单反色，部分组件对比度不足。
- CSS 分散在多个全局文件中，`settings.css` 已逾 1200 行，维护困难。

### 1.2 目标
- 建立一套**可落地、可维护**的全局设计系统。
- 提升**可读性、专业感与信任感**。
- 统一全站组件行为，降低用户认知负担。
- 在 **Settings → AI Models** 页面完成首发落地，验证规范后再推广。

### 1.3 非目标
- 不更换前端技术栈（仍用 React + 手写 CSS / CSS 变量）。
- 不改动业务逻辑与后端接口。
- 不一次性重写所有页面；本次只实现 Settings 试点。

---

## 2. 设计原则

1. **清晰层级** — 通过背景色、卡片、边框、阴影四层材质区分信息密度，避免所有元素平铺。
2. **状态即时可见** — 成功、警告、错误、加载均使用颜色 + 图标 + 文字 + 微动效。
3. **一致行为** — 同类型组件（Button、Input、Tabs、Card）全站只保留一套主要样式。
4. **暗色原生** — 深色模式不是反色，而是重新校准对比度与饱和度。
5. **克制动效** — 动效用于引导注意力，而非装饰；支持 `prefers-reduced-motion`。

---

## 3. 设计系统

### 3.1 颜色

保持现有 `theme.css` 的 CSS 变量结构，逐步收敛为以下语义 token：

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--bg-base` | `#ffffff` | `#0f0f11` | 页面最底层背景 |
| `--bg-surface` | `#f8f8f8` | `#18181b` | 卡片、面板背景 |
| `--bg-elevated` | `#ffffff` | `#232329` | 弹窗、下拉、悬浮层 |
| `--bg-hover` | `#f3f3f5` | `#27272e` | 列表项/卡片悬停 |
| `--border` | `#e4e4e7` | `#2e2e35` | 卡片、分组、分割线 |
| `--border-strong` | `#d4d4d8` | `#3f3f46` | 输入框边框、聚焦态 |
| `--text-primary` | `#18181b` | `#fafafa` | 标题、主文本 |
| `--text-secondary` | `#52525b` | `#a1a1aa` | 描述、次要文本 |
| `--text-muted` | `#71717a` | `#71717a` | placeholder、禁用态 |
| `--accent` | `#4f46e5` | `#6366f1` | 主按钮、链接、激活态 |
| `--accent-hover` | `#4338ca` | `#818cf8` | 悬停态 |
| `--accent-muted` | `rgba(79,70,229,0.08)` | `rgba(99,102,241,0.15)` | 选中背景、轻强调 |
| `--success` | `#16a34a` | `#22c55e` | 成功状态 |
| `--warning` | `#ca8a04` | `#eab308` | 警告状态 |
| `--danger` | `#dc2626` | `#ef4444` | 错误状态 |

**规则：**
- 新增语义 token 必须先声明 `--bg-*`、`--border-*`、`--text-*`，再声明功能色。
- 任何组件禁止使用硬编码十六进制色值；必须从 `theme.css` 变量读取。
- 暗色模式主色 `--accent` 比浅色模式更亮 10-15%，保持感知一致。

### 3.2 字体

保持现有字体栈，统一层级：

| 层级 | 大小 | 行高 | 字重 | 用途 |
|------|------|------|------|------|
| Page Title | 22px | 28px | 600 | 设置页大标题 |
| Section Title | 16px | 22px | 600 | 卡片/分组标题 |
| Body | 14px | 20px | 400 | 正文、标签 |
| Caption | 12px | 16px | 400 | 描述、hint、状态文字 |
| Code | 13px | 18px | 400 | API key、URL 等等宽内容 |

**规则：**
- 所有文本颜色使用 `--text-*` token，禁止在组件中写死 `#666` 等。
- 代码/URL 输入统一使用系统默认等宽字体栈 `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`。

### 3.3 间距

以 4px 为基准网格：

| Token | 值 | 用途 |
|-------|-----|------|
| `--space-1` | 4px | 图标与文字间隙 |
| `--space-2` | 8px | 小组件内部 gap |
| `--space-3` | 12px | 表单项行内间距 |
| `--space-4` | 16px | 卡片内边距、表单组间距 |
| `--space-5` | 20px | 卡片之间、分块间距 |
| `--space-6` | 24px | 页面内容区左右内边距 |
| `--space-8` | 32px | 页面上下大间距 |

**规则：**
- 卡片内边距统一 `16px`（移动端 `12px`）。
- 表单组之间统一 `20px`。
- 避免使用 10px、14px、18px 等“奇数”间距。

### 3.4 圆角

| Token | 值 | 用途 |
|-------|-----|------|
| `--radius-sm` | 6px | 小按钮、标签、徽章 |
| `--radius-md` | 8px | 输入框、小卡片 |
| `--radius-lg` | 12px | 设置卡片、面板 |
| `--radius-xl` | 16px | 弹窗、大面板 |
| `--radius-full` | 9999px | 胶囊按钮、开关 |

**规则：**
- 设置卡片统一 `12px`。
- 按钮统一 `8px`。
- 输入框统一 `8px`。

### 3.5 阴影与边框

| Token | Light | Dark | 用途 |
|-------|-------|------|------|
| `--shadow-card` | `0 1px 3px rgba(0,0,0,0.04)` | `none` | 卡片默认 |
| `--shadow-elevated` | `0 4px 12px rgba(0,0,0,0.08)` | `0 4px 16px rgba(0,0,0,0.35)` | 悬浮层、下拉 |
| `--border-card` | `1px solid var(--border)` | `1px solid var(--border)` | 卡片描边 |

**规则：**
- 浅色模式卡片使用“边框 + 极淡阴影”组合，增加层次但不沉重。
- 深色模式卡片以边框为主，阴影仅用于悬浮层。

---

## 4. 组件规范

### 4.1 卡片（Card / SettingCard）

```
┌────────────────────────────────────────────┐
│  Title                              [icon] │  ← 16px padding
│  Description text (muted)                  │
├────────────────────────────────────────────┤
│                                            │
│  SettingItem 1                             │
│  SettingItem 2                             │
│                                            │
└────────────────────────────────────────────┘
```

**样式：**
- 背景：`var(--bg-surface)`
- 边框：`var(--border-card)`
- 圆角：`var(--radius-lg)`
- 内边距：`16px`
- 阴影：`var(--shadow-card)`（浅色）/ `none`（深色）

**行为：**
- 卡片本身无 hover 动效，避免与内部按钮冲突。
- 若卡片可点击，hover 时边框变为 `--border-strong`，背景变为 `--bg-hover`。

### 4.2 按钮（Button）

保留 `primary` / `secondary` / `ghost` / `danger` 四种变体：

| Variant | 背景 | 文字 | 边框 | 用途 |
|---------|------|------|------|------|
| primary | `--accent` | `#fff` | none | 保存、确认、主要操作 |
| secondary | `--bg-elevated` | `--text-primary` | `--border` | 次要操作、测试连接 |
| ghost | transparent | `--text-secondary` | none | 链接、低优先级操作 |
| danger | `--danger` | `#fff` | none | 删除、危险操作 |

**尺寸：**
- `sm`: 高 28px，padding 8px 12px，字体 12px
- `md`: 高 34px，padding 10px 16px，字体 13px
- `lg`: 高 40px，padding 12px 20px，字体 14px

**行为：**
- Hover: `background` 加深/变亮 8%，`transform: translateY(-1px)`。
- Active/Pressed: `transform: translateY(0)`。
- Focus: 2px `--accent-muted`  outline ring（键盘导航可见）。
- Loading: 左侧显示 `Spinner`，文字保留，按钮禁用但保持原尺寸。

### 4.3 输入框（Input / Select）

**样式：**
- 高度：`34px`（标准）/ `28px`（紧凑）。
- 背景：`var(--bg-base)`（浅色）/ `var(--bg-elevated)`（深色）。
- 边框：`1px solid var(--border)`，圆角 `8px`。
- 内边距：`10px 12px`。
- Placeholder：`var(--text-muted)`。

**状态：**
- Hover: 边框 `--border-strong`。
- Focus: 边框 `--accent`，外加 `0 0 0 3px var(--accent-muted)` 外发光。
- Error: 边框 `--danger`，背景 `--danger` 5% 透明。
- Disabled: 背景 `--bg-surface`，文字 `--text-muted`，无 focus 环。

**API Key 输入：**
- 使用等宽字体，右侧固定显示“显示/隐藏”与“复制”图标按钮。
- 聚焦时整体外发光，不单独给图标按钮加 outline。

### 4.4 标签页（Tabs）

当前有顶层 Settings Tabs 与 AI Models 内部 Tabs 两层。为避免混淆：

**顶层 Settings Tabs**
- 样式：下划线指示器（保留当前 `variant="underline"`），但尺寸 `md`。
- 字体：`14px`，字重 `500`。
- 指示器：2px `--accent`，带 `layoutId` 滑动动效。

**AI Models 内部 Tabs**
- 样式：改为**胶囊/分段控件**（`variant="segment"`），背景 `--bg-surface`，选中项 `--bg-elevated` + `--accent` 文字。
- 尺寸：`sm`。
- 目的：与顶层下划线形成材质差异，明确层级。

### 4.5 徽章/状态（Badge / Status）

统一六种语义色：

| 状态 | 背景 | 文字 | 图标 |
|------|------|------|------|
| success | `--success` 10% | `--success` | 对勾 |
| warning | `--warning` 10% | `--warning` | 感叹号 |
| danger | `--danger` 10% | `--danger` | 叉号 |
| info | `--accent-muted` | `--accent` | 信息 |
| neutral | `--bg-hover` | `--text-secondary` | 圆点 |
| loading | `--bg-hover` | `--text-secondary` | Spinner |

**连接状态（AI Models）**
- 在卡片右上角使用 `Badge` 而非纯文字圆点。
- 测试进行中显示“Testing...” loading badge。
- 测试成功后 2s 自动淡出为稳定的 success badge（可选）。

### 4.6 提示与反馈

**Toast**
- 位置：右上角，距离边缘 `24px`。
- 最大宽度：`360px`。
- 包含图标、标题、可选描述、关闭按钮。
- 自动消失：`4000ms`；hover 时暂停倒计时。

**Inline Alert**
- 用于卡片内的错误/警告说明。
- 左侧 3px 彩色边条，图标 + 标题 + 描述。
- 背景使用对应语义色的 5-10% 透明度。

### 4.7 空状态与加载

**Empty State**
- 居中，图标 `48px`，标题 `16px/600`，描述 `14px/400`。
- 图标颜色 `--text-muted`；标题 `--text-primary`。

**Skeleton**
- 使用 CSS `shimmer` 动画，避免 JS 定时器。
- 卡片骨架：圆角 `12px`，高度 `120px`。
- 文本骨架：圆角 `4px`，高度 `12px`。

---

## 5. Settings 试点设计

### 5.1 页面结构

```
SettingsPage
├── PageHeader: "Settings" + Save/Cancel/Dirty indicator
├── Tabs (top): General | AI Models | PDF Processing | Models | System | ...
└── TabPanel
    └── AIModelsSection
        ├── SectionHeader: "AI Models" + description
        ├── Tabs (segment): LLM | Embedding | Reranker | VLM | OCR
        └── ModelConfigCard
            ├── CardHeader
            │   ├── Title + description
            │   └── Connection status badge + Test button
            ├── Connection Group
            │   ├── Provider (select)
            │   ├── Base URL (text)
            │   └── API Key (password)
            ├── Sampling Group (LLM only)
            │   ├── Max Tokens
            │   └── Top P
            └── OCR Extra Group (OCR only)
                ├── Backend URL
                └── Backend Key
```

### 5.2 AI Models 内部 Tab 改进

- 将 `variant="underline"` 改为 `variant="segment"`。
- 每个 tab 文字旁可显示小图标（可选，先预留）。
- Tab 内容切换使用 `AnimatedPage` 的淡入 + 轻微右移（`x: 8 → 0`），避免生硬跳转。

### 5.3 表单布局改进

**统一字段宽度**
- 标签区固定宽度 `160px`（移动端 `100%` 堆叠）。
- 控制区最小宽度 `280px`，最大宽度 `480px`，占据剩余空间。
- 所有输入框在控制区内左对齐，右边缘自然对齐。

**分组标题**
- 使用 `SectionTitle` 或小型分组标题（`14px/600`）。
- 分组间距 `20px`，组内项间距 `12px`。

**描述文字**
- 每个 SettingItem 保留 description，颜色 `--text-secondary`，字号 `12px`。
- 避免 description 折行超过两行；过长时考虑用 tooltip 或帮助链接。

### 5.4 连接状态反馈改进

- 在 `ModelConfigCard` 标题右侧放置 `Badge`：
  - `not_configured` → neutral badge “未配置”
  - `testing` → loading badge “测试中...”
  - `ok` → success badge “在线”
  - `unreachable` → danger badge “无法连接”
- 测试按钮放在 badge 右侧，使用 `secondary` `sm`。
- 测试成功后显示一次性 inline alert “连接成功，配置已生效”，3s 后自动消失。
- 测试失败在 Base URL / API Key 字段下方显示红色 inline message。

### 5.5 保存反馈改进

- 保留全局 Save/Cancel 按钮，但增加：
  - 用户修改任意字段后，对应字段右侧短暂显示“已修改”小圆点（`dirty dot`），1s 后消失。
  - 保存成功后，按钮文字临时变为“已保存 ✓” 1.5s。
  - 保存失败时，Save 按钮变 danger 并抖动一次（`shake` 动画）。

### 5.6 文件影响清单

本次 Settings 试点将修改/新增以下文件：

| 路径 | 动作 | 说明 |
|------|------|------|
| `frontend/src/styles/theme.css` | 修改 | 补充/收敛颜色 token |
| `frontend/src/styles/patterns.ts` | 修改 | 更新 `surfaceBlock` 等模式 |
| `frontend/src/styles/settings.css` | 修改 | 重构 AI Models 相关样式，删除冗余 |
| `frontend/src/components/ui/Tabs.tsx` | 修改 | 新增 `segment` variant |
| `frontend/src/components/ui/Badge.tsx` | 新增 | 统一徽章组件 |
| `frontend/src/components/ui/InlineAlert.tsx` | 新增 | 卡片内提示组件 |
| `frontend/src/components/ui/Toast.tsx` | 新增 | 全局 Toast（如需要） |
| `frontend/src/components/settings/ModelConfigCard.tsx` | 修改 | 应用新卡片、状态 badge、布局 |
| `frontend/src/components/settings/sections/AIModelsSection.tsx` | 修改 | segment tabs、section header |
| `frontend/src/components/settings/SettingRow.tsx` | 修改 | 统一字段宽度与描述样式 |
| `frontend/src/components/settings/SettingsPage.tsx` | 修改 | 保存按钮反馈 |
| `frontend/src/i18n/locales/en.json` | 修改 | 新增/更新文案 |
| `frontend/src/i18n/locales/zh-CN.json` | 修改 | 新增/更新文案 |

---

## 6. 动效与微交互

### 6.1 原则
- 动效时长以 `200ms` 为主，复杂过渡不超过 `300ms`。
- 缓动函数：`cubic-bezier(0.4, 0, 0.2, 1)`（ease-out 为主）。
- 支持 `prefers-reduced-motion: reduce` 时禁用非必要动画。

### 6.2 具体规范

| 场景 | 动画 | 时长 |
|------|------|------|
| 页面/Tab 切换 | `opacity` + `translateX(8px → 0)` | 200ms |
| 按钮悬停 | `translateY(-1px)` + 背景色变 | 150ms |
| 按钮按下 | `translateY(0)` + scale(0.98) | 100ms |
| 输入框聚焦 | 边框色变 + `box-shadow` 外发光 | 150ms |
| 卡片出现 | `opacity` + `translateY(8px → 0)` | 200ms |
| Badge 状态切换 | `opacity` + `scale(0.95 → 1)` | 150ms |
| Toast 进入 | `translateX(20px → 0)` + `opacity` | 250ms |
| Toast 退出 | `translateX(0 → 20px)` + `opacity` | 200ms |
| 保存失败 | `shake` 关键帧 | 300ms |

### 6.3 减少动效

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 7. 暗色模式策略

- 暗色模式通过 `data-theme="dark"` 与 `theme.css` 变量切换，已有基础。
- 关键调整：
  - 卡片背景 `--bg-surface` 与页面 `--bg-base` 拉开足够对比（当前 `#18181b` vs `#0f0f11`）。
  - 输入框背景使用 `--bg-elevated`（比卡片更亮一层），在深色中更突出。
  - `--accent` 在暗色下更亮（`#6366f1` vs 浅色 `#4f46e5`）。
  - 阴影在暗色下使用高透明度黑（`rgba(0,0,0,0.35)`）。
- 所有新增组件必须同时测试 light/dark。

---

## 8. 可访问性

### 8.1 键盘导航
- 所有交互元素必须可通过 `Tab` 聚焦。
- Focus 环清晰可见：`outline: 2px solid var(--accent); outline-offset: 2px`。
- Tab 组件支持 `← →` 方向键切换。
- 按钮/链接支持 `Space` / `Enter` 激活。

### 8.2 ARIA
- Tabs: `role="tablist"`、`role="tab"`、`role="tabpanel"`，并正确设置 `aria-selected`、`aria-controls`、`aria-labelledby`。
- Badge/Status: 使用 `aria-live="polite"` 播报连接状态变化。
- Form inputs: 所有输入框关联 `<label>` 或通过 `aria-labelledby` 关联。

### 8.3 对比度
- 正文文字与背景对比度 ≥ 4.5:1。
- 大号文字/按钮文字 ≥ 3:1。
- 错误/成功状态同时提供图标+颜色，不单靠颜色传递信息。

---

## 9. 验收标准

### 9.1 设计系统
- [ ] `theme.css` 中新增/收敛的 token 被所有试点组件使用，无硬编码色值。
- [ ] `patterns.ts` 中 `surfaceBlock`、`hstack`、`vstack` 更新为新规范。

### 9.2 Settings 试点
- [ ] AI Models 内部 Tab 改为 `segment` variant，与顶层 `underline` 区分明显。
- [ ] `ModelConfigCard` 使用新卡片样式，标题区显示 Badge + Test 按钮。
- [ ] 表单字段标签区宽度统一（`160px`），控制区最小宽度 `280px`，右边缘对齐。
- [ ] 测试连接状态使用 Badge 展示，loading/success/danger/neutral 四种状态正确。
- [ ] 保存/取消反馈在按钮上可见（保存成功变“已保存 ✓”，失败抖动）。

### 9.3 动效与可访问性
- [ ] Tab 切换、卡片出现、按钮悬停有符合规范的过渡。
- [ ] 设置 `prefers-reduced-motion: reduce` 后非必要动画消失。
- [ ] 所有新增 Tab/Input/Button 可通过键盘操作。

### 9.4 构建与测试
- [ ] `npx tsc --noEmit` 通过。
- [ ] `npm run build` 通过。
- [ ] 视觉回归：在 light/dark 模式下人工检查 AI Models 页。

---

## 10. 后续推广计划

试点验收后，按以下顺序推广：

1. **General / PDF Processing** — 结构简单，复用 `SettingCard` 与 `SettingItem`。
2. **Models / Cache / System** — 涉及列表、卡片网格、统计数字，需要扩展 `StatCard`、`ModelCard` 规范。
3. **全局组件** — `Button`、`Input`、`Spinner`、`EmptyState`、`Skeleton` 全面替换旧实现。
4. **CSS 清理** — 删除 `settings.css` 中冗余样式，按页面拆分模块。

---

## 11. 备注

- 本次设计基于 2026-06-17 对项目前端代码的扫描，重点关注 `frontend/src/components/settings` 与 `frontend/src/styles`。
- 不改动路由、状态管理、后端命令。
- 新增组件优先放在 `frontend/src/components/ui/`，保持与现有设计系统一致。
