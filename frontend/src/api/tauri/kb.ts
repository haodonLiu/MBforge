/** Knowledge base — indexing, semantic search, document structure & pages. */

import { EVT } from '../tauri-events'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface IndexResult {
  indexed: number
  sections: number
  errors: string[]
}

export async function indexProjectRust(root: string): Promise<IndexResult> {
  try {
    return await invoke<IndexResult>('index_project_rust', { root })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    // Tauri v2 on Windows sometimes has transient IPC protocol failures
    if (msg.includes('ipc.localhost') || msg.includes('ERR_CONNECTION_REFUSED') || msg.includes('Failed to fetch')) {
      console.warn('[tauri-bridge] IPC transport failure, retrying once...')
      await new Promise(r => setTimeout(r, 500))
      return invoke<IndexResult>('index_project_rust', { root })
    }
    throw e
  }
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
  return invokeWithError(
    () => invoke<KbSearchResult[]>('kb_search', { root: projectRoot, query, top_k: topK }),
    ErrorCode.ApiError,
  )
}

export interface KbSearchChunk {
  type: 'first' | 'incremental' | 'complete'
  results: KbSearchResult[]
  count: number
  error: string | null
}

/** 流式搜索 — 通过 Tauri 事件分批接收结果 */
export async function kbSearchStream(
  projectRoot: string,
  query: string,
  topK: number,
  onChunk: (chunk: KbSearchChunk) => void,
): Promise<() => void> {
  invokeWithError(
    () => invoke('kb_search_stream', { root: projectRoot, query, top_k: topK }),
    ErrorCode.ApiError,
  ).catch((err: unknown) => {
    onChunk({ type: 'complete', results: [], count: 0, error: String(err) })
  })

  const unlisten = await listen<KbSearchChunk>(EVT.KbSearchChunk, (event) => {
    onChunk(event.payload)
  })

  return unlisten
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
  return invokeWithError(
    () => invoke<TreeNode[] | null>('kb_get_structure', { root: projectRoot, doc_id: docId }),
    ErrorCode.ApiError,
  )
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
  return invokeWithError(
    () => invoke<PageContent[]>('kb_get_pages', { root: projectRoot, doc_id: docId, pages }),
    ErrorCode.ApiError,
  )
}
