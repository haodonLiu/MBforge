const API_BASE = '/api/v1/download'

export interface DownloadModel {
  id: string
  name: string
  type: string
  description: string
  ms_repo: string
  downloaded: boolean
  downloading: boolean
  local_path: string
}

export async function listModels(): Promise<{ success: boolean; models: DownloadModel[] }> {
  const resp = await fetch(`${API_BASE}/models`)
  return resp.json()
}

export async function checkModelStatus(modelId: string) {
  const resp = await fetch(`${API_BASE}/status/${modelId}`)
  return resp.json()
}

export type ProgressEvent =
  | { status: 'connecting'; source: string; repo?: string }
  | { status: 'downloading'; progress?: number; file?: string; file_progress?: number; file_index?: number; total_files?: number; size?: number }
  | { status: 'completed'; source: string; files?: number }
  | { status: 'failed'; error: string }

export function downloadModel(
  modelId: string,
  onEvent: (event: ProgressEvent) => void,
): () => void {
  const controller = new AbortController()

  ;(async () => {
    try {
      const resp = await fetch(`${API_BASE}/download/${modelId}`, {
        method: 'POST',
        signal: controller.signal,
      })

      if (!resp.ok || !resp.body) {
        const err = await resp.json().catch(() => ({ error: `HTTP ${resp.status}` }))
        onEvent({ status: 'failed', error: err.error || `HTTP ${resp.status}` })
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
            try {
              const event = JSON.parse(line.slice(6)) as ProgressEvent
              onEvent(event)
            } catch { /* skip malformed */ }
          }
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        onEvent({ status: 'failed', error: String(e) })
      }
    }
  })()

  return () => controller.abort()
}
