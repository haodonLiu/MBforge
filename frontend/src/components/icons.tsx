/**
 * Icon 统一导出入口（向后兼容）。
 *
 * 实际定义已按功能拆分到以下模块：
 *   - ./icons/nav      — 导航类（Folder, File, Layout, Workflow）
 *   - ./icons/actions  — 操作类（Plus, Trash, Download, Check, X）
 *   - ./icons/ui       — UI 控件（Settings, Search, User, Bot, Chat）
 *   - ./icons/science  — 科学类（Flask, Sparkles, Target, BarChart）
 *   - ./icons/arrows   — 箭头类（Chevron, Arrow, ExternalLink）
 *
 * 业务代码应直接从相应子模块导入，icons.tsx 仅作向后兼容。
 */

export type { IconProps } from './icons/types'

// 重新导出所有 icons
export * from './icons/nav'
export * from './icons/actions'
export * from './icons/ui'
export * from './icons/science'
export * from './icons/arrows'
export * from './icons/brand'
