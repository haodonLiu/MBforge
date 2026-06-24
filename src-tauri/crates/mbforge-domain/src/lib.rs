//! mbforge-domain: MBForge 业务领域层。
//!
//! 承载业务状态与核心领域逻辑：文档/KB、分子数据库/引擎、项目管理、
//! 提取队列与 Embedding/Zvec 搜索封装。该 crate 仅依赖 `mbforge-infra`
//! 与 `mbforge-chem`，不依赖解析管线或 Tauri 应用层。

// 迁移遗留代码中存在大量不符合当前 clippy 严格规则的模式；集中允许而非逐处改写。
#![allow(
    clippy::expect_used,
    clippy::manual_pattern_char_comparison,
    clippy::module_inception,
    clippy::panic,
    clippy::should_implement_trait,
    clippy::unnecessary_map_or,
    clippy::unwrap_used,
    clippy::while_let_loop
)]

pub mod document;
pub mod ingest_queue;
pub mod molecule;
pub mod project;
pub mod vector;
