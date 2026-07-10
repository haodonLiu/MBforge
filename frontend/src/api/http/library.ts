/** Library API — unified document library (Zotero-style). */

import { httpGet, httpGetText, httpPost, invokeWithError, getErrorMessage } from './_utils'

// ── Types ───────────────────────────────────────────

export interface DocumentInfo {
  doc_id: string
  title: string
  file_name: string
  page_count: number
  status: string
  created_at: string
}

export interface CollectionInfo {
  collection_id: string
  name: string
  parent_id: string | null
  doc_count: number
}

export interface CollectionNode extends CollectionInfo {
  children: CollectionNode[]
}

export interface LibraryStatus {
  configured: boolean
  root: string
  doc_count: number
}

// ── Status ──────────────────────────────────────────

export async function getLibraryStatus(): Promise<LibraryStatus> {
  return invokeWithError(() => httpGet<LibraryStatus>('/api/v1/library/status'))
}

// ── Documents ───────────────────────────────────────

export async function importDocument(
  file: File,
  title?: string
): Promise<{ success: boolean; document?: DocumentInfo; error?: string; detail?: string }> {
  const fd = new FormData()
  fd.append('file', file, file.name)
  if (title) fd.append('title', title)
  const resp = await fetch('/api/v1/library/import', { method: 'POST', body: fd })
  return (await resp.json()) as { success: boolean; document?: DocumentInfo; error?: string; detail?: string }
}

export async function listDocuments(
  collectionId?: string
): Promise<{ documents: DocumentInfo[] }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/documents', { collection_id: collectionId })
  )
}

export async function deleteDocument(
  docId: string
): Promise<{ success: boolean }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/documents/delete', { doc_id: docId })
  )
}

// ── Collections ─────────────────────────────────────

export async function createCollection(
  name: string,
  parentId?: string
): Promise<{ success: boolean; collection?: CollectionInfo; error?: string }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/collections/create', { name, parent_id: parentId })
  )
}

export async function listCollections(): Promise<{ collections: CollectionNode[] }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/collections/list', {})
  )
}

export async function deleteCollection(
  collectionId: string
): Promise<{ success: boolean }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/collections/delete', { collection_id: collectionId })
  )
}

export async function addDocumentToCollection(
  collectionId: string,
  docId: string
): Promise<{ success: boolean }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/collections/add-document', {
      collection_id: collectionId,
      doc_id: docId,
    })
  )
}

export async function removeDocumentFromCollection(
  collectionId: string,
  docId: string
): Promise<{ success: boolean }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/collections/remove-document', {
      collection_id: collectionId,
      doc_id: docId,
    })
  )
}

// ── Configuration ───────────────────────────────────

export async function configureLibrary(
  root: string
): Promise<{ success: boolean; root?: string; error?: string }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/configure', { root })
  )
}

// ── Pipeline artifacts (used by DocumentViewer) ───────────

function artifactUrl(path: string, libraryRoot: string, extraParams?: Record<string, string>): string {
  const params = new URLSearchParams({ library_root: libraryRoot })
  if (extraParams) {
    for (const [k, v] of Object.entries(extraParams)) {
      params.set(k, v)
    }
  }
  return `/api/v1/library${path}?${params.toString()}`
}

export async function fetchReorganizedMarkdown(
  docId: string,
  libraryRoot: string
): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  try {
    const text = await httpGetText(artifactUrl(`/documents/${encodeURIComponent(docId)}/reorganized`, libraryRoot))
    return { ok: true, text }
  } catch (e) {
    return { ok: false, error: getErrorMessage(e) }
  }
}

export async function fetchReportJson<T = unknown>(
  docId: string,
  libraryRoot: string
): Promise<{ ok: true; data: T } | { ok: false; error: string }> {
  try {
    const data = await httpGet<T>(artifactUrl(`/documents/${encodeURIComponent(docId)}/report`, libraryRoot))
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: getErrorMessage(e) }
  }
}

export function cropImageUrl(docId: string, relPath: string, libraryRoot: string): string {
  return artifactUrl(
    `/documents/${encodeURIComponent(docId)}/crop`,
    libraryRoot,
    { rel_path: relPath }
  )
}

export async function fetchIndexedMarkdown(
  docId: string,
  libraryRoot: string
): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  try {
    const text = await httpGetText(artifactUrl(`/documents/${encodeURIComponent(docId)}/indexed-md`, libraryRoot))
    return { ok: true, text }
  } catch (e) {
    return { ok: false, error: getErrorMessage(e) }
  }
}

export async function fetchPageText(
  docId: string,
  page: number,
  libraryRoot: string
): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  try {
    const text = await httpGetText(artifactUrl(`/documents/${encodeURIComponent(docId)}/pages/${page}`, libraryRoot))
    return { ok: true, text }
  } catch (e) {
    return { ok: false, error: getErrorMessage(e) }
  }
}
