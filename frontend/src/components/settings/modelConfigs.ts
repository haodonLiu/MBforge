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
  none: [{ value: '', label: 'Off' }],
  mineru: [{ value: 'pipeline', label: 'pipeline (default)' }, { value: 'vlm', label: 'vlm (recommended)' }],
  paddle_ocr: [{ value: 'PaddleOCR-VL-1.6', label: 'PaddleOCR-VL-1.6 (local)' }],
  paddleocr_online: [{ value: 'PaddleOCR-VL-1.6', label: 'PaddleOCR-VL-1.6 (AIStudio Cloud)' }],
}

/** Provider 的可读标签 + 默认 placeholder URL（用于引导）。 */
export const PROVIDER_META: Record<string, { label: string; defaultUrl: string; needsKey: boolean }> = {
  // LLM
  openai_compatible: { label: 'OpenAI Compatible', defaultUrl: 'https://api.openai.com/v1', needsKey: true },
  anthropic: { label: 'Anthropic', defaultUrl: 'https://api.anthropic.com', needsKey: true },
  ollama: { label: 'Ollama (local)', defaultUrl: 'http://localhost:11434', needsKey: false },
  // VLM
  qwen_vl: { label: 'Qwen-VL (local)', defaultUrl: '', needsKey: false },
  // OCR
  none: { label: 'Off', defaultUrl: '', needsKey: false },
  mineru: { label: 'MinerU (Cloud)', defaultUrl: 'https://mineru.net/', needsKey: true },
  paddle_ocr: { label: 'PaddleOCR (local)', defaultUrl: '', needsKey: false },
  paddleocr_online: { label: 'PaddleOCR AIStudio (Cloud)', defaultUrl: 'https://aistudio.baidu.com/paddleocr', needsKey: true },
}
