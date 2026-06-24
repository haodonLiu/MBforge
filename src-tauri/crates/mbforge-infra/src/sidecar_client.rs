//! Sidecar HTTP 客户端抽象（Phase 3 重构）
//!
//! 解决问题：先前 `sidecar_url` 作为 `&str` 参数在 15+ 个函数间穿透，
//! 有的 caller 还直接 `crate::core::constants::sidecar_url()` 调，
//! 有的接受参数但忽略（`_sidecar_url`），混乱无一致性。
//!
//! 新设计：
//! - `SidecarClient` 封装 `base_url` + 共享 `reqwest::Client`
//! - 通过 `Arc<SidecarClient>` 在多个模块间共享（类似 DbManager 模式）
//! - 提供常用端点的便捷方法（health, embed, vlm, moldet）
//! - 旧 `sidecar_url: &str` 路径保留，逐步迁移
//!
//! 用法：
//! ```ignore
//! let client = SidecarClient::get_or_init()?;
//! let chunks = client.embed(texts).await?;
//! ```

use std::sync::{Arc, OnceLock};

use serde::{Deserialize, Serialize};

use crate::config::constants::sidecar_url;
use crate::error::{AppError, AppResult, ErrorCode};
use crate::http;

/// Sidecar HTTP 客户端（单例，通过 `get_or_init` 访问）。
///
/// 内含：
/// - `base_url`：从环境变量/配置推导的 sidecar 根 URL
/// - 多个共享 `reqwest::Client`（15s / 30s / 120s / 300s）
pub struct SidecarClient {
    base_url: String,
}

impl SidecarClient {
    /// 构造一个新 client。`base_url` 不应带尾部斜杠。
    pub fn new(base_url: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
        }
    }

    /// 构造时从环境/常量推导 base_url。
    pub fn from_env() -> Self {
        Self::new(sidecar_url())
    }

    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    /// 健康检查：GET /api/v1/health
    pub async fn health(&self) -> AppResult<HealthResponse> {
        let url = format!("{}/api/v1/health", self.base_url);
        let resp = http::client_15s()
            .get(&url)
            .send()
            .await
            .map_err(|e| AppError {
                code: ErrorCode::Network,
                message: format!("Sidecar health request failed: {}", e),
                path: Some(url.clone()),
                suggestion: Some("检查 Python sidecar 是否在 18792 端口运行".to_string()),
            })?;
        if !resp.status().is_success() {
            return Err(AppError {
                code: ErrorCode::Network,
                message: format!("Sidecar health returned {}", resp.status()),
                path: Some(url),
                suggestion: None,
            });
        }
        resp.json::<HealthResponse>().await.map_err(|e| AppError {
            code: ErrorCode::ApiError,
            message: format!("Sidecar health parse: {}", e),
            path: Some(url),
            suggestion: None,
        })
    }

    /// Embedding 调用：POST /api/v1/embed
    pub async fn embed(&self, texts: &[String], mrl_dim: Option<i32>) -> AppResult<Vec<Vec<f32>>> {
        let url = format!("{}/api/v1/embed", self.base_url);
        let req = EmbedRequest {
            texts: texts.to_vec(),
            mrl_dim,
        };
        // 120s timeout matches the previous `SidecarEmbedder` blocking path
        // (kept for KB long-document scenarios).
        let resp = http::client_120s()
            .post(&url)
            .json(&req)
            .send()
            .await
            .map_err(|e| AppError {
                code: ErrorCode::Network,
                message: format!("Sidecar embed request failed: {}", e),
                path: Some(url.clone()),
                suggestion: None,
            })?;
        if !resp.status().is_success() {
            return Err(AppError {
                code: ErrorCode::ApiError,
                message: format!("Sidecar embed returned {}", resp.status()),
                path: Some(url),
                suggestion: None,
            });
        }
        let parsed: EmbedResponse = resp.json().await.map_err(|e| AppError {
            code: ErrorCode::ApiError,
            message: format!("Sidecar embed parse: {}", e),
            path: Some(url),
            suggestion: None,
        })?;
        Ok(parsed.embeddings)
    }

    /// 简易 ping：返回耗时（毫秒），用于诊断。
    pub async fn ping(&self) -> AppResult<u128> {
        let url = format!("{}/api/v1/health", self.base_url);
        let start = std::time::Instant::now();
        let resp = http::client_15s()
            .get(&url)
            .send()
            .await
            .map_err(|e| AppError {
                code: ErrorCode::Network,
                message: format!("Sidecar ping failed: {}", e),
                path: Some(url),
                suggestion: None,
            })?;
        let _ = resp.bytes().await;
        Ok(start.elapsed().as_millis())
    }
}

// ─── 进程级单例 ────────────────────────────────────────────

static SIDECAR_CLIENT: OnceLock<Arc<SidecarClient>> = OnceLock::new();

/// 获取（或懒初始化）全局 SidecarClient。
///
/// 行为：
/// - 首次调用时从 `constants::sidecar_url()` 构造
/// - 之后所有 caller 共享同一实例
/// - 注意：base_url 在初始化时确定。运行中改环境变量不会影响。
pub fn get_or_init() -> AppResult<Arc<SidecarClient>> {
    Ok(SIDECAR_CLIENT
        .get_or_init(|| Arc::new(SidecarClient::from_env()))
        .clone())
}

// ─── 响应 DTO ─────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: String,
    #[serde(default)]
    pub models: std::collections::HashMap<String, String>,
    #[serde(default)]
    pub resources: std::collections::HashMap<String, String>,
    #[serde(default)]
    pub uptime_seconds: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
struct EmbedRequest {
    texts: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    mrl_dim: Option<i32>,
}

#[derive(Debug, Clone, Deserialize)]
struct EmbedResponse {
    embeddings: Vec<Vec<f32>>,
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use super::*;

    #[test]
    fn client_constructs_from_url() {
        let c = SidecarClient::new("http://127.0.0.1:18792");
        assert_eq!(c.base_url(), "http://127.0.0.1:18792");
    }

    #[test]
    fn from_env_reads_constant() {
        // sidecar_url() 来自 env 变量，未设置时回退到常量
        let c = SidecarClient::from_env();
        assert!(!c.base_url().is_empty());
    }

    #[test]
    fn get_or_init_returns_same_instance() {
        let a = get_or_init().expect("init");
        let b = get_or_init().expect("cached");
        assert!(Arc::ptr_eq(&a, &b));
    }

    #[test]
    fn health_response_parses_object_models_and_resources() {
        let json = r#"{
            "status": "partial",
            "models": {"embedder": "ready", "reranker": "ready", "moldet": "ready"},
            "resources": {"embedding": "ready", "molscribe": "ready"},
            "error": null
        }"#;
        let parsed: HealthResponse = serde_json::from_str(json).expect("parse health");
        assert_eq!(parsed.status, "partial");
        assert_eq!(parsed.models.get("embedder"), Some(&"ready".to_string()));
        assert_eq!(
            parsed.resources.get("embedding"),
            Some(&"ready".to_string())
        );
    }
}
