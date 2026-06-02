/** Project management — open, scan, list, file tree, file operations. */

import { invoke } from '@tauri-apps/api/core'

export interface ProjectInfo {
  name: string
  root: string
  document_count: number
}

export interface ProjectResponse {
  success: boolean
  project?: ProjectInfo
  error?: string
}

/** 打开或创建项目（Rust native，不依赖 Python sidecar） */
export async function openProject(
  root: string,
  name?: string,
): Promise<ProjectResponse> {
  console.log('[tauri-bridge] === openProject START ===')
  console.log('[tauri-bridge] Root:', root)
  console.log('[tauri-bridge] Name:', name)

  try {
    console.log('[tauri-bridge] Calling invoke("open_project", {...})')
    const response = await invoke<ProjectResponse>('open_project', {
      root,
      name: name ?? null,
    })
    console.log('[tauri-bridge] Response:', JSON.stringify(response, null, 2))
    console.log('[tauri-bridge] === openProject END ===')
    return response
  } catch (e: unknown) {
    const error = e as Error
    console.error('[tauri-bridge] === openProject ERROR ===')
    console.error('[tauri-bridge] Error:', error?.message || String(e))
    const msg = error?.message || String(e) || 'Unknown invoke error'
    return { success: false, error: msg }
  }
}

/** 项目文档条目 */
export interface DocumentEntry {
  doc_id: string
  path: string
  doc_type: string
  title: string
  indexed: boolean
  added_at: string
  hash: string
}

/** 扫描项目文件 */
export async function scanProjectFiles(
  root: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invoke('scan_project_files', { root })
}

/** 列出项目文档 */
export async function listProjectDocuments(
  root: string,
  docType?: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return invoke('list_project_documents', { root, docType: docType ?? null })
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
  return invoke('get_file_tree', { root })
}

/** 使用系统对话框导入文件到项目 */
export async function uploadFiles(projectRoot: string): Promise<DocumentEntry[]> {
  return invoke<DocumentEntry[]>('upload_files', { projectRoot })
}

/** 删除项目中的文件 */
export async function deleteFile(projectRoot: string, docId: string): Promise<boolean> {
  return invoke<boolean>('delete_file', { projectRoot, docId })
}

/** 读取文本文件内容（Rust 直接读取，无需 HTTP） */
export async function readTextFile(projectRoot: string, path: string): Promise<string> {
  return invoke<string>('read_text_file', { projectRoot, path })
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
