const API_BASE = '/api/v1'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json() as Promise<T>
}

// SSE 流式工具 — 消费服务端推送的 data: JSON 行
export function sseStream<T>(
  url: string,
  body: unknown,
  onEvent: (event: T) => void,
  onError?: (error: string) => void,
): () => void {
  const controller = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body != null ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        onError?.(`HTTP ${resp.status}`)
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
          }
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        onError?.(String(e))
      }
    }
  })()
  return () => controller.abort()
}

// Health
export function getHealth() {
  return fetchJson<import('../types').HealthResponse>(`${API_BASE}/health`)
}

// LLM streaming
export type ChatStreamEvent =
  | { delta: string; finish_reason?: string }
  | { delta: string; finish_reason: string; error?: string }

export function chatStream(
  messages: { role: string; content: string }[],
  onEvent: (event: ChatStreamEvent) => void,
  temperature = 0.7,
  maxTokens = 4096,
): () => void {
  return sseStream<ChatStreamEvent>(
    `${API_BASE}/llm/chat-stream`,
    { messages, temperature, max_tokens: maxTokens },
    onEvent,
    (error) => onEvent({ delta: '', finish_reason: 'error', error }),
  )
}

// Project
export function createProject(root: string, name = '') {
  return fetchJson<{ success: boolean; project: import('../types').Project; error?: string }>(
    `${API_BASE}/project/create`,
    { method: 'POST', body: JSON.stringify({ root, name }) },
  )
}

export function openProject(root: string, name = '') {
  return fetchJson<{ success: boolean; project: import('../types').Project; error?: string }>(
    `${API_BASE}/project/open`,
    { method: 'POST', body: JSON.stringify({ root, name }) },
  )
}

export function listDocuments(projectRoot: string) {
  return fetchJson<{ success: boolean; documents: import('../types').DocumentEntry[]; error?: string }>(
    `${API_BASE}/project/list?root=${encodeURIComponent(projectRoot)}`,
  )
}

export function scanProject(projectRoot: string) {
  return fetchJson<{ success: boolean; documents: import('../types').DocumentEntry[]; error?: string }>(
    `${API_BASE}/project/scan`,
    { method: 'POST', body: JSON.stringify({ root: projectRoot }) },
  )
}

export type IndexProgressEvent =
  | { status: 'indexing'; file: string; current: number; total: number }
  | { status: 'file_done'; file: string; molecules: number }
  | { status: 'file_error'; file: string; error: string }
  | { status: 'completed'; indexed: number; molecules: number; total: number }
  | { status: 'error'; error: string }

export function indexProjectStream(
  root: string,
  onEvent: (event: IndexProgressEvent) => void,
): () => void {
  return sseStream<IndexProgressEvent>(
    `${API_BASE}/project/index-stream`,
    { root },
    onEvent,
    (error) => onEvent({ status: 'error', error }),
  )
}

// Knowledge Base
export function kbSearch(projectRoot: string, query: string, topK = 5) {
  return fetchJson<{ success: boolean; results: import('../types').SearchResult[]; error?: string }>(
    `${API_BASE}/kb/search`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, query, top_k: topK }) },
  )
}

// Molecule
export function listMolecules(projectRoot: string, limit = 100, offset = 0) {
  return fetchJson<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }>(
    `${API_BASE}/molecule/list?project_root=${encodeURIComponent(projectRoot)}&limit=${limit}&offset=${offset}`,
  )
}

export function searchMolecules(projectRoot: string, q: string, limit = 20) {
  return fetchJson<{ success: boolean; molecules: import('../types').MoleculeRecord[]; error?: string }>(
    `${API_BASE}/molecule/search?project_root=${encodeURIComponent(projectRoot)}&q=${encodeURIComponent(q)}&limit=${limit}`,
  )
}

export function moleculeStats(projectRoot: string) {
  return fetchJson<{ success: boolean; stats: Record<string, unknown>; error?: string }>(
    `${API_BASE}/molecule/stats?project_root=${encodeURIComponent(projectRoot)}`,
  )
}

// Agent
export function getChatHistory(projectRoot: string) {
  return fetchJson<{ success: boolean; messages: import('../types').ChatMessage[] }>(
    `${API_BASE}/agent/history?project_root=${encodeURIComponent(projectRoot)}`,
  )
}

export function agentChat(projectRoot: string, messages: { role: string; content: string }[], temperature = 0.7) {
  return fetchJson<{ success: boolean; content: string; error?: string }>(
    `${API_BASE}/agent/chat`,
    { method: 'POST', body: JSON.stringify({ project_root: projectRoot, messages, temperature }) },
  )
}

export type AgentChatStreamEvent =
  | { delta: string; finish_reason?: string }
  | { delta: string; finish_reason: string; error?: string }

export function agentChatStream(
  projectRoot: string,
  messages: { role: string; content: string }[],
  onEvent: (event: AgentChatStreamEvent) => void,
  temperature = 0.7,
): () => void {
  const controller = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(`${API_BASE}/agent/chat-stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_root: projectRoot, messages, temperature }),
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        onEvent({ delta: '', finish_reason: 'error', error: `HTTP ${resp.status}` })
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
          }
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        onEvent({ delta: '', finish_reason: 'error', error: String(e) })
      }
    }
  })()
  return () => controller.abort()
}

// File Tree
export function getFileTree(projectRoot: string) {
  return fetchJson<{ success: boolean; tree: import('../types').FileNode[]; error?: string }>(
    `${API_BASE}/project/file-tree?root=${encodeURIComponent(projectRoot)}`,
  )
}

// File upload
export function uploadFile(projectRoot: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('project_root', projectRoot)
  return fetchJson<{ success: boolean; doc_id?: string; path?: string; doc_type?: string; error?: string }>(
    `${API_BASE}/file/upload`,
    { method: 'POST', body: form },
  )
}

// ---- Tauri-wrapped Rust commands ----
import {
  isTauriAvailable,
  classifyPdf as tauriClassifyPdf,
  extractText as tauriExtractText,
  type PdfClassification,
  type PdfExtraction,
} from './tauri-bridge'

export async function classifyPdfRust(path: string): Promise<PdfClassification> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriClassifyPdf(path)
}

export async function extractTextRust(path: string): Promise<PdfExtraction> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriExtractText(path)
}

// ---- pipeline Rust commands ----
import {
  parsePdf as tauriParsePdf,
  postProcessPdf as tauriPostProcessPdf,
  processDocument as tauriProcessDocument,
  type PdfParseResult,
  type PostProcessResult,
  type DocProgressEvent,
  type DocumentReport,
} from './tauri-bridge'

export async function parsePdfRust(
  path: string,
  chunkSize?: number,
  overlap?: number,
  parser?: string,
): Promise<PdfParseResult> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriParsePdf(path, chunkSize, overlap, parser)
}

export async function postProcessPdfRust(
  parseResult: PdfParseResult,
): Promise<PostProcessResult> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')
  return tauriPostProcessPdf(parseResult)
}

export async function processDocumentRust(
  path: string,
  userRequest?: string,
  onProgress?: (event: DocProgressEvent) => void,
): Promise<DocumentReport> {
  if (!isTauriAvailable()) throw new Error('Not in Tauri')

  const { listen } = await import('@tauri-apps/api/event')
  return new Promise((resolve, reject) => {
    const unlistenList: (() => void)[] = []

    listen<DocProgressEvent>('doc-progress', (event) => {
      onProgress?.(event.payload)
    }).then((fn) => unlistenList.push(fn))

    listen<DocumentReport>('doc-result', (event) => {
      unlistenList.forEach((fn) => fn())
      resolve(event.payload)
    }).then((fn) => unlistenList.push(fn))

    listen<string>('doc-error', (event) => {
      unlistenList.forEach((fn) => fn())
      reject(new Error(event.payload))
    }).then((fn) => unlistenList.push(fn))

    tauriProcessDocument(path, userRequest).catch((err) => {
      unlistenList.forEach((fn) => fn())
      reject(err)
    })
  })
}
