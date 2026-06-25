/** Project management — open, scan, list, file tree, file operations. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface ProjectInfo {
  name: string
  root: string
  document_count: number
}

/**
 * Discriminated union — Rust uses ``Result<_, String>`` for failures, so the
 * ``success: false`` branch is never produced by the current backend. Keeping
 * it in the type means future Rust changes that return ``success: false``
 * will force a TS compile error in consumers, surfacing contract drift at
 * build time rather than as a "no results" toast at runtime.
 */
export type ProjectResponse =
  | { success: true; project: ProjectInfo }
  | { success: false; error: string }

// DEV ONLY — these console statements exist to debug the Tauri IPC bridge
// during local development. Vite tree-shakes them out of production builds
// (the body becomes dead code under `import.meta.env.DEV === false`).
const dlog = (...args: unknown[]) => {
  if (import.meta.env.DEV) console.log(...args)
}
const derr = (...args: unknown[]) => {
  if (import.meta.env.DEV) console.error(...args)
}

/** 打开或创建项目（Rust native，不依赖 Python sidecar） */
export async function openProject(
  root: string,
  name?: string,
): Promise<ProjectResponse> {
  dlog('[tauri-bridge] === openProject START ===')
  dlog('[tauri-bridge] Root:', root)
  dlog('[tauri-bridge] Name:', name)

  try {
    dlog('[tauri-bridge] Calling invoke("open_project", {...})')
    const response = await invoke<ProjectResponse>('open_project', {
      root,
      name: name ?? null,
    })
    dlog('[tauri-bridge] Response:', JSON.stringify(response, null, 2))
    dlog('[tauri-bridge] === openProject END ===')
    return response
  } catch (e: unknown) {
    const error = e instanceof Error ? e : undefined
    derr('[tauri-bridge] === openProject ERROR ===')
    derr('[tauri-bridge] Error:', error?.message || String(e))
    const msg = error?.message || String(e)
    return { success: false, error: msg }
  }
}

/** 项目文档条目 */
export interface DocumentEntry {
  doc_id: string
  path: string
  source_path?: string
  doc_type: string
  title: string
  indexed: boolean
  /** 规范化文件夹：papers / notes */
  folder?: string
  added_at: string
  hash: string
  mtime?: number
  inspector_status?: string
  text_status?: string
  ocr_status?: string
  ocr_hash?: string
  moldet_status?: string
  moldet_pages?: number[]
  index_status?: string
}

/** 扫描时发现的位置不合规文件 */
export interface ScanWarning {
  path: string
  reason: string
  folder: string
}

export interface ScanResponse {
  success: boolean
  documents: DocumentEntry[]
  new_documents?: DocumentEntry[]
  warnings: ScanWarning[]
}

/** 扫描项目文件 */
export async function scanProjectFiles(root: string): Promise<ScanResponse> {
  return invokeWithError(
    () => invoke<ScanResponse>('scan_project_files', { root }),
    ErrorCode.ProjectOpen,
  )
}

/** 列出项目文档 */
export async function listProjectDocuments(
  root: string,
  docType?: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invokeWithError(
    () => invoke('list_project_documents', { root, docType: docType ?? null }),
    ErrorCode.ProjectOpen,
  )
}

/** 完成状态字段（仅在带状态的列表里出现）。 */
export type IncompleteReason =
  | 'complete'
  | 'missing_text_md'
  | 'missing_report_md'
  | 'missing_both'

/** 文档 + 完成状态（`text.md` + `report.md` 都存在才算完成）。 */
export interface DocumentEntryWithStatus extends DocumentEntry {
  is_complete: boolean
  incomplete_reason: IncompleteReason
}

/** 列出项目文档，每项附带读取完成状态。
 *
 *  完成定义：`<project_root>/projects/<doc_id>/text.md` 与 `report.md`
 *  都存在。任一缺失 → `is_complete: false`，UI 应标「未完成」并提示
 *  用户重跑处理。
 */
export async function listProjectDocumentsWithStatus(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntryWithStatus[] }> {
  return invokeWithError(
    () => invoke('list_project_documents_with_status', { root }),
    ErrorCode.ProjectOpen,
  )
}

/** 单个文档的输出文件状态。 */
export interface DocumentOutputStatus {
  success: boolean
  doc_id: string
  text_md_path: string
  text_md_exists: boolean
  report_md_path: string
  report_md_exists: boolean
  complete: boolean
  incomplete_reason: IncompleteReason
}

/** 查询单个文档是否已生成 `text.md` + `report.md`。 */
export async function getDocumentOutputStatus(
  root: string,
  docId: string,
): Promise<DocumentOutputStatus> {
  return invoke<DocumentOutputStatus>('get_document_output_status', {
    root,
    docId,
  })
}

/** 文件树节点 */
export interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children: FileNode[]
}

/** 获取项目文件树 */
export async function getFileTree(
  root: string,
): Promise<{ success: boolean; tree: FileNode[] }> {
  return invokeWithError(
    () => invoke('get_file_tree', { root }),
    ErrorCode.ProjectOpen,
  )
}

/** 使用系统对话框导入文件到项目 */
export async function uploadFiles(projectRoot: string): Promise<DocumentEntry[]> {
  return invokeWithError(
    () => invoke<DocumentEntry[]>('upload_files', { projectRoot }),
    ErrorCode.ProjectOpen,
  )
}

/** 删除项目中的文件 */
export async function deleteFile(projectRoot: string, docId: string): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('delete_file', { projectRoot, docId }),
    ErrorCode.ProjectOpen,
  )
}

/** 彻底删除 PDF 文档及其所有派生数据。 */
export async function deleteDocument(projectRoot: string, docId: string): Promise<void> {
  return invokeWithError(
    () => invoke('project_delete_document', { projectRoot, docId }),
    ErrorCode.ProjectOpen,
  )
}

/** 重新读取已有 PDF：清空派生数据后重新入队。 */
export async function reingestDocument(projectRoot: string, docId: string): Promise<void> {
  return invokeWithError(
    () => invoke('project_reingest_document', { projectRoot, docId }),
    ErrorCode.ProjectOpen,
  )
}

/** 读取文本文件内容（Rust 直接读取，无需 HTTP） */
export async function readTextFile(projectRoot: string, path: string): Promise<string> {
  return invokeWithError(
    () => invoke<string>('read_text_file', { projectRoot, path }),
    ErrorCode.ProjectOpen,
  )
}

/** 将项目中所有未解析的 PDF 自动加入处理队列，返回实际入队数量。 */
export async function enqueueUnresolvedDocuments(root: string): Promise<number> {
  const resp = await invokeWithError(
    () => invoke<{ success: boolean; enqueued: number; skipped: number }>('enqueue_unresolved_documents', { root }),
    ErrorCode.ProjectOpen,
  )
  return resp.enqueued
}

/** 列出项目文档（与 client.ts listDocuments 兼容的包装） */
export async function listDocumentsTauri(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntry[]; error?: string }> {
  try {
    const resp = await listProjectDocuments(root)
    return { success: true, documents: resp.documents }
  } catch (e) {
    return { success: false, documents: [], error: String(e) }
  }
}
