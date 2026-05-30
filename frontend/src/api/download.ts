import { sseStream } from './client'

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
  return sseStream<ProgressEvent>(
    `${API_BASE}/download/${modelId}`,
    null,
    onEvent,
    (error) => onEvent({ status: 'failed', error }),
  )
}
