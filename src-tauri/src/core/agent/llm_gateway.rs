//! LLM 网关（Phase 4 重构）
//!
//! 解决问题：
//! - `parsers/structure/post_process.rs::dispatch_chat` 每次调用都重新
//!   `OpenAiClient::builder()` 构造 client + 内部 HTTP 连接池
//! - 重复 `temperature(0.2).max_tokens(8192).build()` 等参数拼装
//!
//! 设计：
//! - `LlmGateway` 持有缓存的 OpenAI provider client
//! - 同一组 (provider, base_url, api_key, model) 命中缓存复用
//! - `global()` 返回进程级单例
//!
//! 注意：此模块是 Phase 4 的"骨架"——完整迁移会重写 dispatch_chat
//! 内部逻辑以使用缓存的 client。

use std::collections::HashMap;
use std::sync::{Arc, Mutex, OnceLock};

use rig_core::client::CompletionClient;
use rig_core::providers::openai::Client as OpenAiClient;

use crate::core::config::settings::ModelConfig;

/// Provider 缓存键。同一组 (provider, base_url, api_key_hash, model) 复用 client。
#[derive(Clone, Debug, Hash, PartialEq, Eq)]
struct ProviderKey {
    provider: String,
    base_url: String,
    /// 不用明文 api_key 做 key（避免日志泄露）；用 hash 的前 16 字符即可区分。
    api_key_fingerprint: String,
    model: String,
}

impl ProviderKey {
    fn from_config(cfg: &ModelConfig) -> Self {
        let api_key_fp = {
            use std::collections::hash_map::DefaultHasher;
            use std::hash::{Hash, Hasher};
            let mut h = DefaultHasher::new();
            cfg.api_key.hash(&mut h);
            format!("{:016x}", h.finish())
        };
        Self {
            provider: cfg.provider.clone(),
            base_url: cfg.base_url.clone(),
            api_key_fingerprint: api_key_fp,
            model: cfg.model_name.clone(),
        }
    }
}

/// LLM 网关：缓存 OpenAI provider client，避免每调用重建。
pub struct LlmGateway {
    cache: Mutex<HashMap<ProviderKey, CachedEntry>>,
}

struct CachedEntry {
    client: Arc<OpenAiClient>,
    /// 在创建 client 时一并记录 model 名，调用 `client.completion_model(model)`
    /// 仍需要指定 model（rig 0.38.1 API 要求）。
    model: String,
}

impl LlmGateway {
    /// 构造新网关。配置变化时（如切换 base_url）自动失效缓存。
    pub fn new() -> Self {
        Self {
            cache: Mutex::new(HashMap::new()),
        }
    }

    /// 获取或创建 OpenAI provider client（线程安全）。
    ///
    /// 同一 key 命中缓存时返回 `Arc` 共享实例；缓存未命中时构造并缓存。
    /// 注：当前仅 OpenAI-compatible provider 走 cache 路径；
    /// Anthropic 暂未实现（rig-core 0.38 API 差异），保留 fallback 路径。
    pub fn get_client(
        &self,
        cfg: &ModelConfig,
    ) -> Result<(Arc<OpenAiClient>, String), String> {
        let key = ProviderKey::from_config(cfg);

        // 先查缓存
        {
            let cache = self
                .cache
                .lock()
                .map_err(|e| format!("gateway mutex poisoned: {e}"))?;
            if let Some(cached) = cache.get(&key) {
                return Ok((Arc::clone(&cached.client), cached.model.clone()));
            }
        }

        // 缓存未命中：构造新 client
        if !is_openai_compatible(&cfg.provider) {
            return Err(format!(
                "Provider '{}' is not yet supported by LlmGateway cache; \
                 use call_llm_api_async fallback path",
                cfg.provider
            ));
        }

        let mut b = OpenAiClient::builder().api_key(&cfg.api_key);
        if !cfg.base_url.is_empty() {
            b = b.base_url(&cfg.base_url);
        }
        let client = b
            .build()
            .map_err(|e| format!("openai client build failed: {e}"))?;
        let client_arc = Arc::new(client);

        // 插入缓存
        let mut cache = self
            .cache
            .lock()
            .map_err(|e| format!("gateway mutex poisoned: {e}"))?;
        // 双检查：可能其他线程已插入
        if let Some(cached) = cache.get(&key) {
            return Ok((Arc::clone(&cached.client), cached.model.clone()));
        }
        let model = cfg.model_name.clone();
        cache.insert(
            key,
            CachedEntry {
                client: Arc::clone(&client_arc),
                model: model.clone(),
            },
        );
        Ok((client_arc, model))
    }

    /// 清空缓存（用于配置变更或测试）。
    pub fn clear(&self) {
        if let Ok(mut cache) = self.cache.lock() {
            cache.clear();
        }
    }
}

impl Default for LlmGateway {
    fn default() -> Self {
        Self::new()
    }
}

/// Provider 名是否走 OpenAI 兼容 API（OpenAI / Qwen / DeepSeek / vLLM / Ollama 等）。
fn is_openai_compatible(provider: &str) -> bool {
    matches!(
        provider.to_lowercase().as_str(),
        "openai" | "openai_compatible" | "qwen" | "deepseek" | "vllm" | "ollama" | "lmstudio" | "custom"
    )
}

// ─── 进程级单例 ────────────────────────────────────────────

static GATEWAY: OnceLock<Arc<LlmGateway>> = OnceLock::new();

/// 获取全局 LlmGateway 单例。
pub fn global() -> Arc<LlmGateway> {
    GATEWAY
        .get_or_init(|| Arc::new(LlmGateway::new()))
        .clone()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_config() -> ModelConfig {
        ModelConfig {
            provider: "openai".to_string(),
            base_url: "https://api.openai.com/v1".to_string(),
            api_key: "sk-test123".to_string(),
            model_name: "gpt-4o-mini".to_string(),
            max_tokens: 4096,
            temperature: 0.7,
            top_p: 0.9,
            request_timeout: 120,
        }
    }

    #[test]
    fn cache_key_distinguishes_different_models() {
        let a = ProviderKey::from_config(&test_config());
        let mut b_cfg = test_config();
        b_cfg.model_name = "gpt-4o".to_string();
        let b = ProviderKey::from_config(&b_cfg);
        assert_ne!(a, b);
    }

    #[test]
    fn cache_key_distinguishes_different_keys() {
        let a = ProviderKey::from_config(&test_config());
        let mut b_cfg = test_config();
        b_cfg.api_key = "sk-different".to_string();
        let b = ProviderKey::from_config(&b_cfg);
        assert_ne!(a, b);
    }

    #[test]
    fn cache_key_same_for_same_config() {
        let a = ProviderKey::from_config(&test_config());
        let b = ProviderKey::from_config(&test_config());
        assert_eq!(a, b);
    }

    #[test]
    fn openai_compatible_detection() {
        assert!(is_openai_compatible("openai"));
        assert!(is_openai_compatible("OpenAI"));
        assert!(is_openai_compatible("qwen"));
        assert!(is_openai_compatible("vllm"));
        assert!(!is_openai_compatible("anthropic"));
    }

    #[test]
    fn gateway_clear_empties_cache() {
        let gw = LlmGateway::new();
        gw.clear();
        // 实际构造 client 需要合法 api_key + 真实可达的 base_url，
        // 这里只验证 clear 不 panic
    }

    #[test]
    fn global_singleton_returns_same_instance() {
        let a = global();
        let b = global();
        assert!(Arc::ptr_eq(&a, &b));
    }
}
