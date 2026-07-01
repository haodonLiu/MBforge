export { ModelSelector, DownloadProgressBar, ModelCard, DownloadedModelItem } from './ModelComponents'
export { default as ModelsTab } from './ModelsTab'
export { default as SidecarCard } from './SidecarCard'
export {
  LLM_MODELS,
  VLM_MODELS,
  OCR_MODELS,
  PROVIDER_META,
} from './modelConfigs'
export type { ModelOption, ModelMap } from './modelConfigs'

// 栏目定义与状态类型已迁出 modelConfigs.ts（避免 modelConfigs.ts 被 settings UI 强耦合）。
export { SECTIONS, DEFAULT_SETTINGS, flattenSettings, toBackendPayload, isSettingsEqual } from './types'
export type { SettingsState, SectionId, SectionDef } from './types'
