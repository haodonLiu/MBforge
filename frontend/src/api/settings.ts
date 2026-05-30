import { fetchJson } from './client'

const API_BASE = '/api/v1/settings'

export interface AppSettings {
  theme?: string
  language?: string
  llm?: { provider?: string; base_url?: string; api_key?: string; model_name?: string; max_tokens?: number; temperature?: number; top_p?: number }
  embed?: { provider?: string; model_name?: string; device?: string }
  rerank?: { provider?: string; model_name?: string }
  vlm?: { provider?: string; model_name?: string }
  model_cache_dir?: string
}

export interface SettingsResponse {
  success: boolean
  settings?: AppSettings
  error?: string
}

export function getSettings(): Promise<SettingsResponse> {
  return fetchJson(`${API_BASE}/`)
}

export function saveSettings(settings: Record<string, unknown>): Promise<{ success: boolean; error?: string }> {
  return fetchJson(`${API_BASE}/`, {
    method: 'POST',
    body: JSON.stringify({ settings }),
  })
}
