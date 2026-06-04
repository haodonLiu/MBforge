//! 知识库 — LanceDB 统一存储（向量 + BM25 混合搜索）
//!
//! 使用 LanceDB 作为唯一知识库存储：
//! - 向量搜索：语义相似度（自然语言查询）
//! - BM25 全文搜索：精确关键词匹配（化学名、SMILES）
//! - 混合搜索：execute_hybrid 原生融合
//!
//! 文件缓存使用独立的 SQLite 数据库（简单的 KV 缓存不适合 LanceDB）。
use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex, OnceLock};

use rusqlite::Connection;
use tauri::Emitter;

use crate::core::constants::EVT_KB_SEARCH_CHUNK;
use crate::core::embedding::Embedder;
use crate::core::lance_store::LanceVectorStore;

use super::super::vector_store::SearchResult;
use super::document_tree::DocumentTreeIndex;
use super::file_cache::FileCache;
use super::semantic_cache::{SemanticCache, SemanticCacheConfig};
use super::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
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

/// 知识库：LanceDB（向量 + BM25）+ 文件缓存（SQLite）
pub struct KnowledgeBase {
    lance_store: LanceVectorStore,
    tree_index: Mutex<DocumentTreeIndex>,
    file_cache: FileCache,
    embedder: Option<Embedder>,
}

impl KnowledgeBase {
    /// 初始化知识库（必须在 async 上下文中调用）
    pub async fn new(
        project_root: &Path,
        embed_config: Option<&crate::core::config::EmbedConfig>,
    ) -> Result<Self, String> {
        let kb_dir = project_root.join(".mbforge").join("knowledge_base");
        std::fs::create_dir_all(&kb_dir)
            .map_err(|e| format!("Failed to create KB dir: {}", e))?;

        let lance_dir = kb_dir.join("lancedb");
        let cache_db_path = kb_dir.join("cache.db");

        // 初始化 LanceDB（知识库存储）
        let lance_store = LanceVectorStore::new(&lance_dir, 384).await?;

        // 尝试创建 FTS 索引（幂等操作）
        if let Err(e) = lance_store.create_fts_index().await {
            log::warn!("FTS index creation skipped (may already exist): {}", e);
        }

        // 初始化 SQLite 文件缓存
        let cache_conn = Connection::open(&cache_db_path)
            .map_err(|e| format!("Failed to open cache DB: {}", e))?;
        let file_cache = FileCache::new(cache_conn)?;

        let tree_index = DocumentTreeIndex::new(project_root);

        // 初始化 Embedder
        let embedder = embed_config.and_then(|config| {
            if !config.api_key.is_empty() || config.provider == "qwen3" {
                Some(Embedder::new(config))
            } else {
                None
            }
        });

        Ok(Self {
            lance_store,
            tree_index: Mutex::new(tree_index),
            file_cache,
            embedder,
        })
    }

    /// 是否有向量搜索能力（需要 Embedder）
    pub fn has_vector_search(&self) -> bool {
        self.embedder.is_some()
    }

    pub async fn index_document(
        &self,
        doc_id: &str,
        sections: &[SectionChunk],
        page_texts: &[String],
    ) -> Result<usize, String> {
        let chunk_ids: Vec<String> = sections
            .iter()
            .enumerate()
            .map(|(i, _)| format!("{}:sec{}", doc_id, i))
            .collect();
        let texts: Vec<String> = sections.iter().map(|s| s.text.clone()).collect();
        let metadatas: Vec<String> = sections
            .iter()
            .map(|s| {
                serde_json::to_string(&serde_json::json!({
                    "title": s.title,
                    "path": s.path,
                    "page_start": s.page_start,
                    "page_end": s.page_end,
                }))
                .unwrap_or_default()
            })
            .collect();

        // 计算 embeddings（如果有 Embedder）
        let vectors: Vec<Vec<f32>> = if let Some(embedder) = &self.embedder {
            match embedder.embed(texts.clone()) {
                Ok(v) => v,
                Err(e) => {
                    log::warn!("Embedding failed for {}: {}, using zero vectors", doc_id, e);
                    vec![vec![0.0; 384]; sections.len()]
                }
            }
        } else {
            vec![vec![0.0; 384]; sections.len()]
        };

        // 写入 LanceDB
        self.lance_store
            .upsert_vectors(&chunk_ids, doc_id, &texts, &metadatas, &vectors)
            .await?;

        // 更新文档树索引
        let tree = self
            .tree_index
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;

        Ok(sections.len())
    }

    /// 搜索：有 Embedder 时用混合搜索，否则纯 BM25
    pub async fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        if let Some(embedder) = &self.embedder {
            // 混合搜索：向量 + BM25
            match embedder.embed_single(query) {
                Ok(embedding) => {
                    self.lance_store
                        .search_hybrid(query, &embedding, top_k, None)
                        .await
                }
                Err(e) => {
                    log::warn!("Embedding failed, falling back to BM25: {}", e);
                    self.lance_store.search_text(query, top_k, None).await
                }
            }
        } else {
            // 纯 BM25 文本搜索
            self.lance_store.search_text(query, top_k, None).await
        }
    }

    pub async fn search_sync(&self, query: &str, top_k: usize) -> Vec<SearchResult> {
        match self.search(query, top_k).await {
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

    pub async fn remove_document(&self, doc_id: &str) -> Result<(), String> {
        self.lance_store.delete_doc(doc_id).await?;

        let tree = self
            .tree_index
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        tree.remove_document(doc_id)
    }

    pub async fn stats(&self) -> KbStats {
        let total_sections = self.lance_store.count().await.unwrap_or(0);
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

    /// 获取文件缓存引用
    pub fn file_cache(&self) -> &FileCache {
        &self.file_cache
    }
}

// ============================================================================
// 全局缓存：KB 实例 + SemanticCache
// ============================================================================

/// KB 实例缓存（按 project_root 键）。
///
/// 之前是 `OnceLock<tokio::Mutex<HashMap>>` 加 double-checked-locking：
/// 两个并发调用都可能看到 `contains_key=false` 然后各自构造 `KnowledgeBase`
/// （含 SQLite + LanceDB 连接），后插入者覆盖前者，前者持有的连接
/// 在 Drop 时还要尝试关闭一份已不归它管的文件锁。
///
/// 修复：保持 `tokio::sync::Mutex` 以便跨 `await` 持有锁，但**不释放锁**
/// 就在 `await KnowledgeBase::new`，保证同一时间只有一个线程能执行
/// 构造路径。
pub static KB_CACHE: OnceLock<tokio::sync::Mutex<HashMap<String, Arc<KnowledgeBase>>>> =
    OnceLock::new();

/// SemanticCache 实例缓存（按 project_root 键）
static SEMANTIC_CACHE: OnceLock<Mutex<HashMap<String, SemanticCache>>> = OnceLock::new();

/// 获取或初始化带 Embedder 的 KB 实例。
///
/// 返回 `Arc<KnowledgeBase>` 而非 `MutexGuard`，调用方不再需要先 `get(root)`
/// 再 `ok_or_else` 校验（那个分支在 race 之前是死代码、race 时是 bug）。
///
/// 并发安全：把 lock 一直持到 `KnowledgeBase::new` 完成。读多写少场景下
/// `HashMap` 的 read 不需要锁，但 KB 构造是异步的，必须避免在锁外 await。
pub async fn get_or_init_kb(root: &str) -> Result<Arc<KnowledgeBase>, String> {
    let cache = KB_CACHE.get_or_init(|| tokio::sync::Mutex::new(HashMap::new()));
    let mut guard = cache.lock().await;

    if let Some(kb) = guard.get(root) {
        return Ok(kb.clone());
    }

    // Hold the lock across the await — this is the critical part.
    // `tokio::sync::Mutex` is specifically designed for this.
    let config = crate::core::config::AppConfig::load();
    let kb = KnowledgeBase::new(std::path::Path::new(root), Some(&config.embed))
        .await
        .map_err(|e| format!("KnowledgeBase init failed: {}", e))?;
    let arc = Arc::new(kb);
    guard.insert(root.to_string(), arc.clone());
    Ok(arc)
}

fn get_or_init_semantic_cache(
    root: &str,
) -> std::sync::MutexGuard<'static, HashMap<String, SemanticCache>> {
    let cache = SEMANTIC_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    // 之前用 `unwrap_or_else(|e| e.into_inner())` 静默吞 poison，
    // 这会掩盖持锁线程 panic 后的不一致状态。改为显式 ? 传播错误。
    let mut guard = match cache.lock() {
        Ok(g) => g,
        Err(poisoned) => {
            log::error!("Semantic cache mutex poisoned: {}", poisoned);
            poisoned.into_inner()
        }
    };
    if !guard.contains_key(root) {
        let sc = SemanticCache::new(
            std::path::Path::new(root),
            SemanticCacheConfig::default(),
        );
        guard.insert(root.to_string(), sc);
    }
    guard
}

/// 搜索核心逻辑：semantic_cache (L1) → LanceDB hybrid → cache store → stream_search
pub async fn search_with_cache(
    root: &str,
    query: &str,
    top_k: usize,
) -> Result<(Vec<serde_json::Value>, Vec<StreamingResult>), String> {
    // 1. L1 缓存命中？
    {
        let sc_guard = get_or_init_semantic_cache(root);
        if let Some(cached) = sc_guard.get(root).and_then(|sc| sc.get_l1(query)) {
            let stream = StreamingSearch::new(StreamingSearchConfig::default())
                .execute(cached.clone(), top_k);
            return Ok((cached, stream));
        }
    }

    // 2. LanceDB 混合搜索
    // 返回 `Arc<KnowledgeBase>` —— 之前用 `get_or_init_kb` 拿到 MutexGuard 再
    // `get(root).ok_or_else` 校验是 [Track B-B8] 标记的死代码；现在
    // `get_or_init_kb` 已经返回 Arc，免去二次查找。
    let kb = get_or_init_kb(root).await?;
    let results = kb
        .search(query, top_k)
        .await
        .map_err(|e| format!("Search failed: {}", e))?;
    let json_results: Vec<serde_json::Value> = results
        .into_iter()
        .map(|r| {
            serde_json::json!({
                "id": r.id,
                "text": r.text,
                "metadata": r.metadata,
                "score": r.score,
            })
        })
        .collect();

    // 3. 写入缓存
    {
        let mut sc_guard = get_or_init_semantic_cache(root);
        if let Some(sc) = sc_guard.get_mut(root) {
            sc.store(query, json_results.clone());
        }
    }

    // 4. 流式分批
    let stream =
        StreamingSearch::new(StreamingSearchConfig::default()).execute(json_results.clone(), top_k);

    Ok((json_results, stream))
}

// ============================================================================
// Tauri 命令层
// ============================================================================

/// 搜索（返回完整结果）
#[tauri::command]
pub async fn kb_search(
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<Vec<serde_json::Value>, String> {
    let top_k = top_k.unwrap_or(5);
    let (results, _) = search_with_cache(&root, &query, top_k).await?;
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
    let (_results, chunks) = search_with_cache(&root, &query, top_k).await?;

    for chunk in chunks {
        let _ = app.emit(
            EVT_KB_SEARCH_CHUNK,
            serde_json::json!({
                "type": chunk.r#type,
                "results": chunk.results,
                "count": chunk.count,
                "error": chunk.error,
            }),
        );
    }

    Ok(())
}

#[tauri::command]
pub async fn kb_get_structure(root: String, doc_id: String) -> Result<Option<Vec<TreeNode>>, String> {
    // `get_or_init_kb` 现在直接返回 `Arc<KnowledgeBase>`，不再需要二次 `get`
    // 加 `ok_or_else`（那是 [Track B-B8] 标记的死代码）。
    let kb = get_or_init_kb(&root).await?;
    Ok(kb.get_structure(&doc_id))
}

#[tauri::command]
pub async fn kb_get_pages(root: String, doc_id: String, pages: String) -> Vec<PageContent> {
    match get_or_init_kb(&root).await {
        Ok(kb) => kb.get_pages(&doc_id, &pages),
        Err(e) => {
            log::warn!("kb_get_pages: get_or_init_kb failed: {}", e);
            Vec::new()
        }
    }
}
