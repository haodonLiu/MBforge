/** Library API — unified document library (Zotero-style). */

import { httpGet, httpPost, invokeWithError } from './_utils'

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
  filePath: string,
  title?: string
): Promise<{ success: boolean; document?: DocumentInfo; error?: string; detail?: string }> {
  return invokeWithError(() =>
    httpPost('/api/v1/library/import', { file_path: filePath, title })
  )
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
