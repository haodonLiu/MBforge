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

// ============================================================================
// SMILES 结构校验（纯 Rust，通过 Tauri invoke）
// ============================================================================

import { invoke } from '@tauri-apps/api/core'

export interface ValidationIssue {
  code: string
  message: string
  severity: 'error' | 'warning'
}

export interface ValidateResponse {
  valid: boolean
  canonical_smiles: string | null
  issues: ValidationIssue[]
}

export function validateSmiles(smiles: string): Promise<ValidateResponse> {
  return invoke<ValidateResponse>('chem_validate_smiles', { smiles })
}
