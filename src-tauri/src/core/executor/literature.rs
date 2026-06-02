//! Literature API tools — arXiv / PMC paper metadata and full-text access.
//!
//! All implementations live in `super::super::arxiv`; this module only
//! registers them as native tools (the alternative is HTTP fallback to
//! the Python sidecar).

use std::collections::HashMap;

use super::super::arxiv;
use super::super::tools::{ToolInfo, ToolRegistry};

/// Register all literature native tools.
pub fn register(registry: &mut ToolRegistry, _project_root: &str) {
    // arxiv_metadata — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_metadata", "获取 arXiv 论文的完整元数据（标题、摘要、作者、章节列表、token 计数等）", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID, e.g. 2409.05591"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token (free papers 2409.05591, 2504.21776 don't need it)"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_metadata),
    );

    // arxiv_brief — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_brief", "获取 arXiv 论文的简要信息（标题、TLDR、关键词、引用数）。适合快速筛选。", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID, e.g. 2409.05591"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_brief),
    );

    // arxiv_preview — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_preview", "预览论文的开头部分内容（默认 10000 字符，可调整）。适合移动端或快速浏览引言。", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID"}));
            p.insert("characters".into(), serde_json::json!({"type": "integer", "description": "预览字符数，范围 100-100000，默认 10000"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_preview),
    );

    // arxiv_raw — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_raw", "获取 arXiv 论文的完整内容（Markdown 格式）。适合深入阅读全文。", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_raw),
    );

    // arxiv_section — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_section", "获取论文的特定章节内容，如 Introduction、Methods、Conclusion。", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID"}));
            p.insert("section".into(), serde_json::json!({"type": "string", "description": "章节名称，如 Introduction、Methods、Conclusion"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_section),
    );

    // arxiv_search — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_search", "跨 arXiv/bioRxiv/medRxiv 统一语义检索论文。支持多维度过滤。", {
            let mut p = HashMap::new();
            p.insert("query".into(), serde_json::json!({"type": "string", "description": "搜索查询（最大 500 字符）"}));
            p.insert("source".into(), serde_json::json!({"type": "string", "description": "来源：arxiv（默认）、biorxiv、medrxiv"}));
            p.insert("top_k".into(), serde_json::json!({"type": "integer", "description": "返回结果数 1-100，默认 10"}));
            p.insert("offset".into(), serde_json::json!({"type": "integer", "description": "分页偏移，默认 0"}));
            p.insert("authors".into(), serde_json::json!({"type": "string", "description": "作者过滤（逗号分隔）"}));
            p.insert("orgs".into(), serde_json::json!({"type": "string", "description": "机构过滤（逗号分隔）"}));
            p.insert("categories".into(), serde_json::json!({"type": "string", "description": "分类过滤，如 cs.AI,cs.CL（逗号分隔）"}));
            p.insert("date_search_type".into(), serde_json::json!({"type": "string", "description": "日期类型：exact、after、before、between"}));
            p.insert("date_str".into(), serde_json::json!({"type": "string", "description": "日期值，格式 YYYY / YYYY-MM / YYYY-MM-DD；between 时逗号分隔起止"}));
            p.insert("min_citation".into(), serde_json::json!({"type": "integer", "description": "最低引用数过滤"}));
            p.insert("use_fine_rerank".into(), serde_json::json!({"type": "boolean", "description": "是否使用精排（默认 true）"}));
            p.insert("return_contents".into(), serde_json::json!({"type": "boolean", "description": "是否返回检索到的章节内容（默认 false）"}));
            p.insert("return_roc".into(), serde_json::json!({"type": "boolean", "description": "是否返回 RoC 列表（默认 false）"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_search),
    );

    // arxiv_trending — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("arxiv_trending", "获取论文在社交媒体（Twitter/X）上的传播数据，包括推文数、点赞数、浏览数。需要 API token。", {
            let mut p = HashMap::new();
            p.insert("arxiv_id".into(), serde_json::json!({"type": "string", "description": "arXiv paper ID"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "API token（必需）"}));
            p
        }),
        Box::new(arxiv::tool_arxiv_trending),
    );

    // pmc_metadata — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("pmc_metadata", "获取 PubMed Central (PMC) 论文的元数据（标题、DOI、摘要、作者、类别）。", {
            let mut p = HashMap::new();
            p.insert("pmc_id".into(), serde_json::json!({"type": "string", "description": "PMC paper ID, e.g. PMC544940"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token (free papers PMC544940, PMC514704 don't need it)"}));
            p
        }),
        Box::new(arxiv::tool_pmc_metadata),
    );

    // pmc_json — Agentic Data API
    registry.register_with_fn(
        ToolInfo::new("pmc_json", "获取 PubMed Central (PMC) 论文的完整 JSON（含全文内容和元数据）。", {
            let mut p = HashMap::new();
            p.insert("pmc_id".into(), serde_json::json!({"type": "string", "description": "PMC paper ID, e.g. PMC514704"}));
            p.insert("token".into(), serde_json::json!({"type": "string", "description": "Optional API token"}));
            p
        }),
        Box::new(arxiv::tool_pmc_json),
    );
}
