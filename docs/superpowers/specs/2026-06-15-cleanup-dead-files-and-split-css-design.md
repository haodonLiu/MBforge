# 清理废弃文件与进一步拆分样式设计

## 背景与目标

前端工作流重构完成后，仍有以下遗留清理项：

1. `SettingsModal.tsx` 和 `Environment.tsx` 已无任何引用，属于死代码。
2. `environment/` 目录下的子组件仍被 `settings/SystemTab.tsx` 使用，但目录位置不再合理。
3. `global.css` 中仍包含 PDF Viewer、Notes、MoleculeDisplay 等明确属于其他功能域的样式。

本次清理目标是：

- 删除死代码文件。
- 将 Environment 子组件迁移到 Settings 子目录下，保持代码组织清晰。
- 将 PDF Viewer、Notes、MoleculeDisplay 样式从 `global.css` 拆分为独立样式文件。

## 设计原则

1. 最小变更：只移动文件和拆分样式，不修改组件行为。
2. 引用更新：所有导入路径必须同步更新。
3. 构建可验证：每次移动或拆分后必须保证类型检查、测试、构建通过。

## 文件变更

### 删除文件

- `frontend/src/components/SettingsModal.tsx`
- `frontend/src/components/Environment.tsx`

### 迁移目录

- 将 `frontend/src/components/environment/` 迁移到 `frontend/src/components/settings/environment/`。
- 更新 `frontend/src/components/settings/SystemTab.tsx` 中的导入路径：
  - `@/components/environment/StatCard` → `@/components/settings/environment/StatCard`
  - `@/components/environment/LibrarySection` → `@/components/settings/environment/LibrarySection`
  - `@/components/environment/sections` → `@/components/settings/environment/sections`
  - `@/components/environment/types` → `@/components/settings/environment/types`
- 更新 `frontend/src/components/settings/DetectionCacheCard.tsx` 和 `SidecarCard.tsx` 中的注释，说明它们现在被 SystemTab 使用。

### 新增样式文件

- `frontend/src/styles/pdf-viewer.css`：PDF Viewer 和 PDF Toolbar 相关样式。
- `frontend/src/styles/notes.css`：Notes 组件相关样式。
- `frontend/src/styles/molecule-display.css`：MoleculeDisplay 组件相关样式。

### 修改样式文件

- `frontend/src/styles/global.css`：移除 PDF Viewer、Notes、MoleculeDisplay 的样式规则。
- `frontend/src/main.tsx`：按顺序导入新的样式文件。

## 验收标准

1. `SettingsModal.tsx` 和 `Environment.tsx` 不存在于 `frontend/src/components/` 中。
2. `frontend/src/components/environment/` 目录不存在；其内容已迁移到 `frontend/src/components/settings/environment/`。
3. `frontend/src/components/settings/SystemTab.tsx` 使用新的导入路径。
4. `global.css` 中不再包含 PDF Viewer、Notes、MoleculeDisplay 的样式规则。
5. `pdf-viewer.css`、`notes.css`、`molecule-display.css` 包含对应样式并在 `main.tsx` 中导入。
6. `cd frontend && npx tsc --noEmit` 零错误。
7. `cd frontend && npm test` 全部通过。
8. `cd frontend && npm run build` 构建成功。
9. `cd src-tauri && cargo check` 零错误。

## 风险

- 文件移动可能导致路径导入错误，需通过类型检查捕获。
- CSS 拆分若遗漏规则可能导致样式丢失，需通过构建和视觉检查验证。
