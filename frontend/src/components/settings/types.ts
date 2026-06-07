// 设置面板 — 统一类型与默认值。
//
// 单一事实来源：所有 section 共享同一个 `SettingsState`，确保保存时
// 字段不会出现"漏存 / 写错路径"的问题。DEFAULT_SETTINGS 与后端
// `AppConfig::default()` (src-tauri/src/core/config/settings.rs) 保持对齐。

import type { AppSettings } from '../../api/settings'

/** 编辑中的扁平状态。所有字段以字符串/数字/布尔承载。 */
export interface SettingsState {
  // —— 常规 ——
  theme: 'dark' | 'light' | 'system'
  language: 'zh' | 'en'
  auto_open_project: boolean

  // —— LLM ——
  llm_provider: string
  llm_base_url: string
  llm_api_key: string
  llm_model: string
  llm_max_tokens: number
  llm_temperature: number
  llm_top_p: number
  llm_request_timeout: number

  // —— Embedding ——
  embed_provider: string
  embed_model: string
  embed_base_url: string
  embed_api_key: string
  embed_device: 'cpu' | 'cuda' | 'auto'
  embed_mrl_dim: number
  embed_instruction: string

  // —— Reranker ——
  rerank_provider: string
  rerank_model: string
  rerank_device: 'cpu' | 'cuda' | 'auto'
  rerank_max_length: number

  // —— VLM ——
  vlm_provider: string
  vlm_base_url: string
  vlm_api_key: string
  vlm_model: string

  // —— OCR ——
  ocr_provider: string
  ocr_base_url: string
  ocr_api_key: string
  ocr_model: string
  ocr_use_hf_mirror: boolean
  ocr_use_pdf_inspector: boolean

  // —— Model Service ——
  server_host: string
  server_port: number
  server_auto_start: boolean
  server_startup_timeout: number
  server_health_check_interval: number

  // —— Models ——
  model_cache_dir: string
}

export const DEFAULT_SETTINGS: SettingsState = {
  theme: 'dark',
  language: 'zh',
  auto_open_project: false,

  llm_provider: 'openai_compatible',
  llm_base_url: '',
  llm_api_key: '',
  llm_model: '',
  llm_max_tokens: 4096,
  llm_temperature: 0.7,
  llm_top_p: 0.9,
  llm_request_timeout: 120,

  embed_provider: 'qwen3',
  embed_model: 'Qwen/Qwen3-Embedding-0.6B',
  embed_base_url: '',
  embed_api_key: '',
  embed_device: 'cpu',
  embed_mrl_dim: 0,
  embed_instruction: '',

  rerank_provider: 'qwen3',
  rerank_model: 'Qwen/Qwen3-Reranker-0.6B',
  rerank_device: 'cpu',
  rerank_max_length: 8192,

  vlm_provider: 'none',
  vlm_base_url: '',
  vlm_api_key: '',
  vlm_model: '',

  ocr_provider: 'none',
  ocr_base_url: '',
  ocr_api_key: '',
  ocr_model: '',
  ocr_use_hf_mirror: true,
  ocr_use_pdf_inspector: true,

  server_host: '127.0.0.1',
  server_port: 18792,
  server_auto_start: true,
  server_startup_timeout: 120,
  server_health_check_interval: 5,

  model_cache_dir: '',
}

/** 栏目定义 — AI Models 合并了原 LLM/Embed/Rerank 与 VLM/OCR（视觉模型）。 */
export type SectionId =
  | 'general'
  | 'ai_models'
  | 'model_service'
  | 'model_downloads'
  | 'about'

export interface SectionDef {
  id: SectionId
  labelKey: string
  icon: 'settings' | 'download' | 'cpu' | 'flask' | 'info' | 'layout'
}

export const SECTIONS: SectionDef[] = [
  { id: 'general', labelKey: 'settings.general', icon: 'settings' },
  { id: 'ai_models', labelKey: 'settings.aiModels', icon: 'cpu' },
  { id: 'model_service', labelKey: 'settings.modelService', icon: 'layout' },
  { id: 'model_downloads', labelKey: 'settings.modelDownloads', icon: 'download' },
  { id: 'about', labelKey: 'settings.about', icon: 'info' },
]

/**
 * 把后端返回的 JSON 拍平到 SettingsState。缺失字段使用默认值。
 *
 * 注意：后端 `AppConfig` 的字段名是 camelCase（serde rename_all 不开），
 * 而我们内部字段是 snake_case — 显式写一层映射比依赖 serde rename 更安全。
 */
export function flattenSettings(raw: AppSettings | null | undefined): SettingsState {
  const s: AppSettings = raw ?? {}
  const llm = s.llm ?? {}
  const embed = s.embed ?? {}
  const rerank = s.rerank ?? {}
  const vlm = s.vlm ?? {}
  const ocr = s.ocr ?? {}
  const ms = s.model_server ?? {}
  return {
    theme: (s.theme as SettingsState['theme']) || DEFAULT_SETTINGS.theme,
    language: (s.language as SettingsState['language']) || DEFAULT_SETTINGS.language,
    auto_open_project: s.auto_open_project === true,

    llm_provider: llm.provider || DEFAULT_SETTINGS.llm_provider,
    llm_base_url: llm.base_url || DEFAULT_SETTINGS.llm_base_url,
    llm_api_key: llm.api_key || DEFAULT_SETTINGS.llm_api_key,
    llm_model: llm.model_name || DEFAULT_SETTINGS.llm_model,
    llm_max_tokens: llm.max_tokens || DEFAULT_SETTINGS.llm_max_tokens,
    llm_temperature: typeof llm.temperature === 'number' ? llm.temperature : DEFAULT_SETTINGS.llm_temperature,
    llm_top_p: typeof llm.top_p === 'number' ? llm.top_p : DEFAULT_SETTINGS.llm_top_p,
    llm_request_timeout: llm.request_timeout || DEFAULT_SETTINGS.llm_request_timeout,

    embed_provider: embed.provider || DEFAULT_SETTINGS.embed_provider,
    embed_model: embed.model_name || DEFAULT_SETTINGS.embed_model,
    embed_base_url: embed.base_url || DEFAULT_SETTINGS.embed_base_url,
    embed_api_key: embed.api_key || DEFAULT_SETTINGS.embed_api_key,
    embed_device: (embed.device as SettingsState['embed_device']) || DEFAULT_SETTINGS.embed_device,
    embed_mrl_dim: embed.mrl_dim || DEFAULT_SETTINGS.embed_mrl_dim,
    embed_instruction: embed.instruction || DEFAULT_SETTINGS.embed_instruction,

    rerank_provider: rerank.provider || DEFAULT_SETTINGS.rerank_provider,
    rerank_model: rerank.model_name || DEFAULT_SETTINGS.rerank_model,
    rerank_device: (rerank.device as SettingsState['rerank_device']) || DEFAULT_SETTINGS.rerank_device,
    rerank_max_length: rerank.max_length || DEFAULT_SETTINGS.rerank_max_length,

    vlm_provider: vlm.provider || DEFAULT_SETTINGS.vlm_provider,
    vlm_base_url: vlm.base_url || DEFAULT_SETTINGS.vlm_base_url,
    vlm_api_key: vlm.api_key || DEFAULT_SETTINGS.vlm_api_key,
    vlm_model: vlm.model_name || DEFAULT_SETTINGS.vlm_model,

    ocr_provider: ocr.provider || DEFAULT_SETTINGS.ocr_provider,
    ocr_base_url: ocr.base_url || DEFAULT_SETTINGS.ocr_base_url,
    ocr_api_key: ocr.api_key || DEFAULT_SETTINGS.ocr_api_key,
    ocr_model: ocr.model_name || DEFAULT_SETTINGS.ocr_model,
    ocr_use_hf_mirror: ocr.use_hf_mirror !== false,
    ocr_use_pdf_inspector: ocr.use_pdf_inspector !== false,

    server_host: ms.host || DEFAULT_SETTINGS.server_host,
    server_port: ms.port || DEFAULT_SETTINGS.server_port,
    server_auto_start: ms.auto_start !== false,
    server_startup_timeout: ms.startup_timeout || DEFAULT_SETTINGS.server_startup_timeout,
    server_health_check_interval: ms.health_check_interval || DEFAULT_SETTINGS.server_health_check_interval,

    model_cache_dir: s.model_cache_dir || DEFAULT_SETTINGS.model_cache_dir,
  }
}

/**
 * 把 SettingsState 拍平为后端 `save_settings` 期望的嵌套 JSON。
 * 关键不变量：保留所有节点（即使为空字符串），以便后端 merge
 * 能正确"清空"字段。
 */
export function toBackendPayload(s: SettingsState): Record<string, unknown> {
  return {
    theme: s.theme,
    language: s.language,
    auto_open_project: s.auto_open_project,
    llm: {
      provider: s.llm_provider,
      base_url: s.llm_base_url,
      api_key: s.llm_api_key,
      model_name: s.llm_model,
      max_tokens: s.llm_max_tokens,
      temperature: s.llm_temperature,
      top_p: s.llm_top_p,
      request_timeout: s.llm_request_timeout,
    },
    embed: {
      provider: s.embed_provider,
      model_name: s.embed_model,
      base_url: s.embed_base_url,
      api_key: s.embed_api_key,
      device: s.embed_device,
      mrl_dim: s.embed_mrl_dim || null,
      instruction: s.embed_instruction,
    },
    rerank: {
      provider: s.rerank_provider,
      model_name: s.rerank_model,
      device: s.rerank_device,
      max_length: s.rerank_max_length,
    },
    vlm: {
      provider: s.vlm_provider,
      base_url: s.vlm_base_url,
      api_key: s.vlm_api_key,
      model_name: s.vlm_model,
    },
    ocr: {
      provider: s.ocr_provider,
      base_url: s.ocr_base_url,
      api_key: s.ocr_api_key,
      model_name: s.ocr_model,
      use_hf_mirror: s.ocr_use_hf_mirror,
      use_pdf_inspector: s.ocr_use_pdf_inspector,
    },
    model_server: {
      host: s.server_host,
      port: s.server_port,
      auto_start: s.server_auto_start,
      startup_timeout: s.server_startup_timeout,
      health_check_interval: s.server_health_check_interval,
    },
    model_cache_dir: s.model_cache_dir,
  }
}

/** 浅比较 — 用 JSON.stringify 容易因字段顺序误报。 */
export function isSettingsEqual(a: SettingsState, b: SettingsState): boolean {
  const keys = Object.keys(a) as (keyof SettingsState)[]
  for (const k of keys) {
    if (a[k] !== b[k]) return false
  }
  return true
}
