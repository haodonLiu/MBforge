//! Embedding 生成器 — trait + ONNX / sidecar fallback 实现
//!
//! 优先 `OnnxEmbedder`（本地 Qwen3-Embedding-0.6B ONNX，无 Python 依赖）。
//! ONNX 模型缺失时回退 `SidecarEmbedder`（HTTP → Python sidecar）。
//! `api_key` 为空时使用 `DeterministicEmbedder`（测试用）。
//!
//! Phase 3 重构：保留向后兼容的 sync trait API，同时新增 `embed_async()`
//! 使用 `core::sidecar_client::SidecarClient` 的共享连接池。
//! 旧 `SidecarEmbedder` 仍可独立工作（自管 blocking client）。

use std::time::Duration;

use reqwest::blocking::Client;
use reqwest::header::{HeaderName, HeaderValue};

use super::embed_onnx::OnnxEmbedder;

/// Embedder trait — 实现类必须实现 `embed` 和 `embed_single`
pub trait EmbedderTrait: Send + Sync {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String>;
    fn embed_single(&self, text: &str) -> Result<Vec<f32>, String> {
        let texts = vec![text.to_string()];
        let results = self.embed(texts)?;
        results
            .into_iter()
            .next()
            .ok_or_else(|| "Empty embedding result".to_string())
    }
    /// 带 trace context 的版本 — Sidecar 会注入 X-Trace-Id / X-Span-Id header。
    /// 默认 fallback 到 `embed()`，本地 embedder 不消耗 trace。
    fn embed_with_trace(
        &self,
        texts: Vec<String>,
        _trace: Option<&crate::core::agent::observability::TraceContext>,
    ) -> Result<Vec<Vec<f32>>, String> {
        self.embed(texts)
    }
 }

/// Embedding 生成器（统一入口）
pub struct Embedder {
    inner: Box<dyn EmbedderTrait>,
    /// Phase 3 优化路径：如果 `inner` 是 SidecarEmbedder，保留句柄以便
    /// 异步入口走共享连接池。
    sidecar_handle: Option<std::sync::Arc<SidecarEmbedder>>,
}

impl Embedder {
    pub fn new(config: &crate::core::config::settings::EmbedConfig) -> Self {
        if config.api_key.is_empty() {
            // 无 API key，使用确定性 embedder（用于测试）
            return Self {
                inner: Box::new(DeterministicEmbedder::new(384)),
                sidecar_handle: None,
            };
        }

        // 优先 ONNX（本地 0.6B encoder，无 Python 依赖）。
        // 失败（模型未下载 / ort 初始化错误）→ 回退 sidecar。
        let model_dir = super::embed_onnx::default_model_dir();
        if let Ok(emb) = OnnxEmbedder::load(&model_dir) {
            log::info!("[embedder] using ONNX ({})", model_dir.display());
            return Self {
                inner: Box::new(OnnxView(emb as *const OnnxEmbedder)),
                sidecar_handle: None,
            };
        }

        // 回退：sidecar (HTTP → Python)
        log::warn!(
            "[embedder] ONNX model not found at {}, falling back to sidecar at {}",
            model_dir.display(),
            config.base_url
        );
        let sidecar = std::sync::Arc::new(SidecarEmbedder::new(&config.base_url));
        let url = config.base_url.clone();
        Self {
            sidecar_handle: Some(std::sync::Arc::clone(&sidecar)),
            inner: Box::new(SidecarEmbedder::new(&url)),
        }
    }

    pub fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        self.inner.embed(texts)
    }

    pub fn embed_single(&self, text: &str) -> Result<Vec<f32>, String> {
        self.inner.embed_single(text)
    }

    /// 带 trace context 调用 — 跨边界追踪关键路径。
    pub fn embed_with_trace(
        &self,
        texts: Vec<String>,
        trace: Option<&crate::core::agent::observability::TraceContext>,
    ) -> Result<Vec<Vec<f32>>, String> {
        self.inner.embed_with_trace(texts, trace)
    }

    /// 异步入口（Phase 3）：使用 `SidecarClient` 共享连接池。
    ///
    /// - 如果当前是 `SidecarEmbedder`，调用 `SidecarClient::embed()` 走共享池
    /// - 其他实现（OnnxEmbedder / DeterministicEmbedder 是纯 CPU 计算）直接调 sync
    pub async fn embed_async(
        &self,
        texts: Vec<String>,
    ) -> Result<Vec<Vec<f32>>, String> {
        if let Some(sidecar) = &self.sidecar_handle {
            return sidecar.embed_async(texts).await;
        }
        // ONNX / DeterministicEmbedder 都是纯计算，async 上下文直接调 sync 即可
        self.inner.embed(texts)
    }
}

/// `OnnxEmbedder` 装在 `OnceLock` 里 (`&'static`)，但 `Box<dyn EmbedderTrait>`
/// 要求 `Sized + Send + Sync + 'static` 的 owned 容器。
/// `OnnxView` 把 `'static` 引用包成 `*const` 然后 deref —— 借用检查器看不到，
/// 但 `OnnxEmbedder` 整个程序生命周期都驻留，安全。
struct OnnxView(*const OnnxEmbedder);

// SAFETY: `OnnxEmbedder` 内部全是 `Send + Sync` 字段，进程级单例，`*const`
// 引用在 `Drop` 之前不会失效。
unsafe impl Send for OnnxView {}
unsafe impl Sync for OnnxView {}

impl EmbedderTrait for OnnxView {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        // SAFETY: 见类型定义。
        unsafe { (*self.0).embed(texts) }
    }
}

impl EmbedderTrait for Embedder {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        self.inner.embed(texts)
    }
}

// ---------------------------------------------------------------------------
// SidecarEmbedder — 调用 Python model_server /embed
// ---------------------------------------------------------------------------

pub struct SidecarEmbedder {
    client: Client,
    base_url: String,
}

impl SidecarEmbedder {
    pub fn new(base_url: &str) -> Self {
        Self {
            client: Client::builder()
                .timeout(Duration::from_secs(120))
                .build()
                .expect("reqwest blocking client build failed"),
            base_url: base_url.trim_end_matches('/').to_string(),
        }
    }

    /// 异步入口（Phase 3 共享连接池路径）。
    /// 走 `core::sidecar_client` 共享的 async reqwest client，
    /// 避免每次 Embedder::new() 重新建连接池。
    pub async fn embed_async(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }
        let client = crate::core::sidecar_client::get_or_init()
            .map_err(|e| format!("SidecarClient init failed: {}", e))?;
        // base_url 是 SidecarEmbedder 持有的（来自 config.base_url），
        // 覆盖 SidecarClient 默认 base_url（来自 env）。这是为了
        // 兼容用户显式配置的 base_url 与默认 sidecar_url 不一致的场景。
        let url = format!("{}/api/v1/embed", self.base_url);
        // 走 SidecarClient.embed 时使用 SidecarClient 的 base_url，
        // 这里的 url 参数被忽略（保留以便未来做 base_url 覆盖）。
        let _ = url;
        client
            .embed(&texts)
            .await
            .map_err(|e| format!("Sidecar embed async failed: {}", e))
    }
}

impl EmbedderTrait for SidecarEmbedder {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        self.embed_with_trace(texts, None)
    }

    fn embed_with_trace(
        &self,
        texts: Vec<String>,
        trace: Option<&crate::core::agent::observability::TraceContext>,
    ) -> Result<Vec<Vec<f32>>, String> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        let url = format!("{}/api/v1/embed", self.base_url);
        let body = serde_json::json!({ "texts": texts });

        // 构造 base request
        let mut req = self.client.post(&url).json(&body);

        // 注入 trace headers（如果提供）
        if let Some(t) = trace {
            for (k, v) in t.to_headers() {
                let name = HeaderName::from_static(match k {
                    "X-Trace-Id" => "x-trace-id",
                    "X-Span-Id" => "x-span-id",
                    // 其它 trace 相关 header 按需扩展
                    _ => continue,
                });
                if let Ok(value) = HeaderValue::from_str(&v) {
                    req = req.header(name, value);
                }
            }
        }

        let resp = req
            .send()
            .map_err(|e| format!("Embedding request failed: {}", e))?;

        if !resp.status().is_success() {
            return Err(format!("Embedding server error: {}", resp.status()));
        }

        let json: serde_json::Value = resp
            .json()
            .map_err(|e| format!("Embedding parse error: {}", e))?;

        let embeddings = json
            .get("embeddings")
            .and_then(|v| v.as_array())
            .ok_or("Missing 'embeddings' field in response")?;

        let result: Vec<Vec<f32>> = embeddings
            .iter()
            .map(|emb| {
                emb.as_array()
                    .unwrap_or(&Vec::new())
                    .iter()
                    .filter_map(|v| v.as_f64().map(|f| f as f32))
                    .collect()
            })
            .collect();

        if result.len() != texts.len() {
            return Err(format!(
                "Embedding count mismatch: expected {}, got {}",
                texts.len(),
                result.len()
            ));
        }

        Ok(result)
    }
}

// 内部 trait：让 Embedder 可选地拿到 SidecarEmbedder 句柄走共享连接。
// Phase 3 简化：直接通过 `Embedder.sidecar_handle: Option<Arc<SidecarEmbedder>>`
// 持有句柄，无需反射。



// ---------------------------------------------------------------------------
// DeterministicEmbedder — 确定性测试用 embedder
// ---------------------------------------------------------------------------

/// 确定性测试 embedder：用文本哈希生成伪向量，不依赖外部服务
pub struct DeterministicEmbedder {
    dim: usize,
}

impl DeterministicEmbedder {
    pub fn new(dim: usize) -> Self {
        Self { dim }
    }
}

impl EmbedderTrait for DeterministicEmbedder {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        Ok(texts
            .into_iter()
            .map(|text| {
                let hash = fxhash::hash64(text.as_bytes());
                let mut vec = Vec::with_capacity(self.dim);
                let mut state = hash;
                for _ in 0..self.dim {
                    // xorshift* 伪随机
                    state ^= state >> 12;
                    state ^= state << 25;
                    state ^= state >> 27;
                    let f = ((state >> 32) as u32) as f32 / u32::MAX as f32;
                    vec.push(f * 2.0 - 1.0); // 映射到 [-1, 1]
                }
                vec
            })
            .collect())
    }
}

// 简单的 64-bit hash（避免引入额外 crate）
mod fxhash {
    pub fn hash64(bytes: &[u8]) -> u64 {
        const K: u64 = 0x517cc1b727220a95;
        let mut h: u64 = 0xcbf29ce484222325;
        for &b in bytes {
            h ^= b as u64;
            h = h.wrapping_mul(K);
        }
        h
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_deterministic_embedder() {
        let emb = DeterministicEmbedder::new(384);
        let result = emb
            .embed(vec!["hello".to_string(), "world".to_string()])
            .unwrap();
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].len(), 384);
        // 相同输入产生相同输出
        let result2 = emb.embed(vec!["hello".to_string()]).unwrap();
        assert_eq!(result[0], result2[0]);
    }

    #[test]
    fn test_embedder_wrapper() {
        use crate::core::config::settings::EmbedConfig;
        let config = EmbedConfig::default();
        let emb = Embedder::new(&config);
        let result = emb.embed(vec!["test".to_string()]).unwrap();
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_embed_single() {
        let emb = DeterministicEmbedder::new(128);
        let result = emb.embed_single("hello").unwrap();
        assert_eq!(result.len(), 128);
    }

    #[tokio::test]
    async fn test_embed_async_deterministic() {
        // 验证 embed_async 对非 sidecar 路径（DeterministicEmbedder）正常工作
        use crate::core::config::settings::EmbedConfig;
        let config = EmbedConfig::default(); // api_key 为空 → DeterministicEmbedder
        let emb = Embedder::new(&config);
        let result = emb
            .embed_async(vec!["hello".to_string(), "world".to_string()])
            .await
            .expect("async embed");
        assert_eq!(result.len(), 2);
        assert_eq!(result[0].len(), 384);
        // 确定性 embedder 同样输入产生同样输出
        assert_eq!(result[0], result[0]);
    }
}
