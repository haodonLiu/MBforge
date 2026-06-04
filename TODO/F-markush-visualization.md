# Task F: Markush 结构可视化

> 优先级: P1 · 难度: ★★★☆☆ · 工作量: 2-3 天 · 依赖: 无

## 目标

让 Markush 结构在前端可渲染显示。当前后端已能生成 MoleCode（Mermaid 图文本），
但前端无法渲染，分子显示完全依赖 PubChem 外部 API。

## 当前状态

| 组件 | 状态 |
|------|------|
| `molecode.rs` 生成 Mermaid 文本 | ✅ 已实现 |
| `molecode.rs` 处理 `{R1}`/`{Boc}` 缩写节点 | ✅ 已实现 |
| 前端 mermaid.js 渲染 | ❌ 未安装 |
| `esmiles_to_molecode` Tauri 命令 | ❌ 未暴露 |
| Markush 可视化组件 | ❌ 不存在 |

## 实现步骤

### F1: 前端安装 mermaid.js

```bash
cd frontend && npm i mermaid
```

### F2: 创建 MermaidCode 组件

- 新建 `frontend/src/components/ui/MermaidCode.tsx`
- 接收 `code: string` prop（Mermaid 图文本）
- 使用 `mermaid.render()` 生成 SVG
- 处理缩写节点 `{R1}`、`{Boc}` 的渲染样式

### F3: 集成到 Markdown 渲染

- 修改 `frontend/src/components/Chat.tsx`
- 检测 ` ```mermaid ` 代码块
- 使用 `MermaidCode` 组件替代纯文本显示

### F4: 暴露 Tauri 命令

- 在 `commands/` 中新增 `esmiles_to_molecode_cmd`
- 注册到 `generate_handler!`
- 前端可按需调用：`invoke('esmiles_to_molecode_cmd', { esmiles, name })`

### F5: MoleculeDisplay 集成

- 修改 `frontend/src/components/molecule/MoleculeDisplay.tsx`
- 添加 "MoleCode 视图" 切换按钮
- 默认显示 PubChem PNG，切换后显示 Mermaid 图
- 离线时自动降级到 Mermaid 图（不依赖外部 API）

## 参考文件

- `ref/MoleCode/molecode/markush/rdkit_to_mermaid.py` — Markush → Mermaid 转换
- `ref/MoleCode/docs/04-markush.md` — Markush 文档
- `src-tauri/src/core/molecode.rs` — 后端 MoleCode 生成器
- `frontend/src/components/molecule/MoleculeDisplay.tsx` — 当前分子显示组件

## 验证

```bash
# 前端
cd frontend && npm test
# 新增测试：
# - MermaidCode 组件渲染测试
# - Chat 中 mermaid 代码块检测测试

# 后端
cargo test --lib -- core::molecode --nocapture
```
