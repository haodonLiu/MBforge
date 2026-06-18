# AI 模型设置页风格统一与可编辑设计

**Date:** 2026-06-17  
**Scope:** MBForge frontend settings + Rust backend config/runtime  
**Status:** Approved

---

## 1. Background

当前设置中 AI Models 标签下包含 5 个子页：LLM、Embedding、Reranker、VLM、OCR。它们的视觉风格不一致：

- LLM 页是只读状态卡片（`LlmStatusCard`），显示从 `.env` 读取的环境变量，用户无法编辑。
- Embedding / Reranker / VLM / OCR 使用统一的横向表单行（`SettingRow` + `SettingGroup`），已经可编辑并保存到 `config.json`。

用户希望：
1. 统一 5 个 AI 模型子页的视觉风格。
2. 允许在设置中直接修改模型信息，尤其是 API Key 和 Base URL。

---

## 2. Goals

1. 统一 LLM / Embedding / Reranker / VLM / OCR 五个子页的视觉风格。
2. 将 LLM 从只读状态卡片改为可编辑表单。
3. 运行时仍支持 `.env` 环境变量，但 UI 配置可作为默认值/回退。
4. 复用现有 UI 原子组件，保持代码可维护性。
5. 保证 `npm run build` 通过，不影响既有功能。

---

## 3. Out of Scope

- 本地模型下载页（Models）和模型服务页（Model Service）不做风格统一，保持原样。
- 不新增 Provider 预设数据；继续使用 `modelConfigs.ts` 中的建议列表。
- 不处理既有的 `ProcessingQueue.logs.test.tsx` 测试失败。

---

## 4. Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  SettingsPage                                                   │
│  ├── loads SettingsState via get_settings()                     │
│  ├── renders SettingsTabs → LlmTab / AIModelsSection            │
│  └── saves via save_settings() → config.json                    │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐      ┌──────────────────┐     ┌──────────────┐
│  LLM Subpage  │      │ Embed/Rerank/     │     │  VLM / OCR   │
│  (with Test)  │      │ VLM Subpages     │     │  Subpages    │
└───────┬───────┘      └────────┬─────────┘     └──────┬───────┘
        │                       │                      │
        └───────────────────────┼──────────────────────┘
                                ▼
                  ┌─────────────────────────┐
                  │    ModelConfigCard      │
                  │  reusable component     │
                  └─────────────────────────┘
                                │
                                ▼
                  ┌─────────────────────────┐
                  │ ProviderField /         │
                  │ ApiKeyInput /           │
                  │ ModelSelector /         │
                  │ NumberField             │
                  └─────────────────────────┘

Runtime LLM config resolution:
1. If `MBFORGE_LLM_PROVIDER` env var exists → use all `MBFORGE_LLM_*` env vars.
2. Else → read `AppConfig.llm` from `config.json`.
3. If neither provides required fields → error.
```

---

## 5. Component Design

### 5.1 ModelConfigCard

A new reusable component located at:

```
frontend/src/components/settings/ModelConfigCard.tsx
```

Props:

```ts
interface ModelConfigCardProps {
  modelType: 'llm' | 'embed' | 'rerank' | 'vlm' | 'ocr';
  title: string;
  description?: string;
  config: ModelConfig;          // slice of SettingsState
  onChange: (patch: Partial<ModelConfig>) => void;
  showTest?: boolean;           // default false; true for LLM
  testStatus?: 'idle' | 'testing' | 'success' | 'error';
  onTest?: () => void;
}
```

The card renders:

1. **Header**: title + description + optional Test button.
2. **Connection group**: provider, base URL, API key, model name.
3. **Advanced group**: model-specific fields such as max tokens, temperature, top_p, timeout, device, mrlDim, maxLength, useHfMirror.

For OCR, the card will additionally render per-backend key inputs (MinerU, UniParser, PaddleOCR host/model) inside a dedicated group.

### 5.2 Field Definitions

Each model type declares its fields declaratively:

```ts
const MODEL_FIELDS: Record<string, FieldDef[]> = {
  llm: [
    { key: 'provider', type: 'provider', required: true },
    { key: 'baseUrl', type: 'url' },
    { key: 'apiKey', type: 'apiKey' },
    { key: 'model', type: 'model' },
    { key: 'maxTokens', type: 'number', group: 'advanced' },
    { key: 'temperature', type: 'number', group: 'advanced', min: 0, max: 2, step: 0.1 },
    { key: 'topP', type: 'number', group: 'advanced', min: 0, max: 1, step: 0.05 },
    { key: 'requestTimeout', type: 'number', group: 'advanced' },
  ],
  embed: [ ... ],
  rerank: [ ... ],
  vlm: [ ... ],
  ocr: [ ... ],
};
```

### 5.3 Existing UI Atoms

Reuse the following components:

- `ProviderField` — provider select with conditional base URL / API key.
- `ApiKeyInput` — password input with show/hide and copy.
- `ModelSelector` — free-text input with `<datalist>` model suggestions.
- `NumberField` — numeric inputs for sampling parameters.
- `SettingGroup` — group titles such as "Connection" and "Advanced".

### 5.4 Visual Style

User selected **Option B: Card Groups**.

- Each sub-page contains one primary card with rounded corners, border, and subtle shadow (consistent with existing card styles).
- Fields are stacked vertically inside the card with 16px row gaps.
- Labels sit above inputs in a stacked layout (`layout="stacked"`), matching the focused card aesthetic.
- Header includes the model type title and a one-line description.
- For LLM only, the header includes a Test/Refresh button and a connection status badge.

---

## 6. Backend Changes

### 6.1 LLM Runtime Config Resolution

File: `src-tauri/src/core/agent/rig_adapter.rs`

Change `MbforgeProviderConfig::from_app_config()` from env-only to env-first with config fallback:

```rust
impl MbforgeProviderConfig {
    pub fn from_app_config(config: &AppConfig) -> Result<Self, String> {
        // 1. Try environment variables first
        if let Ok(provider) = std::env::var("MBFORGE_LLM_PROVIDER") {
            return Ok(Self {
                provider,
                base_url: std::env::var("MBFORGE_LLM_BASE_URL").ok(),
                api_key: std::env::var("MBFORGE_LLM_API_KEY").ok(),
                model: std::env::var("MBFORGE_LLM_MODEL").ok(),
                // ... max_tokens, temperature, top_p, timeout
            });
        }

        // 2. Fallback to AppConfig.llm
        let llm = &config.llm;
        if llm.provider.is_empty() {
            return Err("LLM provider is not configured".into());
        }

        Ok(Self {
            provider: llm.provider.clone(),
            base_url: llm.base_url.clone(),
            api_key: llm.api_key.clone(),
            model: llm.model.clone(),
            // ...
        })
    }
}
```

### 6.2 Settings Save Path

No change required. `save_settings` already merges the `llm` node into `config.json`.

Ensure `frontend/src/components/settings/types.ts#toBackendPayload` includes all LLM fields when saving.

### 6.3 Test Connection

`test_llm_connection` command already calls the same config resolution path, so it will automatically pick up the new env/config precedence.

---

## 7. State & Types

### 7.1 SettingsState

`SettingsState` already contains flattened LLM fields (`llm_provider`, `llm_base_url`, etc.).
No schema change is required.

### 7.2 Payload Mapping

`toBackendPayload` must emit:

```json
{
  "llm": {
    "provider": "...",
    "base_url": "...",
    "api_key": "...",
    "model": "...",
    "max_tokens": 4096,
    "temperature": 0.7,
    "top_p": 1.0,
    "request_timeout": 60
  }
}
```

---

## 8. i18n

Reuse existing keys where possible and add new ones for LLM editable fields:

```json
{
  "settings": {
    "llmProvider": "Provider",
    "llmBaseUrl": "Base URL",
    "llmApiKey": "API Key",
    "llmModel": "Model",
    "llmMaxTokens": "Max Tokens",
    "llmTemperature": "Temperature",
    "llmTopP": "Top P",
    "llmRequestTimeout": "Request Timeout",
    "llmConnectionGroup": "Connection",
    "llmAdvancedGroup": "Advanced",
    "llmTestConnection": "Test Connection",
    "llmTesting": "Testing...",
    "llmConnectionOk": "Connection OK",
    "llmConnectionFailed": "Connection failed"
  }
}
```

Both `en.json` and `zh-CN.json` will be updated.

---

## 9. Validation

1. **Provider** is required for all model types.
2. **Base URL** optional; if provided, validate URL format.
3. **Temperature** range 0–2, step 0.1.
4. **Top P** range 0–1, step 0.05.
5. **Max tokens / request timeout** positive integers.
6. Errors shown inline below inputs or via existing toast.

---

## 10. Testing & Verification

1. `npm run build` in `frontend/` must pass.
2. Settings page loads and saves LLM / Embed / Rerank / VLM / OCR without errors.
3. LLM Test button reflects connection status.
4. With `.env` set, runtime uses env values; with env unset, runtime uses config.json values.
5. Existing settings-related unit tests pass or are updated.
6. Pre-existing `ProcessingQueue.logs.test.tsx` failures are out of scope.

---

## 11. Files to Modify

### Frontend

- `frontend/src/components/settings/ModelConfigCard.tsx` — new
- `frontend/src/components/settings/sections/AIModelsSection.tsx` — integrate ModelConfigCard
- `frontend/src/components/settings/LlmTab.tsx` — remove LlmStatusCard wrapper
- `frontend/src/components/settings/LlmStatusCard.tsx` — delete or repurpose for status-only display
- `frontend/src/components/settings/types.ts` — ensure LLM fields in payload
- `frontend/src/i18n/locales/en.json` — add keys
- `frontend/src/i18n/locales/zh-CN.json` — add keys

### Backend

- `src-tauri/src/core/agent/rig_adapter.rs` — env-first config resolution

### Optional

- `frontend/src/styles/settings.css` — adjust card spacing if needed

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| LLM runtime breaks if env/config precedence is wrong | Add explicit fallback logic and test both paths |
| Existing users rely on env-only behavior | Keep env as highest priority |
| OCR has special per-backend fields | Keep OCR config inside ModelConfigCard with conditional group |
| Type errors from refactored props | Run `npm run build` and TypeScript checks |

---

## 13. Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Pages in scope | LLM / Embed / Reranker / VLM / OCR | User explicitly selected all 5 sub-pages |
| Editable fields | Provider, Base URL, API Key, Model + model-specific params | Covers the user's core request |
| Layout style | Card Groups (single card per page) | User selected Option B |
| Env precedence | Env vars win, config.json fallback | Backward compatibility |
| Implementation scope | Full unification with reusable component | User selected Approach 2 |
