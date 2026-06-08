import { fetchJson, sseStream } from './http'

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
  license: string
  license_url: string
  size_mb: number
  source_url: string
}

export interface DownloadedModel {
  id: string
  name: string
  path: string
  size_mb: number
  type: string
  in_catalog: boolean
}

export function listModels(): Promise<{ success: boolean; models: DownloadModel[] }> {
  return fetchJson(`${API_BASE}/models`)
}

export function getModelDir(): Promise<{ success: boolean; model_dir: string }> {
  return fetchJson(`${API_BASE}/model-dir`)
}

export function listDownloaded(): Promise<{ success: boolean; models: DownloadedModel[]; model_dir: string }> {
  return fetchJson(`${API_BASE}/list-downloaded`)
}

export function deleteModel(modelId: string): Promise<{ success: boolean; deleted?: string; error?: string }> {
  return fetchJson(`${API_BASE}/delete/${encodeURIComponent(modelId)}`, {
    method: 'DELETE',
  })
}

export function checkModelStatus(modelId: string) {
  return fetchJson(`${API_BASE}/status/${modelId}`)
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
