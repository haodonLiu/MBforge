const API_BASE = '/api/v1'

export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
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
export type ChatStreamEvent = {
  delta: string
  finish_reason?: string
  error?: string
}

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

// Project (browser dev fallback — Tauri uses Rust native commands)
export function listDocuments(projectRoot: string) {
  return fetchJson<{ success: boolean; documents: import('../types').DocumentEntry[]; error?: string }>(
    `${API_BASE}/project/list?root=${encodeURIComponent(projectRoot)}`,
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

export interface MoleculeStats {
  total: number
  with_activity?: number
  pending?: number
}

export function moleculeStats(projectRoot: string) {
  return fetchJson<{ success: boolean; stats: MoleculeStats; error?: string }>(
    `${API_BASE}/molecule/stats?project_root=${encodeURIComponent(projectRoot)}`,
  )
}

// File Tree
export function getFileTree(projectRoot: string) {
  return fetchJson<{ success: boolean; tree: import('../types').FileNode[]; error?: string }>(
    `${API_BASE}/project/file-tree?root=${encodeURIComponent(projectRoot)}`,
  )
}

// File content (Markdown/TXT preview)
export function readFileContent(filePath: string, projectRoot?: string) {
  const params = new URLSearchParams({ path: filePath })
  if (projectRoot) params.set('project_root', projectRoot)
  return fetchJson<{ success: boolean; content: string; filename: string; error?: string }>(
    `${API_BASE}/file/content?${params.toString()}`,
  )
}

// File upload — DEV ONLY fallback for browser mode.
// Tauri mode uses `uploadFiles()` from tauri-bridge.ts (Rust native dialog + fs copy).
export function uploadFile(projectRoot: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  form.append('project_root', projectRoot)
  // Do NOT use fetchJson here — FormData requires browser-set multipart boundary.
  return (async () => {
    const resp = await fetch(`${API_BASE}/file/upload`, {
      method: 'POST',
      body: form,
    })
    if (!resp.ok) {
      const text = await resp.text()
      throw new Error(`HTTP ${resp.status}: ${text}`)
    }
    return resp.json() as Promise<{ success: boolean; doc_id?: string; path?: string; doc_type?: string; error?: string }>
  })()
}
// ============================================================================
// SAR (Structure-Activity Relationship) Analysis
// ============================================================================

export interface SARCompoundInput {
  id: string
  name: string
  smiles: string
  activity?: number | null
  activity_type?: string | null
  units?: string | null
}

export interface RGroupMatrix {
  core_smiles: string
  r_labels: string[]
  rows: string[][]
  compounds: Array<Record<string, unknown> & { id: string; name: string; smiles: string; matches: boolean }>
  unmatched_count: number
}

export interface RGroupMatrixResponse {
  success: boolean
  core_smiles?: string
  r_labels?: string[]
  rows?: string[][]
  compounds?: RGroupMatrix['compounds']
  unmatched_count?: number
  error?: string
}

export interface ActivityHeatmapCell {
  substituent_smiles: string
  avg_activity: number
  count: number
  min: number
  max: number
}

export interface ActivityHeatmapEntry {
  r_label: string
  cells: ActivityHeatmapCell[]
}

export interface ActivityHeatmapResponse {
  success: boolean
  heatmaps: ActivityHeatmapEntry[]
  error?: string
}

export function buildRGroupMatrix(
  compounds: SARCompoundInput[],
  core_smiles?: string,
  auto_extract_scaffold = true,
): Promise<RGroupMatrixResponse> {
  return fetchJson<RGroupMatrixResponse>(`${API_BASE}/sar/matrix`, {
    method: 'POST',
    body: JSON.stringify({
      compounds,
      core_smiles: core_smiles ?? null,
      auto_extract_scaffold,
    }),
  })
}

export function buildActivityHeatmap(
  matrix: RGroupMatrix,
  lower_is_better = true,
): Promise<ActivityHeatmapResponse> {
  return fetchJson<ActivityHeatmapResponse>(`${API_BASE}/sar/heatmap`, {
    method: 'POST',
    body: JSON.stringify({ matrix, lower_is_better }),
  })
}

export function extractScaffold(smiles_list: string[]) {
  return fetchJson<{ success: boolean; core_smiles: string | null; error?: string }>(
    `${API_BASE}/sar/scaffold`,
    {
      method: 'POST',
      body: JSON.stringify({ smiles_list }),
    },
  )
}

