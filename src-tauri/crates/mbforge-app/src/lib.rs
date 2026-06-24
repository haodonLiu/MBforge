//! mbforge-app: Tauri 应用入口与命令聚合层。
//!
//! 承载所有 `#[tauri::command]` IPC 命令、Python sidecar 生命周期管理
//! 以及自定义 `mbforge://` URI scheme 协议。是 workspace 的顶层聚合 crate。

// 迁移遗留代码中存在大量不符合当前 clippy 严格规则的模式；集中允许而非逐处改写。
#![allow(
    clippy::expect_used,
    clippy::lines_filter_map_ok,
    clippy::manual_pattern_char_comparison,
    clippy::new_without_default,
    clippy::obfuscated_if_else,
    clippy::ptr_arg,
    clippy::redundant_closure,
    clippy::too_many_arguments,
    clippy::unnecessary_lazy_evaluations,
    unused_imports,
    unused_variables
)]

pub mod commands;
pub mod protocol;
pub mod sidecar;
