// 设置 Tauri 调用的前端封装。
//
// 字段命名与后端 `AppConfig` 保持一致（snake_case 节点），
// 拍平/映射逻辑在 `components/settings/types.ts` 里。

import { invoke } from '@tauri-apps/api/core'

export interface LlmConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model_name?: string
  max_tokens?: number
  temperature?: number
  top_p?: number
  request_timeout?: number
}

export interface EmbedConfig {
  provider?: string
  model_name?: string
  base_url?: string
  api_key?: string
  device?: 'cpu' | 'cuda' | 'auto'
  mrl_dim?: number | null
  instruction?: string
}

export interface RerankConfig {
  provider?: string
  model_name?: string
  device?: 'cpu' | 'cuda' | 'auto'
  max_length?: number
}

export interface VlmConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model_name?: string
}

export interface OcrConfig {
  provider?: string
  base_url?: string
  api_key?: string
  model_name?: string
  use_hf_mirror?: boolean
  use_pdf_inspector?: boolean
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
  embed?: EmbedConfig
  rerank?: RerankConfig
  vlm?: VlmConfig
  ocr?: OcrConfig
  model_server?: ModelServerConfig
  model_cache_dir?: string
  recent_projects?: string[]
}

export interface SettingsResponse {
  success: boolean
  settings?: AppSettings
  error?: string
}

export async function getSettings(): Promise<SettingsResponse> {
  try {
    const settings = await invoke<AppSettings>('get_settings')
    return { success: true, settings }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export async function saveSettings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }> {
  try {
    await invoke('save_settings', { settings })
    return { success: true }
  } catch (e) {
    return { success: false, error: String(e) }
  }
}

export interface BuildInfo {
  version: string
  tauri: string
  platform: string
  config_path: string
}

export async function fetchBuildInfo(): Promise<BuildInfo> {
  return invoke<BuildInfo>('app_build_info')
}

export async function exportSettings(targetPath: string): Promise<void> {
  await invoke('export_settings', { targetPath })
}

export async function resetSettings(): Promise<void> {
  await invoke('reset_settings')
}

export async function getConfigDir(): Promise<string> {
  return invoke<string>('config_dir_path')
}
