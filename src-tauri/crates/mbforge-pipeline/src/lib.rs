//! mbforge-pipeline: PDF 解析管线与摄取编排。
//!
//! 承载从 PDF/图像到结构化文档、分子、知识库索引的完整解析流程。
//! 该 crate 是 `mbforge-domain` 的消费方，通过 domain 的公共 API
//!（`KnowledgeBase`、`MoleculeDatabase`、`Project` 等）写入解析结果，
//! 从而避免 domain → pipeline 的循环依赖。

// 迁移遗留代码中存在大量不符合当前 clippy 严格规则的模式；集中允许而非逐处改写。
#![allow(
    clippy::bind_instead_of_map,
    clippy::empty_line_after_doc_comments,
    clippy::expect_used,
    clippy::extend_with_drain,
    clippy::large_enum_variant,
    clippy::let_and_return,
    clippy::manual_pattern_char_comparison,
    clippy::manual_strip,
    clippy::map_flatten,
    clippy::match_like_matches_macro,
    clippy::module_inception,
    clippy::new_without_default,
    clippy::panic,
    clippy::redundant_closure,
    clippy::should_implement_trait,
    clippy::too_many_arguments,
    clippy::unnecessary_cast,
    clippy::unnecessary_map_or,
    clippy::unnecessary_sort_by,
    clippy::unwrap_used,
    clippy::useless_conversion,
    clippy::while_let_loop
)]

pub mod chem;
pub mod doc_types;
pub mod ingest_worker;
pub mod keywords;
pub mod ocr;
pub mod pdf;
pub mod pipeline;
pub mod structure;
