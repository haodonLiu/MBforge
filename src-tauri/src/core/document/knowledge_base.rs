//! 知识库 — FTS5 全文搜索 + semantic_cache + stream_search
//!
//! 使用 SQLite FTS5 实现文本搜索，纯本地运行，不依赖任何外部模型。
//! 集成 semantic_cache (L1 hash / L2 embedding) 加速重复查询。
//! 集成 stream_search 分批返回结果。

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use tauri::Emitter;

use crate::core::constants::EVT_KB_SEARCH_CHUNK;

use super::document_tree::DocumentTreeIndex;
use super::semantic_cache::{SemanticCache, SemanticCacheConfig};
use super::stream_search::{StreamingSearch, StreamingSearchConfig, StreamingResult};
use super::super::vector_store::{SearchResult, SqliteVectorStore, VectorItem, VectorStore};
use crate::parsers::sections::{SectionChunk, TreeNode};

pub use super::document_tree::PageContent;

fn count_nodes(nodes: &[TreeNode]) -> usize {
    nodes.iter().map(|n| 1 + count_nodes(&n.nodes)).sum()
}

pub struct KbStats {
    pub document_count: usize,
    pub section_count: usize,
    pub total_sections: usize,
}

pub struct KnowledgeBase {
    vector_store: Box<dyn VectorStore>,
    tree_index: Mutex<DocumentTreeIndex>,
}

impl KnowledgeBase {
    pub fn new(project_root: &Path) -> Result<Self, String> {
        let kb_dir = project_root.join(".mbforge").join("knowledge_base");
        std::fs::create_dir_all(&kb_dir).map_err(|e| format!("Failed to create KB dir: {}", e))?;
        let db_path = kb_dir.join("vectors.db");
        let vector_store = SqliteVectorStore::new(&db_path)?;
        let tree_index = DocumentTreeIndex::new(project_root);
        Ok(Self {
            vector_store: Box::new(vector_store),
            tree_index: Mutex::new(tree_index),
        })
    }

    pub fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<usize, String> {
        let items: Vec<VectorItem> = sections
            .iter()
            .enumerate()
            .map(|(i, section)| VectorItem {
                id: format!("{}:sec{}", doc_id, i),
                doc_id: doc_id.to_string(),
                text: section.text.clone(),
                embedding: vec![],  // FTS5 不需要 embedding
                metadata: serde_json::json!({
                    "title": section.title,
                    "path": section.path,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                }),
            })
            .collect();

        self.vector_store.upsert(items)?;

        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;
        Ok(sections.len())
    }

    pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        self.vector_store.search(query, top_k, None)
    }

    pub fn search_sync(&self, query: &str, top_k: usize) -> Vec<SearchResult> {
        match self.vector_store.search(query, top_k, None) {
            Ok(results) => results,
            Err(e) => {
                log::warn!("KnowledgeBase search_sync failed: {}", e);
                Vec::new()
            }
        }
    }

    pub fn get_structure(&self, doc_id: &str) -> Option<Vec<TreeNode>> {
        let tree = self.tree_index.lock().ok()?;
        tree.get_structure(doc_id)
    }

    pub fn get_pages(&self, doc_id: &str, pages: &str) -> Vec<PageContent> {
        self.tree_index
            .lock()
            .ok()
            .map(|tree| tree.get_pages(doc_id, pages))
            .unwrap_or_default()
    }

    pub fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        self.vector_store.delete(doc_id)?;
        let tree = self.tree_index.lock().map_err(|e| format!("Lock error: {}", e))?;
        tree.remove_document(doc_id)
    }

    pub fn stats(&self) -> KbStats {
        let total_sections = self.vector_store.count().unwrap_or(0);
        let (document_count, section_count) = self
            .tree_index
            .lock()
            .ok()
            .map(|t| {
                let trees = t.load_trees();
                let doc_count = trees.len();
                let sec_count: usize = trees.values().map(|nodes| count_nodes(nodes)).sum();
                (doc_count, sec_count)
            })
            .unwrap_or((0, 0));
        KbStats {
            document_count,
            section_count,
            total_sections,
        }
    }
}

// ============================================================================
// 全局缓存：KB 实例 + SemanticCache
// ============================================================================

/// KB 实例缓存（按 project_root 键，供 knowledge_base.rs 和 executor.rs 共用）
pub static KB_CACHE: OnceLock<Mutex<HashMap<String, KnowledgeBase>>> = OnceLock::new();

/// SemanticCache 实例缓存（按 project_root 键）
static SEMANTIC_CACHE: OnceLock<Mutex<HashMap<String, SemanticCache>>> = OnceLock::new();

/// 获取或初始化 KB 实例（公共供 executor.rs 调用）
pub fn get_or_init_kb(root: &str) -> Result<std::sync::MutexGuard<'static, HashMap<String, KnowledgeBase>>, String> {
    let cache = KB_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    let guard = cache.lock().map_err(|e| format!("KB cache lock error: {}", e))?;
    if guard.contains_key(root) {
        return Ok(guard);
    }
    drop(guard);
    let kb = KnowledgeBase::new(std::path::Path::new(root))?;
    let mut guard = cache.lock().map_err(|e| format!("KB cache lock error: {}", e))?;
    guard.insert(root.to_string(), kb);
    Ok(guard)
}

fn get_or_init_semantic_cache(root: &str) -> std::sync::MutexGuard<'static, HashMap<String, SemanticCache>> {
    let cache = SEMANTIC_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    let mut guard = cache.lock().unwrap_or_else(|e| e.into_inner());
    if !guard.contains_key(root) {
        let sc = SemanticCache::new(
            std::path::Path::new(root),
            None,  // 无 embedder → 仅 L1 (hash) 模式
            SemanticCacheConfig::default(),
        );
        guard.insert(root.to_string(), sc);
    }
    guard
}

/// 搜索核心逻辑：semantic_cache (L1) → FTS5 → cache store → stream_search
pub fn search_with_cache(root: &str, query: &str, top_k: usize) -> Result<(Vec<serde_json::Value>, Vec<StreamingResult>), String> {
    // 1. L1 缓存命中？
    {
        let sc_guard = get_or_init_semantic_cache(root);
        if let Some(cached) = sc_guard.get(root).and_then(|sc| sc.get_l1(query)) {
            let stream = StreamingSearch::new(StreamingSearchConfig::default())
                .execute(cached.clone(), top_k);
            return Ok((cached, stream));
        }
    }

    // 2. FTS5 搜索
    let guard = get_or_init_kb(root)?;
    let kb = guard.get(root).unwrap();
    let results = kb.search(query, top_k)
        .map_err(|e| format!("Search failed: {}", e))?;

    let json_results: Vec<serde_json::Value> = results
        .into_iter()
        .map(|r| serde_json::json!({
            "id": r.id,
            "text": r.text,
            "metadata": r.metadata,
            "score": r.score,
        }))
        .collect();

    // 3. 写入缓存
    {
        let mut sc_guard = get_or_init_semantic_cache(root);
        if let Some(sc) = sc_guard.get_mut(root) {
            sc.store(query, json_results.clone());
        }
    }

    // 4. 流式分批
    let stream = StreamingSearch::new(StreamingSearchConfig::default())
        .execute(json_results.clone(), top_k);

    Ok((json_results, stream))
}

// ============================================================================
// Tauri 命令层
// ============================================================================

/// 同步搜索（返回完整结果，兼容旧接口）
#[tauri::command]
pub fn kb_search(
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<Vec<serde_json::Value>, String> {
    let top_k = top_k.unwrap_or(5);
    let (results, _) = search_with_cache(&root, &query, top_k)?;
    Ok(results)
}

/// 流式搜索（通过 Tauri 事件分批推送结果）
#[tauri::command]
pub async fn kb_search_stream(
    app: tauri::AppHandle,
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<(), String> {
    let top_k = top_k.unwrap_or(5);
    let (_results, chunks) = search_with_cache(&root, &query, top_k)?;

    // 通过事件逐 chunk 推送
    for chunk in chunks {
        let _ = app.emit(EVT_KB_SEARCH_CHUNK, serde_json::json!({
            "type": chunk.r#type,
            "results": chunk.results,
            "count": chunk.count,
            "error": chunk.error,
        }));
    }

    Ok(())
}

#[tauri::command]
pub fn kb_get_structure(
    root: String,
    doc_id: String,
) -> Result<Option<Vec<TreeNode>>, String> {
    let guard = get_or_init_kb(&root)?;
    let kb = guard.get(&root).unwrap();
    Ok(kb.get_structure(&doc_id))
}

#[tauri::command]
pub fn kb_get_pages(root: String, doc_id: String, pages: String) -> Vec<PageContent> {
    if let Ok(guard) = get_or_init_kb(&root) {
        let kb = guard.get(&root).unwrap();
        kb.get_pages(&doc_id, &pages)
    } else {
        Vec::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kb_creation() {
        let dir = std::env::temp_dir().join(format!("kb_test_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir);
        assert!(kb.is_ok());
    }

    #[test]
    fn test_remove_nonexistent() {
        let dir = std::env::temp_dir().join(format!("kb_test_rm_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let kb = KnowledgeBase::new(&dir).unwrap();
        assert!(kb.remove_document("nonexistent").is_ok());
    }
}
