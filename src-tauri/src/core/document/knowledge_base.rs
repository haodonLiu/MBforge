//! 知识库 — SQLite 统一存储（向量 + FTS5 + 文件缓存）
//!
//! 纯 SQLite 实现，零额外依赖：
//! - 向量搜索：BLOB 存储 + Rust 余弦计算（<20K chunks 时 <10ms）
//! - FTS5 全文搜索：精确关键词匹配（化学名、SMILES）
//! - 混合搜索：RRF 融合向量 + FTS5 结果
//! - 文件缓存：SHA-256 + mtime 检查
//!
//! 存储文件：`.mbforge/knowledge_base.db`（单文件，替代旧的 vectors.db + cache.db）

use std::path::Path;
use std::sync::{Mutex, OnceLock};

use dashmap::DashMap;

use rusqlite::Connection;
use tauri::Emitter;

use crate::core::config::constants::EVT_KB_SEARCH_CHUNK;
use crate::core::error::{AppError, AppResult, ErrorCode};
use crate::core::vector::embedding::Embedder;
use crate::core::vector::sqlite_vector_store::{SqliteVectorStore, reciprocal_rank_fusion};

use crate::core::vector::vector_store::SearchResult;
use super::document_tree::DocumentTreeIndex;
use super::file_cache::FileCache;
use super::semantic_cache::{SemanticCache, SemanticCacheConfig};
use super::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
use crate::core::types::{SectionChunk, TreeNode};

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
        embed_config: Option<&crate::core::config::settings::EmbedConfig>,
    ) -> AppResult<Self> {
        let meta_dir = project_root.join(".mbforge");
        std::fs::create_dir_all(&meta_dir)?;

        let db_path = meta_dir.join("knowledge_base.db");
        let legacy_vec = meta_dir.join("knowledge_base").join("vectors.db");
        let legacy_cache = meta_dir.join("knowledge_base").join("cache.db");

        // 向后兼容：从旧数据库迁移（仅当新库不存在且旧库存在时）
        if !db_path.exists() && (legacy_vec.exists() || legacy_cache.exists()) {
            log::info!("Migrating legacy KB databases to knowledge_base.db");
            Self::migrate_legacy(&db_path, &legacy_vec, &legacy_cache)?;
        }

        // 主连接：向量存储
        let vec_conn = Connection::open(&db_path)?;
        let vector_store = SqliteVectorStore::from_conn(vec_conn, 384)?;

        // 第二个连接：文件缓存（同一文件，WAL 模式下并发读安全）
        let cache_conn = Connection::open(&db_path)?;
        let file_cache = FileCache::new(cache_conn)?;

        // 第三个连接：FTS5（独立连接避免写锁冲突）
        let fts_conn = Connection::open(&db_path)?;
        fts_conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA busy_timeout=5000;
             PRAGMA wal_autocheckpoint=1000;",
        )?;
        fts_conn.execute_batch(
            "CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
                id, text
            )",
        )?;

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

    /// 从旧的 vectors.db + cache.db 迁移到统一的 knowledge_base.db
    fn migrate_legacy(
        new_path: &Path,
        legacy_vec: &Path,
        legacy_cache: &Path,
    ) -> AppResult<()> {
        let conn = Connection::open(new_path)?;

        // 初始化新库 schema
        SqliteVectorStore::setup_schema(&conn, 384)?;
        FileCache::setup_schema(&conn)?;

        // 迁移 vectors 表
        if legacy_vec.exists() {
            let vec_path = legacy_vec.to_string_lossy();
            conn.execute_batch(&format!(
                "ATTACH DATABASE '{}' AS old_vec",
                vec_path.replace('\\', "/").replace('\'', "''")
            ))?;

            // 复制 vectors 数据（旧表可能没有 dim 列）
            conn.execute(
                "INSERT INTO vectors (chunk_id, doc_id, text, metadata, embedding, dim)
                 SELECT chunk_id, doc_id, text, metadata, embedding, 0
                 FROM old_vec.vectors",
                [],
            )?;

            // 重建 FTS5
            conn.execute_batch(
                "INSERT INTO sections_fts (id, text)
                 SELECT chunk_id, text FROM vectors"
            )?;

            conn.execute_batch("DETACH DATABASE old_vec")?;
            log::info!("Migrated vectors from legacy database");
        }

        // 迁移 file_cache 表
        if legacy_cache.exists() {
            let cache_path = legacy_cache.to_string_lossy();
            conn.execute_batch(&format!(
                "ATTACH DATABASE '{}' AS old_cache",
                cache_path.replace('\\', "/").replace('\'', "''")
            ))?;

            conn.execute(
                "INSERT INTO file_cache
                 SELECT * FROM old_cache.file_cache",
                [],
            )?;

            conn.execute_batch("DETACH DATABASE old_cache")?;
            log::info!("Migrated file_cache from legacy database");
        }

        Ok(())
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
    ) -> AppResult<usize> {
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
            let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
            // 先删除旧条目
            let _ = conn.execute(
                "DELETE FROM sections_fts WHERE id LIKE ?1 || '%'",
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
        let tree = self.tree_index.lock().map_err(|e| e.to_string())?;
        tree.index_document(doc_id, sections, page_texts)
            .map_err(|e| AppError::new(ErrorCode::Unknown, e))?;

        Ok(sections.len())
    }

    /// 搜索：有 Embedder 时用混合搜索，否则纯 FTS5
    pub fn search(&self, query: &str, top_k: usize) -> AppResult<Vec<SearchResult>> {
        if self.has_vector_search() {
            self.hybrid_search(query, top_k)
        } else {
            self.fts_search(query, top_k)
        }
    }

    /// FTS5 全文搜索
    fn fts_search(&self, query: &str, top_k: usize) -> AppResult<Vec<SearchResult>> {
        let clean_query = query
            .replace('"', "")
            .replace('\'', "")
            .replace('-', " ")
            .split_whitespace()
            .filter(|w| w.len() >= 2)
            .collect::<Vec<_>>()
            .join(" OR ");

        if clean_query.is_empty() {
            return Ok(Vec::new());
        }

        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut stmt = conn.prepare(
            "SELECT v.chunk_id, v.text, v.metadata, rank
             FROM sections_fts f
             JOIN vectors v ON f.id = v.chunk_id
             WHERE sections_fts MATCH ?1
             ORDER BY rank
             LIMIT ?2",
        )?;

        let rows = stmt.query_map(rusqlite::params![clean_query, top_k as i64], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, f64>(3).unwrap_or(0.0),
            ))
        })?;

        let mut results = Vec::new();
        for row in rows {
            let (id, text, meta_str, rank) = row?;
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
    fn hybrid_search(&self, query: &str, top_k: usize) -> AppResult<Vec<SearchResult>> {
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

    pub fn remove_document(&self, doc_id: &str) -> AppResult<()> {
        self.vector_store.delete_doc(doc_id)?;

        let tree = self.tree_index.lock().map_err(|e| e.to_string())?;
        tree.remove_document(doc_id)
            .map_err(|e| AppError::new(ErrorCode::Unknown, e))
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

pub static KB_CACHE: OnceLock<DashMap<String, KnowledgeBase>> = OnceLock::new();
static SEMANTIC_CACHE: OnceLock<DashMap<String, SemanticCache>> = OnceLock::new();

/// 获取或初始化 KB 实例
pub fn get_or_init_kb(
    root: &str,
) -> AppResult<dashmap::mapref::one::Ref<'static, String, KnowledgeBase>> {
    let cache = KB_CACHE.get_or_init(|| DashMap::new());
    if let Some(entry) = cache.get(root) {
        return Ok(entry);
    }

    let config = crate::core::config::settings::AppConfig::load();
    let kb = KnowledgeBase::new(std::path::Path::new(root), Some(&config.embed))?;

    cache.insert(root.to_string(), kb);
    Ok(cache.get(root).expect("just inserted"))
}

fn get_or_init_semantic_cache(
    root: &str,
) -> dashmap::mapref::one::Ref<'static, String, SemanticCache> {
    let cache = SEMANTIC_CACHE.get_or_init(|| DashMap::new());
    if let Some(entry) = cache.get(root) {
        return entry;
    }
    let sc = SemanticCache::new(
        std::path::Path::new(root),
        SemanticCacheConfig::default(),
    );
    cache.insert(root.to_string(), sc);
    cache.get(root).expect("just inserted")
}

/// 搜索核心逻辑
pub fn search_with_cache(
    root: &str,
    query: &str,
    top_k: usize,
) -> AppResult<(Vec<serde_json::Value>, Vec<StreamingResult>)> {
    // 1. L1 缓存命中？
    {
        let sc = get_or_init_semantic_cache(root);
        if let Some(cached) = sc.value().get_l1(query) {
            let stream = StreamingSearch::new(StreamingSearchConfig::default())
                .execute(cached.clone(), top_k);
            return Ok((cached, stream));
        }
    }

    // 2. 搜索
    let kb = get_or_init_kb(root)?;
    let results = kb.search(query, top_k)?;

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
        let sc = get_or_init_semantic_cache(root);
        sc.value().store(query, json_results.clone());
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
    let (results, _) = search_with_cache(&root, &query, top_k).map_err(|e| e.to_string())?;
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
    let (_results, chunks) = search_with_cache(&root, &query, top_k).map_err(|e| e.to_string())?;

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
    let kb = get_or_init_kb(&root).map_err(|e| e.to_string())?;
    Ok(kb.get_structure(&doc_id))
}

#[tauri::command]
pub fn kb_get_pages(root: String, doc_id: String, pages: String) -> Vec<PageContent> {
    if let Ok(kb) = get_or_init_kb(&root) {
        kb.get_pages(&doc_id, &pages)
    } else {
        Vec::new()
    }
}
