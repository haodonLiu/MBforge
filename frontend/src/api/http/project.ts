/** Project management — open, scan, list, file tree, file operations. */

import { httpGet, httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'

/** 获取常用目录列表 */
export async function getCommonDirs(): Promise<{ name: string; path: string }[]> {
  try {
    const resp = await httpGet<{ dirs: { name: string; path: string }[] }>('/api/v1/project/common-dirs')
    return resp.dirs ?? []
  } catch {
    return []
  }
}

export interface ProjectInfo {
  name: string
  root: string
  document_count: number
}

export type ProjectResponse =
  | { success: true; project: ProjectInfo }
  | { success: false; error: string }

/** 打开或创建项目 */
export async function openProject(
  root: string,
  name?: string,
): Promise<ProjectResponse> {
  try {
    const resp = await httpPost<{ success: boolean; root: string; name: string; document_count: number }>(
      '/api/v1/project/open',
      { root, name: name ?? null },
    )
    if (resp.success) {
      return { success: true, project: { name: resp.name, root: resp.root, document_count: resp.document_count } }
    }
    return { success: false, error: 'open project failed' }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    return { success: false, error: msg }
  }
}

export interface DocumentEntry {
  doc_id: string
  path: string
  source_path?: string
  doc_type: string
  title: string
  indexed: boolean
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
export async function scanProjectFiles(root: string, recursive = false): Promise<ScanResponse> {
  return invokeWithError(
    () => httpPost<ScanResponse>('/api/v1/project/scan', { root, recursive }),
    ErrorCode.ProjectOpen,
  )
}

/** 列出项目文档 */
export async function listProjectDocuments(
  root: string,
  docType?: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invokeWithError(
    () => httpPost<{ success: boolean; documents: DocumentEntry[] }>('/api/v1/project/documents', {
      root,
      doc_type: docType ?? null,
    }),
    ErrorCode.ProjectOpen,
  )
}

export type IncompleteReason =
  | 'complete'
  | 'missing_text_md'
  | 'missing_report_md'
  | 'missing_both'

export interface DocumentEntryWithStatus extends DocumentEntry {
  is_complete: boolean
  incomplete_reason: IncompleteReason
}

export async function listProjectDocumentsWithStatus(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntryWithStatus[] }> {
  return invokeWithError(
    () => httpPost<{ success: boolean; documents: DocumentEntryWithStatus[] }>(
      '/api/v1/project/documents',
      { root, with_status: true },
    ),
    ErrorCode.ProjectOpen,
  )
}

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

export async function getDocumentOutputStatus(
  root: string,
  docId: string,
): Promise<DocumentOutputStatus> {
  return invokeWithError(
    () => httpPost<DocumentOutputStatus>('/api/v1/project/documents', {
      root,
      doc_id: docId,
      output_status: true,
    }),
    ErrorCode.ProjectOpen,
  )
}

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
    () => httpPost<{ success: boolean; tree: FileNode[] }>('/api/v1/project/file-tree', { root }),
    ErrorCode.ProjectOpen,
  )
}

/** 使用系统对话框导入文件到项目 */
export async function uploadFiles(projectRoot: string): Promise<DocumentEntry[]> {
  return invokeWithError(
    () => httpPost<{ success: boolean; documents: DocumentEntry[] }>('/api/v1/project/documents', {
      root: projectRoot,
    }),
    ErrorCode.ProjectOpen,
  ).then((r) => r.documents)
}

/** 删除项目中的文件 */
export async function deleteFile(projectRoot: string, docId: string): Promise<boolean> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean }>('/api/v1/project/documents', {
      root: projectRoot,
      action: 'delete',
      doc_id: docId,
    }),
    ErrorCode.ProjectOpen,
  )
  return resp.success
}

/** 彻底删除 PDF 文档及其所有派生数据。 */
export async function deleteDocument(projectRoot: string, docId: string): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/project/documents', {
      root: projectRoot,
      action: 'delete',
      doc_id: docId,
      deep: true,
    }),
    ErrorCode.ProjectOpen,
  )
}

/** 重新读取已有 PDF：清空派生数据后重新入队。 */
export async function reingestDocument(projectRoot: string, docId: string): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/project/documents', {
      root: projectRoot,
      action: 'reingest',
      doc_id: docId,
    }),
    ErrorCode.ProjectOpen,
  )
}

/** 读取文本文件内容 */
export async function readTextFile(projectRoot: string, path: string): Promise<string> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; content: string }>('/api/v1/project/file-tree', {
      root: projectRoot,
      action: 'read',
      path,
    }),
    ErrorCode.ProjectOpen,
  )
  return resp.content
}

/** 将项目中所有未解析的 PDF 自动加入处理队列，返回实际入队数量。 */
export async function enqueueUnresolvedDocuments(root: string): Promise<number> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; enqueued: number }>('/api/v1/pipeline/enqueue', {
      project_root: root,
      action: 'enqueue_unresolved',
    }),
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
