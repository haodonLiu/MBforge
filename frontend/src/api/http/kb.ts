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
    () => httpPost<IndexResult>('/api/v1/pipeline/process', { project_root: root, file_path: '' }),
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
  projectRoot: string,
  query: string,
  topK = 5,
): Promise<KbSearchResult[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; results: KbSearchResult[] }>('/api/v1/kb/search', {
      project_root: projectRoot,
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
  projectRoot: string,
  query: string,
  topK: number,
  onChunk: (chunk: KbSearchChunk) => void,
): Promise<() => void> {
  const params = new URLSearchParams({
    query,
    top_k: String(topK),
    project_root: projectRoot,
  })
  return connectSSE(`/api/v1/kb/search/stream?${params}`, (event) => {
    const d = event.data
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
  projectRoot: string,
  docId: string,
): Promise<TreeNode[] | null> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; structure: TreeNode[] | null }>('/api/v1/kb/structure', {
      project_root: projectRoot,
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
  projectRoot: string,
  docId: string,
  pages: string,
): Promise<PageContent[]> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; pages: PageContent[] }>('/api/v1/kb/pages', {
      project_root: projectRoot,
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

export async function kbListWiki(projectRoot: string): Promise<WikiList> {
  const params = new URLSearchParams({ project_root: projectRoot })
  return invokeWithError(
    () => httpGet<WikiList>(`/api/v1/kb/wiki/list?${params}`),
    ErrorCode.ApiError,
  )
}

export function kbGetWikiSummary(
  docId: string,
  projectRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ project_root: projectRoot, doc_id: docId })
  return fetchWikiText(`/api/v1/kb/wiki/summary?${params}`)
}

export function kbGetWikiConcept(
  name: string,
  projectRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ project_root: projectRoot, name })
  return fetchWikiText(`/api/v1/kb/wiki/concept?${params}`)
}

export function kbGetWikiEntity(
  name: string,
  projectRoot: string
): Promise<string | null> {
  const params = new URLSearchParams({ project_root: projectRoot, name })
  return fetchWikiText(`/api/v1/kb/wiki/entity?${params}`)
}
