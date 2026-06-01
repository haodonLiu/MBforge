import { fetchJson, sseStream } from './client'

const API_BASE = '/api/v1/download'
const RESOURCES_BASE = '/api/v1/resources'

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

// ===== 资源管理 API =====

export interface ResourceStatusItem {
  id: string
  name: string
  type: string
  status: string
  local_path: string
  size_mb: number
  version: string
  error: string
}

export interface EnvironmentReport {
  success: boolean
  python_version: string
  gpu_available: boolean
  gpu_name: string
  cuda_version: string
  summary: string
  resources: ResourceStatusItem[]
}

export interface ResourceCatalogItem {
  id: string
  name: string
  type: string
  description: string
  size_mb: number
  license: string
  ms_repo: string
  pip_name: string
}

export function checkResources(): Promise<EnvironmentReport> {
  return fetchJson(`${RESOURCES_BASE}/check`)
}

export function getResourceCatalog(): Promise<{ success: boolean; catalog: ResourceCatalogItem[] }> {
  return fetchJson(`${RESOURCES_BASE}/catalog`)
}

export function checkResourceStatus(resourceId: string): Promise<{ success: boolean; resource: ResourceStatusItem }> {
  return fetchJson(`${RESOURCES_BASE}/status/${encodeURIComponent(resourceId)}`)
}

export type ResourceProgressEvent =
  | { status: 'starting'; resource_id: string }
  | { status: 'skip'; resource_id: string; name: string; reason: string }
  | { status: 'ensuring'; resource_id: string; name: string }
  | { status: 'downloading'; progress?: number; file?: string; file_progress?: number }
  | { status: 'done'; resource_id: string; name: string; resource: ResourceStatusItem }
  | { status: 'failed'; resource_id: string; name?: string; error: string }
  | { status: 'finished'; summary: string }

export function ensureResource(
  resourceId: string,
  onEvent: (event: ResourceProgressEvent) => void,
): () => void {
  return sseStream<ResourceProgressEvent>(
    `${RESOURCES_BASE}/ensure/${encodeURIComponent(resourceId)}`,
    null,
    onEvent,
    (error) => onEvent({ status: 'failed', resource_id: resourceId, error }),
  )
}

export function ensureAllResources(
  onEvent: (event: ResourceProgressEvent) => void,
): () => void {
  return sseStream<ResourceProgressEvent>(
    `${RESOURCES_BASE}/ensure-all`,
    null,
    onEvent,
    (error) => onEvent({ status: 'failed', resource_id: 'all', error }),
  )
}
