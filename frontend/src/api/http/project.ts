/**
 * Project→Library compat shim.
 *
 * After the project→library migration retired the legacy `/api/v1/project/*`
 * router chain, this module exposes the same surface area as the old
 * `project.ts` so existing importers keep compiling. Each function either
 * delegates to the corresponding `library.ts` helper or returns a graceful
 * "no equivalent" placeholder for endpoints that no longer exist
 * (e.g. `getCommonDirs`, `reingestDocument`).
 *
 * New code should use `library.ts` directly.
 */

import { httpGet, httpPost, invokeWithError } from './_utils'
import {
  configureLibrary,
  deleteDocument as deleteLibraryDocument,
  listDocuments as listLibraryDocuments,
} from './library'

// ── Compat: project/open → library/configure ────────────

export interface ProjectInfo {
  name: string
  root: string
  document_count: number
}

export type ProjectResponse =
  | { success: true; project: ProjectInfo }
  | { success: false; error: string }

/** Open project = configure library root (the only thing the legacy router
 * actually persisted on the backend). Document count reflects the unified store.
 */
export async function openProject(
  root: string,
  _name?: string,
): Promise<ProjectResponse> {
  try {
    const resp = await configureLibrary(root)
    if (!resp.success || !resp.root) {
      return { success: false, error: resp.error ?? 'configure failed' }
    }
    const { doc_count } = await invokeWithError(() =>
      httpGet<{ doc_count: number }>('/api/v1/library/status'),
    )
    const name = root.split(/[\\/]/).filter(Boolean).pop() ?? root
    return {
      success: true,
      project: { name, root: resp.root, document_count: doc_count },
    }
  } catch (e: unknown) {
    return { success: false, error: e instanceof Error ? e.message : String(e) }
  }
}

// ── Compat: project/common-dirs → returns empty (no backend equivalent) ──

export async function getCommonDirs(): Promise<{ name: string; path: string }[]> {
  // The library router does not expose common OS folders; the web frontend
  // has no native shell API to enumerate them either. Return empty so
  // FolderPicker falls back to manual entry.
  return []
}

// ── Compat: project/scan → no equivalent; use listDocuments ──────

export interface ScanWarning {
  path: string
  reason: string
  folder: string
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

export interface ScanResponse {
  success: boolean
  documents: DocumentEntry[]
  new_documents?: DocumentEntry[]
  warnings: ScanWarning[]
}

/** Legacy filesystem-walk endpoint — no equivalent in the library model.
 * Returns the documents that the library already knows about. */
export async function scanProjectFiles(
  _root: string,
  _recursive = false,
): Promise<ScanResponse> {
  const docs = await listDocumentsTauriWrapper()
  return {
    success: true,
    documents: docs.documents,
    warnings: [],
  }
}

// ── Compat: project/documents → listDocuments ────────────

export async function listProjectDocuments(
  _root: string,
  _docType?: string,
): Promise<{ success: boolean; documents: DocumentEntry[] }> {
  return listDocumentsTauriWrapper()
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
  _root: string,
): Promise<{ success: boolean; documents: DocumentEntryWithStatus[] }> {
  const r = await listDocumentsTauriWrapper()
  return {
    success: r.success,
    documents: r.documents.map(d => ({
      ...d,
      is_complete: false,
      incomplete_reason: 'complete' as IncompleteReason,
    })),
  }
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
  _root: string,
  docId: string,
): Promise<DocumentOutputStatus> {
  return {
    success: false,
    doc_id: docId,
    text_md_path: '',
    text_md_exists: false,
    report_md_path: '',
    report_md_exists: false,
    complete: false,
    incomplete_reason: 'missing_both',
  }
}

export async function getFileTree(
  _root: string,
): Promise<{ success: boolean; tree: never[] }> {
  // Tree building is a filesystem operation that the library router does
  // not expose. Return empty tree; UI should fall back to listing-only view.
  return { success: true, tree: [] }
}

export async function uploadFiles(_projectRoot: string): Promise<DocumentEntry[]> {
  // Web mode has no native file picker; the React UI uses its own uploader.
  return []
}

export async function deleteFile(
  _projectRoot: string,
  docId: string,
): Promise<boolean> {
  return invokeWithError(() => deleteLibraryDocument(docId))
    .then(() => true)
    .catch(() => false)
}

export async function deleteDocument(
  _projectRoot: string,
  docId: string,
): Promise<void> {
  await invokeWithError(() => deleteLibraryDocument(docId))
}

export async function reingestDocument(
  _projectRoot: string,
  _docId: string,
): Promise<void> {
  // No equivalent in library router; the pipeline trigger lives elsewhere.
  // Intentionally a no-op so existing callers don't crash.
}

export async function readTextFile(
  _projectRoot: string,
  path: string,
): Promise<string> {
  // The legacy `/api/v1/project/file-tree?action=read` endpoint no longer
  // exists. For paths under the dev server's public root we can still
  // fetch them; otherwise this throws and the caller's error path runs.
  const url = path.startsWith('/') || path.startsWith('http') ? path : `/${path}`
  const r = await fetch(url)
  if (!r.ok) throw new Error(`readTextFile ${path}: HTTP ${r.status}`)
  return await r.text()
}

export async function enqueueUnresolvedDocuments(_root: string): Promise<number> {
  // Library router does not expose this functionality yet. Returning 0 keeps
  // existing buttons no-op and toast-safe.
  return 0
}

export async function listDocumentsTauri(
  _root?: string,
): Promise<{ success: boolean; documents: DocumentEntry[]; error?: string }> {
  return listDocumentsTauriWrapper()
}

// ── Internal: map library.ts DocumentInfo → project.ts DocumentEntry ──

async function listDocumentsTauriWrapper(): Promise<{
  success: boolean
  documents: DocumentEntry[]
  error?: string
}> {
  try {
    const { documents } = await listLibraryDocuments()
    return {
      success: true,
      documents: documents.map(d => ({
        doc_id: d.doc_id,
        path: d.file_name,
        doc_type: '',
        title: d.title,
        indexed: d.status === 'indexed',
        added_at: d.created_at,
        hash: '',
      })),
    }
  } catch (e) {
    return { success: false, documents: [], error: String(e) }
  }
}
