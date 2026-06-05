import { invoke } from '@tauri-apps/api/core'

export interface AppSettings {
  theme?: string
  language?: string
  llm?: { provider?: string; base_url?: string; api_key?: string; model_name?: string; max_tokens?: number; temperature?: number; top_p?: number }
  embed?: { provider?: string; model_name?: string; device?: string; base_url?: string; api_key?: string }
  rerank?: { provider?: string; model_name?: string; device?: string; max_length?: number }
  vlm?: { provider?: string; base_url?: string; api_key?: string; model_name?: string }
  ocr?: { provider?: string; base_url?: string; api_key?: string; model_name?: string; use_hf_mirror?: boolean; use_pdf_inspector?: boolean }
  model_server?: { host?: string; port?: number; auto_start?: boolean; startup_timeout?: number; health_check_interval?: number }
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
