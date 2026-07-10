/** Knowledge base — indexing, semantic search, document structure & pages. */

import { httpGet, httpGetText, httpPost, invokeWithError, AppError } from './_utils'
import { ErrorCode } from '@/utils/errors'
import { connectSSE } from './sse'

export interface IndexResult {
  indexed: number
  sections: number
  errors: string[]
}

export async function indexProject(root: string): Promise<IndexResult> {
  return invokeWithError(
    () => httpPost<IndexResult>('/api/v1/pipeline/process', { library_root: root, file_path: '' }),
    ErrorCode.ApiError,
  )
}

export interface KbSearchResult {
  id: string
  text: string
  metadata: Record<string, unknown>
  score: number
}

export async function kbSearch(
  libraryRoot: string,
  query: string,
  topK = 5,
): Promise<KbSearchResult[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: KbSearchResult[] }>('/api/v1/kb/search', {
      library_root: libraryRoot,
      query,
      top_k: topK,
    }),
    ErrorCode.ApiError,
  )
  return resp.results
}

export interface KbSearchChunk {
  type: 'first' | 'incremental' | 'complete'
  results: KbSearchResult[]
  count: number
  error: string | null
}

export function kbSearchStream(
  libraryRoot: string,
  query: string,
  topK: number,
  onChunk: (chunk: KbSearchChunk) => void,
): () => void {
  const params = new URLSearchParams({
    query,
    top_k: String(topK),
    library_root: libraryRoot,
  })
  return connectSSE(`/api/v1/kb/search/stream?${params}`, (event) => {
    const d = event.data as {
      type?: string
      error?: string
      total?: number
      count?: number
      results?: KbSearchResult[]
    }
    if (d.type === 'error') {
      onChunk({ type: 'complete', results: [], count: 0, error: d.error ?? 'search error' })
    } else if (d.type === 'done') {
      onChunk({ type: 'complete', results: [], count: d.total ?? 0, error: null })
    } else {
      onChunk({
        type: d.type === 'results' ? 'incremental' : 'first',
        results: d.results ?? [],
        count: d.count ?? 0,
        error: null,
      })
    }
  })
}

export interface TreeNode {
  title: string
  node_id: string
  line_num: number
  nodes: TreeNode[]
}

export async function kbGetStructure(
  libraryRoot: string,
  docId: string,
): Promise<TreeNode[] | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; structure: TreeNode[] | null }>('/api/v1/kb/structure', {
      library_root: libraryRoot,
      doc_id: docId,
    }),
    ErrorCode.ApiError,
  )
  return resp.structure
}

export interface PageContent {
  page: number
  content: string
}

export async function kbGetPages(
  libraryRoot: string,
  docId: string,
  pages: string,
): Promise<PageContent[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; pages: PageContent[] }>('/api/v1/kb/pages', {
      library_root: libraryRoot,
      doc_id: docId,
      pages,
    }),
    ErrorCode.ApiError,
  )
  return resp.pages
}

// ── Wiki artifacts (used by DocumentViewer's WikiDrawer) ───────────

export interface WikiList {
  summaries: string[]
  concepts: string[]
  entities: string[]
}

async function fetchWikiText(url: string): Promise<string | null> {
  try {
    return await httpGetText(url)
  } catch (e) {
    const appErr = e instanceof AppError ? e : new AppError(ErrorCode.ApiError, String(e))
    if (appErr.context?.http_status === 404) return null
    throw appErr
  }
}

export async function kbListWiki(libraryRoot: string): Promise<WikiList> {
  const params = new URLSearchParams({ library_root: libraryRoot })
  return invokeWithError(
    () => httpGet<WikiList>(`/api/v1/kb/wiki/list?${params}`),
    ErrorCode.ApiError,
  )
}

export function kbGetWikiSummary(
  docId: string,
  libraryRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ library_root: libraryRoot, doc_id: docId })
  return fetchWikiText(`/api/v1/kb/wiki/summary?${params}`)
}

export function kbGetWikiConcept(
  name: string,
  libraryRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ library_root: libraryRoot, name })
  return fetchWikiText(`/api/v1/kb/wiki/concept?${params}`)
}

export function kbGetWikiEntity(
  name: string,
  libraryRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ library_root: libraryRoot, name })
  return fetchWikiText(`/api/v1/kb/wiki/entity?${params}`)
}
