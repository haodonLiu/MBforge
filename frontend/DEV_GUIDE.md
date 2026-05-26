# MBForge 前端开发规范

## 项目结构

```
frontend/
├── src/
│   ├── App.tsx              # 主布局，保持 routes 不变
│   ├── main.tsx             # 入口文件
│   ├── components/          # 页面组件
│   │   ├── Sidebar.tsx     # 侧边栏导航
│   │   ├── Header.tsx      # 顶部标题栏
│   │   ├── Welcome.tsx     # 首页
│   │   ├── Search.tsx      # 知识库搜索
│   │   ├── Chat.tsx        # AI 对话
│   │   ├── PDFViewer.tsx   # PDF 阅读器
│   │   ├── MoleculeLibrary.tsx  # 分子库
│   │   ├── Workflow.tsx    # 工作流
│   │   ├── ProjectView.tsx # 项目视图
│   │   ├── Settings.tsx    # 设置面板 ⭐ 新增
│   │   └── icons.tsx       # SVG 图标
│   ├── styles/
│   │   └── global.css      # 全局样式 + CSS 变量
│   ├── api/
│   │   └── client.ts       # API 客户端 ⚠️ 不要修改
│   └── types/
│       └── index.ts         # 共享类型 ⚠️ 不要修改
├── vite.config.ts           # Vite 配置 ⚠️ 不要修改
├── package.json            # 依赖 ⚠️ 不要修改
└── tsconfig.json           # TypeScript 配置
```

## UI Agent 权限

### ✅ 可以修改
- `frontend/src/components/*.tsx` — 所有页面组件，可随意重构 UI
- `frontend/src/styles/global.css` — 主题、间距、动画
- `frontend/src/App.tsx` — 布局调整（保持 routes 不变）
- `frontend/src/components/icons.tsx` — 添加新 SVG 图标

### ❌ 不要修改
- `frontend/src/api/client.ts` — 后端 API 契约
- `frontend/src/types/index.ts` — 共享类型定义
- `frontend/vite.config.ts` — 代理配置
- `frontend/package.json` — 依赖管理

## 设计规范

### 布局系统
```tsx
// App.tsx 当前 Grid 布局
display: grid
gridTemplateColumns: '56px 1fr'  // 侧边栏 56px
gridTemplateRows: 'auto 1fr auto'  // 头部、主内容、状态栏
```

### CSS 变量（global.css）
```css
/* 颜色 */
--bg-base: #ffffff        /* 主背景 */
--bg-surface: #f8f8f8     /* 卡片/面板背景 */
--bg-elevated: #f0f0f0    /* 悬浮背景 */
--bg-hover: #e5e5e5        /* 悬停状态 */
--accent: #1a1a1a          /* 主色调（当前为黑色） */
--accent-hover: #333333    /* 主色调悬停 */
--accent-muted: rgba(0,0,0,0.06)  /* 主色调浅色 */
--text-primary: #1a1a1a    /* 主文字 */
--text-secondary: #666666  /* 次要文字 */
--text-muted: #999999      /* 辅助文字 */
--border: #e0e0e0          /* 边框 */
--border-light: #d0d0d0    /* 浅边框 */

/* 字号 */
--font-size-base: 14px
--font-size-small: 12px
--font-size-large: 16px
--font-size-title: 20px
```

### 工具类（global.css）
```css
/* Flex */
.flex { display: flex }
.flex-col { flex-direction: column }
.items-center { align-items: center }
.justify-between { justify-content: space-between }
.gap-2 { gap: 8px }
.gap-3 { gap: 12px }
.gap-4 { gap: 16px }
.flex-1 { flex: 1 }

/* Overflow */
.overflow-auto { overflow: auto }
.overflow-hidden { overflow: hidden }

/* Button */
.btn { padding: 12px 24px; border-radius: 10px; cursor: pointer }
.btn-primary { background: var(--accent); color: white }
.btn-secondary { background: var(--bg-surface); border: 1px solid var(--border) }

/* Input */
.input { padding: 12px 14px; border: 1px solid var(--border); border-radius: 8px }

/* Card */
.card { background: var(--bg-surface); border: 1px solid var(--border); border-radius: 12px }
```

### 组件模式

```tsx
// 侧边栏导航项示例 (Sidebar.tsx)
<button
  title="页面名称"
  style={{
    width: '44px',
    height: '44px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: '8px',
    border: 'none',
    cursor: 'pointer',
    background: isActive ? 'var(--accent-muted)' : 'transparent',
    color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
  }}
>
  <Icon size={20} />
</button>
```

## 路由配置

当前路由（App.tsx）：
```tsx
<Routes>
  <Route path="/" element={<Welcome />} />
  <Route path="/search" element={<Search />} />
  <Route path="/chat" element={<Chat />} />
  <Route path="/pdf" element={<PDFViewer />} />
  <Route path="/molecules" element={<MoleculeLibrary />} />
  <Route path="/workflow" element={<Workflow />} />
  <Route path="/project" element={<ProjectView />} />
  <Route path="/settings" element={<Settings />} />  // ⭐ 需要添加
</Routes>
```

## 新增组件清单

### Settings.tsx（待实现）
- 主题设置（浅色/深色/跟随系统）
- 字号设置（小/中/大）
- AI 模型配置（Provider、模型、API Key）
- Embedding 配置
- Reranker 配置
- 模型服务配置（Host、端口、超时）
- 关于页面

### PDFViewer.tsx 增强
- [x] 左侧缩略图面板
- [x] 主阅读区
- [x] 右侧注释面板（高亮/笔记/分子）
- [x] 工具栏（翻页、高亮、笔记、缩放）
- [ ] 提取分子快捷栏（HTML 原型中有，可迁移）

## 开发命令

```bash
# 安装依赖
cd frontend && npm install

# 开发模式
npm run dev

# 构建生产版本
npm run build

# 预览生产版本
npm run preview
```

## 注意事项

1. **保持风格一致** — 使用 CSS 变量而非硬编码颜色
2. **使用工具类** — 优先使用 global.css 中的工具类，减少内联样式
3. **图标统一** — 新图标添加到 icons.tsx，使用统一的大小参数
4. **响应式** — 考虑大屏适配，主要针对 1400px+ 屏幕
5. **无障碍** — 按钮要有 title 属性，支持键盘导航

## 修改前必读

每次修改前，请重新阅读此文件以确保：
1. 明确修改范围（✅ 可改 vs ❌ 不可改）
2. 理解当前的布局系统
3. 遵循既有的 CSS 变量命名
4. 保持组件模式一致
