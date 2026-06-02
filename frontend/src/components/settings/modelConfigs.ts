// 模型配置常量 - 按 Provider 分类

export const EMBED_MODELS: Record<string, { value: string; label: string }[]> = {
  qwen3: [
    { value: 'Qwen/Qwen3-Embedding-0.6B', label: 'Qwen3-Embedding-0.6B' },
  ],
  sentence_transformers: [
    { value: 'BAAI/bge-base-zh-v1.5', label: 'BGE-Base-ZH-v1.5' },
  ],
  openai: [
    { value: 'text-embedding-3-small', label: 'text-embedding-3-small' },
  ],
}

export const RERANK_MODELS: Record<string, { value: string; label: string }[]> = {
  qwen3: [
    { value: 'Qwen/Qwen3-Reranker-0.6B', label: 'Qwen3-Reranker-0.6B' },
  ],
  sentence_transformers: [
    { value: 'BAAI/bge-reranker-v2-m3', label: 'BGE-Reranker-v2-M3' },
  ],
}

export const LLM_MODELS: Record<string, { value: string; label: string }[]> = {
  openai_compatible: [
    { value: 'Qwen/Qwen2.5-7B-Instruct-GGUF', label: 'Qwen2.5-7B-Instruct' },
  ],
  anthropic: [
    { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
  ],
  ollama: [
    { value: 'qwen2.5:7b', label: 'Qwen2.5-7B' },
  ],
}

export const SETTING_SECTIONS = [
  { id: 'general', labelKey: 'settings.general', icon: 'settings' },
  { id: 'ai', labelKey: 'settings.ai', icon: 'settings' },
  { id: 'embedding', labelKey: 'settings.embedding', icon: 'settings' },
  { id: 'reranker', labelKey: 'settings.reranker', icon: 'settings' },
  { id: 'models', labelKey: 'settings.models', icon: 'download' },
  { id: 'environment', labelKey: 'settings.environment', icon: 'settings' },
  { id: 'appearance', labelKey: 'settings.appearance', icon: 'settings' },
  { id: 'server', labelKey: 'settings.server', icon: 'settings' },
  { id: 'about', labelKey: 'settings.about', icon: 'settings' },
] as const

export type Section = typeof SETTING_SECTIONS[number]['id']
