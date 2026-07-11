/** Settings HTTP API wrappers. */

import { httpGet, httpPut } from './_utils'

export interface LlmConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model?: string
  max_tokens?: number
  temperature?: number
  top_p?: number
  request_timeout?: number
}

export interface VlmConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model?: string
}

export interface OcrConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model?: string
  use_hf_mirror?: boolean
  use_pdf_inspector?: boolean
  mineru_api_key?: string | null
  paddleocr_api_key?: string | null
  paddleocr_host?: string | null
  paddleocr_model?: string | null
  glmocr_api_key?: string | null
  glmocr_model?: string | null
  upload_batch_size?: number
}

export interface ModelServerConfig {
  host?: string
  port?: number
  auto_start?: boolean
  startup_timeout?: number
  health_check_interval?: number
}

export interface AppSettings {
  theme?: string
  language?: string
  auto_open_project?: boolean
  llm?: LlmConfig
  vlm?: VlmConfig
  ocr?: OcrConfig
  model_server?: ModelServerConfig
  model_cache_dir?: string
  recent_projects?: string[]
  pdf_parse?: PdfParseConfig
  moldet?: MoldetConfig
  ingest?: IngestConfig
  popo?: PopoConfig
}

export interface PdfParseConfig {
  chunk_size?: number
  chunk_overlap?: number
}

export interface PopoConfig {
  enabled?: boolean
}

export interface MoldetConfig {
  auto_moldet_on_import?: boolean
  moldet_batch_size?: number
  detection_dpi?: number
  detection_batch_size?: number
}

export interface IngestConfig {
  auto_enqueue_on_import?: boolean
}

export interface SettingsResponse {
  success: boolean
  settings?: AppSettings
  error?: string
}

export async function getSettings(): Promise<SettingsResponse> {
  try {
    const resp = await httpGet<{ success: boolean; settings: AppSettings }>('/api/v1/settings')
    return { success: true, settings: resp.settings }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function saveSettings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }> {
  try {
    await httpPut('/api/v1/settings', settings)
    return { success: true }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export interface BuildInfo {
  version: string
  platform: string
  config_path: string
}

export function fetchBuildInfo(): BuildInfo {
  return { version: '0.4.0', platform: navigator.platform, config_path: '' }
}

export async function exportSettings(_targetPath: string): Promise<void> {
  const settings = await getSettings()
  if (settings.settings) {
    const blob = new Blob([JSON.stringify(settings.settings, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mbforge-settings.json'
    a.click()
    URL.revokeObjectURL(url)
  }
}

export async function resetSettings(): Promise<void> {
  await httpPut('/api/v1/settings', {})
}

export function getConfigDir(): Promise<string> {
  return Promise.resolve('/config')
}
