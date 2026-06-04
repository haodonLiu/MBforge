//! 知识库 — SQLite 统一存储（向量 + FTS5 + 文件缓存）
//!
//! 纯 SQLite 实现，零额外依赖：
//! - 向量搜索：BLOB 存储 + Rust 余弦计算（<20K chunks 时 <10ms）
//! - FTS5 全文搜索：精确关键词匹配（化学名、SMILES）
//! - 混合搜索：RRF 融合向量 + FTS5 结果
//! - 文件缓存：SHA-256 + mtime 检查

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Mutex, OnceLock};

use rusqlite::Connection;
use tauri::Emitter;

use crate::core::constants::EVT_KB_SEARCH_CHUNK;
use crate::core::embedding::Embedder;
use crate::core::sqlite_vector_store::{SqliteVectorStore, reciprocal_rank_fusion};

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

/// 知识库：SQLite（向量 + FTS5）+ 文件缓存
pub struct KnowledgeBase {
    vector_store: SqliteVectorStore,
    fts_conn: Mutex<Connection>,
    tree_index: Mutex<DocumentTreeIndex>,
    file_cache: FileCache,
    embedder: Option<Embedder>,
}

impl KnowledgeBase {
    /// 初始化知识库
    pub fn new(
        project_root: &Path,
        embed_config: Option<&crate::core::config::EmbedConfig>,
    ) -> Result<Self, String> {
        let kb_dir = project_root.join(".mbforge").join("knowledge_base");
        std::fs::create_dir_all(&kb_dir)
            .map_err(|e| format!("Failed to create KB dir: {}", e))?;

        let vectors_db_path = kb_dir.join("vectors.db");
        let cache_db_path = kb_dir.join("cache.db");

        // 向量存储
        let vector_store = SqliteVectorStore::open(&vectors_db_path, 384)?;

        // FTS5 全文搜索（独立连接，避免锁冲突）
        let fts_conn = Connection::open(&vectors_db_path)
            .map_err(|e| format!("Failed to open FTS DB: {}", e))?;
        fts_conn
            .execute_batch(
                "CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
                    id, text, content='vectors', content_rowid='rowid'
                )",
            )
            .map_err(|e| format!("Failed to create FTS5: {}", e))?;

        // 文件缓存
        let cache_conn = Connection::open(&cache_db_path)
            .map_err(|e| format!("Failed to open cache DB: {}", e))?;
        let file_cache = FileCache::new(cache_conn)?;

        let tree_index = DocumentTreeIndex::new(project_root);

        // Embedder
        let embedder = embed_config.and_then(|config| {
            if !config.api_key.is_empty() || config.provider == "qwen3" {
                Some(Embedder::new(config))
            } else {
                None
            }
        });

        Ok(Self {
            vector_store,
            fts_conn: Mutex::new(fts_conn),
            tree_index: Mutex::new(tree_index),
            file_cache,
            embedder,
        })
    }

    /// 是否有向量搜索能力
    pub fn has_vector_search(&self) -> bool {
        self.embedder.is_some()
    }

    /// 索引文档
    pub fn index_document(
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

        // 计算 embeddings
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

        // 写入向量表
        self.vector_store
            .upsert_vectors(&chunk_ids, doc_id, &texts, &metadatas, &vectors)?;

        // 同步 FTS5
        {
            let conn = self.fts_conn.lock().map_err(|e| format!("Lock error: {}", e))?;
            // 先删除旧条目
            let _ = conn.execute(
                "DELETE FROM sections_fts WHERE rowid IN (SELECT rowid FROM vectors WHERE doc_id = ?1)",
                rusqlite::params![doc_id],
            );
            // 插入新条目
            for (i, text) in texts.iter().enumerate() {
                let _ = conn.execute(
                    "INSERT INTO sections_fts (id, text) VALUES (?1, ?2)",
                    rusqlite::params![chunk_ids[i], text],
                );
            }
        }

        // 更新文档树
        let tree = self
            .tree_index
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        tree.index_document(doc_id, sections, page_texts)?;

        Ok(sections.len())
    }

    /// 搜索：有 Embedder 时用混合搜索，否则纯 FTS5
    pub fn search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        if self.has_vector_search() {
            self.hybrid_search(query, top_k)
        } else {
            self.fts_search(query, top_k)
        }
    }

    /// FTS5 全文搜索
    fn fts_search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        let clean_query = query
            .replace('"', "")
            .replace("'", "")
            .replace('-', " ")
            .split_whitespace()
            .filter(|w| w.len() >= 2)
            .collect::<Vec<_>>()
            .join(" OR ");

        if clean_query.is_empty() {
            return Ok(Vec::new());
        }

        let conn = self.fts_conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let mut stmt = conn
            .prepare(
                "SELECT v.chunk_id, v.text, v.metadata, rank
                 FROM sections_fts f
                 JOIN vectors v ON f.id = v.chunk_id
                 WHERE sections_fts MATCH ?1
                 ORDER BY rank
                 LIMIT ?2",
            )
            .map_err(|e| format!("Prepare failed: {}", e))?;

        let rows = stmt
            .query_map(rusqlite::params![clean_query, top_k as i64], |row| {
                Ok((
                    row.get::<_, String>(0)?,
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, f64>(3).unwrap_or(0.0),
                ))
            })
            .map_err(|e| format!("Query failed: {}", e))?;

        let mut results = Vec::new();
        for row in rows {
            let (id, text, meta_str, rank) = row.map_err(|e| format!("Row error: {}", e))?;
            let metadata: serde_json::Value =
                serde_json::from_str(&meta_str).unwrap_or(serde_json::json!({}));
            let score: f32 = if rank < 0.0 {
                1.0 / (1.0 + rank.abs() as f32)
            } else {
                0.5
            };
            results.push(SearchResult {
                id,
                text,
                metadata,
                score,
            });
        }

        Ok(results)
    }

    /// 混合搜索：FTS5 + 向量 + RRF 融合
    fn hybrid_search(&self, query: &str, top_k: usize) -> Result<Vec<SearchResult>, String> {
        let fts_results = self.fts_search(query, top_k * 3)?;

        let vec_results = if let Some(embedder) = &self.embedder {
            match embedder.embed_single(query) {
                Ok(embedding) => self
                    .vector_store
                    .search_vector(&embedding, top_k * 3, None)
                    .unwrap_or_default(),
                Err(e) => {
                    log::warn!("Embedding failed, FTS5-only: {}", e);
                    Vec::new()
                }
            }
        } else {
            Vec::new()
        };

        Ok(reciprocal_rank_fusion(fts_results, vec_results, top_k))
    }

    pub fn search_sync(&self, query: &str, top_k: usize) -> Vec<SearchResult> {
        match self.search(query, top_k) {
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
        self.vector_store.delete_doc(doc_id)?;

        let tree = self
            .tree_index
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
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

    pub fn file_cache(&self) -> &FileCache {
        &self.file_cache
    }
}

// ============================================================================
// 全局缓存
// ============================================================================

pub static KB_CACHE: OnceLock<Mutex<HashMap<String, KnowledgeBase>>> = OnceLock::new();
static SEMANTIC_CACHE: OnceLock<Mutex<HashMap<String, SemanticCache>>> = OnceLock::new();

/// 获取或初始化 KB 实例
pub fn get_or_init_kb(
    root: &str,
) -> Result<std::sync::MutexGuard<'static, HashMap<String, KnowledgeBase>>, String> {
    let cache = KB_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    let guard = cache
        .lock()
        .map_err(|e| format!("KB cache lock error: {}", e))?;
    if guard.contains_key(root) {
        return Ok(guard);
    }
    drop(guard);

    let config = crate::core::config::AppConfig::load();
    let kb = KnowledgeBase::new(std::path::Path::new(root), Some(&config.embed))?;

    let mut guard = cache
        .lock()
        .map_err(|e| format!("KB cache lock error: {}", e))?;
    guard.insert(root.to_string(), kb);
    Ok(guard)
}

fn get_or_init_semantic_cache(
    root: &str,
) -> std::sync::MutexGuard<'static, HashMap<String, SemanticCache>> {
    let cache = SEMANTIC_CACHE.get_or_init(|| Mutex::new(HashMap::new()));
    let mut guard = cache.lock().unwrap_or_else(|e| e.into_inner());
    if !guard.contains_key(root) {
        let sc = SemanticCache::new(
            std::path::Path::new(root),
            SemanticCacheConfig::default(),
        );
        guard.insert(root.to_string(), sc);
    }
    guard
}

/// 搜索核心逻辑
pub fn search_with_cache(
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

    // 2. 搜索
    let guard = get_or_init_kb(root)?;
    let kb = guard
        .get(root)
        .ok_or_else(|| format!("Knowledge base not initialized for root: {}", root))?;
    let results = kb
        .search(query, top_k)
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
// Tauri 命令
// ============================================================================

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

#[tauri::command]
pub async fn kb_search_stream(
    app: tauri::AppHandle,
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<(), String> {
    let top_k = top_k.unwrap_or(5);
    let (_results, chunks) = search_with_cache(&root, &query, top_k)?;

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
pub fn kb_get_structure(root: String, doc_id: String) -> Result<Option<Vec<TreeNode>>, String> {
    let guard = get_or_init_kb(&root)?;
    let kb = guard
        .get(&root)
        .ok_or_else(|| format!("Knowledge base not found for root: {}", root))?;
    Ok(kb.get_structure(&doc_id))
}

#[tauri::command]
pub fn kb_get_pages(root: String, doc_id: String, pages: String) -> Vec<PageContent> {
    if let Ok(guard) = get_or_init_kb(&root) {
        let kb = guard.get(&root).expect("KB just initialized for root");
        kb.get_pages(&doc_id, &pages)
    } else {
        Vec::new()
    }
}
