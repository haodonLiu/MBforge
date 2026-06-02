//! Knowledge base native tools — semantic search, document structure & pages.

use std::collections::HashMap;

use super::super::tools::{ToolInfo, ToolRegistry};

/// Register all knowledge-base native tools.
pub fn register(registry: &mut ToolRegistry, project_root: &str) {
    let root = project_root.to_string();

    // search_knowledge_base — Rust Native（替代 Sidecar）
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("search_knowledge_base", "搜索项目知识库，基于语义相似度检索相关文档内容", {
            let mut p = HashMap::new();
            p.insert("query".into(), serde_json::json!({"type": "string"}));
            p.insert("top_k".into(), serde_json::json!({"type": "integer"}));
            p
        }),
        Box::new(move |args| {
            let query = args["query"].as_str().unwrap_or("");
            let top_k = args["top_k"].as_u64().unwrap_or(5) as usize;
            match native_search_knowledge_base(&r, query, top_k) {
                Ok(results) => serde_json::to_string(&results).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                Err(e) => format!("Search error: {}", e),
            }
        }),
    );

    // get_document_structure — Rust Native
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("get_document_structure", "获取文档的章节结构树（heading 层级）", {
            let mut p = HashMap::new();
            p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
            p
        }),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            match native_get_document_structure(&r, doc_id) {
                Ok(tree) => serde_json::to_string(&tree).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                Err(e) => format!("Structure error: {}", e),
            }
        }),
    );

    // get_document_pages — Rust Native
    let r = root.clone();
    registry.register_with_fn(
        ToolInfo::new("get_document_pages", "按页码获取文档的原始文本内容", {
            let mut p = HashMap::new();
            p.insert("doc_id".into(), serde_json::json!({"type": "string"}));
            p.insert("pages".into(), serde_json::json!({"type": "string", "description": "页码范围，如 '5-7,10'"}));
            p
        }),
        Box::new(move |args| {
            let doc_id = args["doc_id"].as_str().unwrap_or("");
            let pages = args["pages"].as_str().unwrap_or("");
            match native_get_document_pages(&r, doc_id, pages) {
                Ok(pages) => serde_json::to_string(&pages).unwrap_or_else(|e| format!("Serialize error: {}", e)),
                Err(e) => format!("Pages error: {}", e),
            }
        }),
    );
}

// ===== Native implementations =====
// 使用 knowledge_base.rs 中的共享 KB_CACHE，避免重复缓存

fn native_search_knowledge_base(
    root: &str,
    query: &str,
    top_k: usize,
) -> Result<Vec<serde_json::Value>, String> {
    let (results, _) = crate::core::knowledge_base::search_with_cache(root, query, top_k)?;
    Ok(results)
}

fn native_get_document_structure(
    root: &str,
    doc_id: &str,
) -> Result<Option<Vec<crate::parsers::sections::TreeNode>>, String> {
    let guard = crate::core::knowledge_base::get_or_init_kb(root)?;
    // get_or_init_kb guarantees `root` is present; the unwrap_or_else branch
    // is defensive against future refactors that change that invariant.
    let kb = guard
        .get(root)
        .ok_or_else(|| format!("KnowledgeBase not initialized for project: {}", root))?;
    Ok(kb.get_structure(doc_id))
}

fn native_get_document_pages(
    root: &str,
    doc_id: &str,
    pages: &str,
) -> Result<Vec<crate::core::knowledge_base::PageContent>, String> {
    let guard = crate::core::knowledge_base::get_or_init_kb(root)?;
    let kb = guard
        .get(root)
        .ok_or_else(|| format!("KnowledgeBase not initialized for project: {}", root))?;
    Ok(kb.get_pages(doc_id, pages))
}
