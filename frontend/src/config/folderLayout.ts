/**
 * Canonical project folder layout.
 *
 * Single source of truth for the UI. The backend mirrors via
 * `src/mbforge/utils/constants.py` (PROJECT_FORMAT_VERSION / *_FILE / *_DIR).
 */

export const PROJECTS_DIR = 'projects' as const
export const PAPERS_DIR = 'papers' as const
export const NOTES_DIR = 'notes' as const
export const MOLECULES_DIR = 'molecules' as const
export const INDEX_DIR = 'index' as const
export const REPORTS_DIR = 'reports' as const

export const PAPERS_EXTS = ['pdf'] as const
export const NOTES_EXTS = ['md', 'txt'] as const

export const CANONICAL_USER_DIRS = [
  PROJECTS_DIR,
  PAPERS_DIR,
  NOTES_DIR,
  MOLECULES_DIR,
  INDEX_DIR,
  REPORTS_DIR,
] as const

export interface FolderSpec {
  name: string
  role: 'input' | 'output' | 'meta'
  accepts: string
  description: string
}

export const FOLDER_SPECS: readonly FolderSpec[] = [
  {
    name: PROJECTS_DIR,
    role: 'input',
    accepts: '(DocumentProject)',
    description: '每篇导入 PDF 的独立文档项目',
  },
  {
    name: PAPERS_DIR,
    role: 'input',
    accepts: '.pdf',
    description: '用户拖入的 PDF 论文（旧版，自动迁移）',
  },
  {
    name: NOTES_DIR,
    role: 'input',
    accepts: '.md / .txt',
    description: '用户手写笔记 + pipeline 提取的 MD',
  },
  {
    name: MOLECULES_DIR,
    role: 'output',
    accepts: '(.sdf / .mol / .pdb / .smi)',
    description: 'pipeline 提取出的分子（系统写入）',
  },
  {
    name: INDEX_DIR,
    role: 'output',
    accepts: '(内部)',
    description: '向量库、chunks、semantic cache（系统写入）',
  },
  {
    name: REPORTS_DIR,
    role: 'output',
    accepts: '(报告 / 图表)',
    description: '生成的报告、figures（系统写入）',
  },
  {
    name: '.mbforge',
    role: 'meta',
    accepts: '(元数据)',
    description: 'app 独占 — version.json / index.json / settings.json',
  },
] as const
