// 模型配置常量 - 按 Provider 分类。
//
// 这些只是 UI 下拉里的"建议值"，用户可以键入任意模型名（见
// `ModelSelector` 的自由文本实现）。这里列举的是各 provider 的主流
// 默认模型，方便快速选用。

export interface ModelOption {
  value: string
  label: string
}

export type ModelMap = Record<string, ModelOption[]>

export const LLM_MODELS: ModelMap = {
  openai_compatible: [
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
    { value: 'deepseek-chat', label: 'DeepSeek Chat' },
    { value: 'Qwen/Qwen2.5-7B-Instruct-GGUF', label: 'Qwen2.5-7B-Instruct (GGUF)' },
  ],
  anthropic: [
    { value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5' },
    { value: 'claude-opus-4-1', label: 'Claude Opus 4.1' },
    { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
  ],
  ollama: [
    { value: 'qwen2.5:7b', label: 'Qwen2.5 7B' },
    { value: 'llama3.1:8b', label: 'Llama 3.1 8B' },
    { value: 'gemma2:9b', label: 'Gemma 2 9B' },
  ],
}

export const EMBED_MODELS: ModelMap = {
  qwen3: [{ value: 'Qwen/Qwen3-Embedding-0.6B', label: 'Qwen3-Embedding-0.6B' }],
  sentence_transformers: [
    { value: 'BAAI/bge-base-zh-v1.5', label: 'BGE-Base-ZH-v1.5' },
    { value: 'BAAI/bge-large-zh-v1.5', label: 'BGE-Large-ZH-v1.5' },
  ],
  openai: [
    { value: 'text-embedding-3-small', label: 'text-embedding-3-small' },
    { value: 'text-embedding-3-large', label: 'text-embedding-3-large' },
  ],
}

export const RERANK_MODELS: ModelMap = {
  qwen3: [{ value: 'Qwen/Qwen3-Reranker-0.6B', label: 'Qwen3-Reranker-0.6B' }],
  sentence_transformers: [
    { value: 'BAAI/bge-reranker-v2-m3', label: 'BGE-Reranker-v2-M3' },
    { value: 'BAAI/bge-reranker-large', label: 'BGE-Reranker-Large' },
  ],
}

export const VLM_MODELS: ModelMap = {
  openai_compatible: [
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'gpt-4o-mini', label: 'GPT-4o mini' },
  ],
  anthropic: [{ value: 'claude-sonnet-4-5', label: 'Claude Sonnet 4.5' }],
  qwen_vl: [
    { value: 'Qwen/Qwen2-VL-7B-Instruct', label: 'Qwen2-VL-7B-Instruct' },
    { value: 'Qwen/Qwen2-VL-72B-Instruct', label: 'Qwen2-VL-72B-Instruct' },
  ],
}

export const OCR_MODELS: ModelMap = {
  paddle_ocr: [{ value: 'PaddleOCR-VL-0.9B', label: 'PaddleOCR-VL-0.9B' }],
  mineru: [{ value: 'MinerU-1.0', label: 'MinerU 1.0' }],
  dots_ocr: [{ value: 'dots.ocr', label: 'dots.ocr' }],
}

/** Provider 的可读标签 + 默认 placeholder URL（用于引导）。 */
export const PROVIDER_META: Record<string, { label: string; defaultUrl: string; needsKey: boolean }> = {
  // LLM
  openai_compatible: { label: 'OpenAI Compatible', defaultUrl: 'https://api.openai.com/v1', needsKey: true },
  anthropic: { label: 'Anthropic', defaultUrl: 'https://api.anthropic.com', needsKey: true },
  ollama: { label: 'Ollama (本地)', defaultUrl: 'http://localhost:11434', needsKey: false },
  // Embed
  qwen3: { label: 'Qwen3 (本地)', defaultUrl: '', needsKey: false },
  sentence_transformers: { label: 'Sentence Transformers (本地)', defaultUrl: '', needsKey: false },
  openai: { label: 'OpenAI (API)', defaultUrl: 'https://api.openai.com/v1', needsKey: true },
  // VLM
  qwen_vl: { label: 'Qwen-VL (本地)', defaultUrl: '', needsKey: false },
  // OCR
  paddle_ocr: { label: 'PaddleOCR (本地)', defaultUrl: '', needsKey: false },
  mineru: { label: 'MinerU (本地)', defaultUrl: '', needsKey: false },
  dots_ocr: { label: 'dots.ocr (本地)', defaultUrl: '', needsKey: false },
  // 通用
  none: { label: '不启用', defaultUrl: '', needsKey: false },
}
