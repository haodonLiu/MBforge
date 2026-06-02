//! Embedding 生成器 — trait + sidecar 实现
//!
//! 当前通过 HTTP 调用 Python sidecar 的 /embed 端点，
//! 后续可替换为本地 ONNX Runtime (`ort` crate)。

use std::time::Duration;

use reqwest::blocking::Client;

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
}

/// Embedding 生成器（统一入口）
pub struct Embedder {
    inner: Box<dyn EmbedderTrait>,
}

impl Embedder {
    pub fn new(config: &super::config::EmbedConfig) -> Self {
        if config.api_key.is_empty() {
            // 无 API key，使用确定性 embedder（用于测试）
            Self {
                inner: Box::new(DeterministicEmbedder::new(384)),
            }
        } else {
            Self {
                inner: Box::new(SidecarEmbedder::new(&config.base_url)),
            }
        }
    }

    pub fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        self.inner.embed(texts)
    }

    pub fn embed_single(&self, text: &str) -> Result<Vec<f32>, String> {
        self.inner.embed_single(text)
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
}

impl EmbedderTrait for SidecarEmbedder {
    fn embed(&self, texts: Vec<String>) -> Result<Vec<Vec<f32>>, String> {
        if texts.is_empty() {
            return Ok(Vec::new());
        }

        let url = format!("{}/api/v1/embed", self.base_url);
        let body = serde_json::json!({ "texts": texts });

        let resp = self
            .client
            .post(&url)
            .json(&body)
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
        use super::super::config::EmbedConfig;
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
}
