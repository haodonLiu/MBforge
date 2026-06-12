//! Knowledge base native tools — semantic search, document structure & pages.

// ===== Native implementations =====
// ===== Native implementations =====
// 使用 knowledge_base.rs 中的共享 KB_CACHE。
//
// 这里不能简单地 `tokio::runtime::Handle::current().block_on(...)`：
//   1. 闭包被注册为 sync `Box<dyn Fn>`，由 executor 同步调用；
//   2. 如果直接 `block_on`，Tauri 的 tokio runtime 上会 panic /
//      deadlock（"Cannot drop a runtime in a context where blocking is
//      not allowed"）。
// 解决：让 native 闭包自己 spawn 一个任务来 await 异步函数；调用方
// `executor.execute` 必须包成 async（见 [Track C-C11] 修复）。
// 这里先转成 sync-with-handle 的形式，配合 executor 层的 spawn_blocking。

pub async fn native_search_knowledge_base(
    root: &str,
    query: &str,
    top_k: usize,
) -> Result<Vec<serde_json::Value>, String> {
    let (results, _) = crate::core::document::knowledge_base::search_with_cache(root, query, top_k).await.map_err(|e| e.to_string())?;
    Ok(results)
}

pub fn native_get_document_structure(
    root: &str,
    doc_id: &str,
) -> Result<Option<Vec<crate::parsers::structure::sections::TreeNode>>, String> {
    let kb = crate::core::document::knowledge_base::get_or_init_kb(root).map_err(|e| e.to_string())?;
    Ok(kb.get_structure(doc_id))
}

pub fn native_get_document_pages(
    root: &str,
    doc_id: &str,
    pages: &str,
) -> Result<Vec<crate::core::document::knowledge_base::PageContent>, String> {
    let kb = crate::core::document::knowledge_base::get_or_init_kb(root).map_err(|e| e.to_string())?;
    Ok(kb.get_pages(doc_id, pages))
}
