//! 共享 HTTP 客户端工厂
//!
//! 避免每次请求都创建新的 `reqwest::Client`（每次创建都会新建连接池）。
//! 提供按超时时间分类的预建客户端。

use std::sync::LazyLock;
use std::time::Duration;

/// 短超时客户端（15s）— 用于快速 sidecar 调用（agent LLM、skills 创建）
static CLIENT_15S: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("Failed to build HTTP client (15s)")
});

/// 中等超时客户端（30s）— 用于 sidecar 工具执行、记忆提取
static CLIENT_30S: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .expect("Failed to build HTTP client (30s)")
});

/// 标准超时客户端（120s）— 用于 VLM、KB 索引等中等耗时操作
static CLIENT_120S: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(120))
        .build()
        .expect("Failed to build HTTP client (120s)")
});

/// 长超时客户端（300s）— 用于 VLM describe 等长时间操作
static CLIENT_300S: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(300))
        .build()
        .expect("Failed to build HTTP client (300s)")
});

/// 获取短超时客户端（15s）
pub fn client_15s() -> &'static reqwest::Client {
    &CLIENT_15S
}

/// 获取中等超时客户端（30s）
pub fn client_30s() -> &'static reqwest::Client {
    &CLIENT_30S
}

/// 获取标准超时客户端（120s）
pub fn client_120s() -> &'static reqwest::Client {
    &CLIENT_120S
}

/// 获取长超时客户端（300s）
pub fn client_300s() -> &'static reqwest::Client {
    &CLIENT_300S
}
