#![allow(dead_code)]
//! 知识库 — SQLite 业务表 + Zvec 搜索封装。
//!
//! - SQLite：coref / file_cache / document_tree / semantic_cache 等业务表。
//! - Zvec：向量 + 全文 + 混合搜索（由 `SearchEngine` 封装）。
//!
//! 存储文件：
//! - `.mbforge/knowledge_base.db`（SQLite 业务表）
//! - `.mbforge/search.zvec/`（Zvec collection）

use std::path::Path;
use std::sync::{Arc, Mutex, OnceLock};

use dashmap::DashMap;

use rusqlite::Connection;
use tauri::Emitter;

use crate::vector::embedding::Embedder;
use mbforge_infra::config::constants::{EVT_KB_SEARCH_CHUNK, INDEX_DIR, PROJECT_META_DIR};
use mbforge_infra::db::SharedConn;
use mbforge_infra::error::{AppError, AppResult, ErrorCode};

use super::document_tree::DocumentTreeIndex;
use super::file_cache::FileCache;
use super::search_engine::{SearchEngine, SearchResult};
use super::semantic_cache::{SemanticCache, SemanticCacheConfig};
use super::stream_search::{StreamingResult, StreamingSearch, StreamingSearchConfig};
use mbforge_infra::types::{SectionChunk, TreeNode};

pub use super::document_tree::PageContent;

fn count_nodes(nodes: &[TreeNode]) -> usize {
    nodes.iter().map(|n| 1 + count_nodes(&n.nodes)).sum()
}

pub struct KbStats {
    pub document_count: usize,
    pub section_count: usize,
    pub total_sections: usize,
}

// ============================================================================
// Coref 持久化（figure_labels + coref_predictions）
// ============================================================================

/// 图内 OCR 检出的 label 标注
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FigureLabel {
    pub id: i64,
    pub doc_id: String,
    pub page: i64,
    pub label_bbox: Vec<f64>, // [x1, y1, x2, y2] in image coords
    pub label_text: String,
    pub ocr_conf: f64,
    pub image_path: Option<String>,
}

/// 分子-标识符配对预测
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CorefPrediction {
    pub id: i64,
    pub doc_id: String,
    pub page: i64,
    pub mol_smiles: Option<String>,
    pub mol_bbox: Option<Vec<f64>>,
    pub mol_conf: Option<f64>,
    pub label_id: Option<i64>,
    pub label_text: Option<String>,
    pub label_bbox: Option<Vec<f64>>,
    pub confidence: f64,
    pub source: String, // 'geometric' | 'llm' | 'manual'
    pub is_confirmed: bool,
    /// 所属 figure 路径 — 用于前端把 figure 局部 0-1 bbox 投影到 PDF 页面坐标
    #[serde(default)]
    pub image_path: Option<String>,
}

/// 设置 figure_annotations 相关 schema（幂等）
fn setup_figure_annotations_schema(conn: &Connection) -> rusqlite::Result<()> {
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS figure_labels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            page INTEGER NOT NULL,
            label_bbox TEXT NOT NULL,
            label_text TEXT NOT NULL,
            ocr_conf REAL NOT NULL,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(doc_id, page, label_bbox, label_text)
        );
        CREATE INDEX IF NOT EXISTS idx_figure_labels_doc ON figure_labels(doc_id, page);
        CREATE INDEX IF NOT EXISTS idx_figure_labels_text ON figure_labels(label_text);

        CREATE TABLE IF NOT EXISTS coref_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT NOT NULL,
            page INTEGER NOT NULL,
            mol_smiles TEXT,
            mol_bbox TEXT,
            mol_conf REAL,
            label_id INTEGER,
            label_text TEXT,
            label_bbox TEXT,
            confidence REAL NOT NULL,
            source TEXT NOT NULL,
            is_confirmed INTEGER NOT NULL DEFAULT 0,
            image_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_coref_pred_doc ON coref_predictions(doc_id, page);
        CREATE INDEX IF NOT EXISTS idx_coref_pred_label ON coref_predictions(label_text);
        CREATE INDEX IF NOT EXISTS idx_coref_pred_smiles ON coref_predictions(mol_smiles);
        CREATE INDEX IF NOT EXISTS idx_coref_pred_label_id ON coref_predictions(label_id);
        CREATE INDEX IF NOT EXISTS idx_coref_pred_confirmed ON coref_predictions(is_confirmed);
        CREATE INDEX IF NOT EXISTS idx_coref_pred_image_path ON coref_predictions(image_path);",
    )?;

    // 旧库兼容：image_path 列在 v3 才加
    add_column_if_missing(conn, "coref_predictions", "image_path", "TEXT")?;
    Ok(())
}

/// 兼容旧库：检测列是否存在，不存在则 ALTER TABLE ADD COLUMN
fn add_column_if_missing(
    conn: &Connection,
    table: &str,
    column: &str,
    type_sql: &str,
) -> rusqlite::Result<()> {
    let mut stmt = conn.prepare(&format!("PRAGMA table_info({})", table))?;
    let mut rows = stmt.query([])?;
    while let Some(row) = rows.next()? {
        let name: String = row.get(1)?;
        if name == column {
            return Ok(());
        }
    }
    let sql = format!("ALTER TABLE {} ADD COLUMN {} {}", table, column, type_sql);
    conn.execute(&sql, [])?;
    Ok(())
}

/// 知识库：SQLite 业务表 + Zvec 搜索。
pub struct KnowledgeBase {
    search_engine: SearchEngine,
    fts_conn: SharedConn,
    tree_index: Mutex<DocumentTreeIndex>,
    file_cache: FileCache,
    embedder: Option<Embedder>,
}

impl KnowledgeBase {
    /// 初始化知识库。
    pub fn new(
        project_root: &Path,
        embed_config: Option<&mbforge_infra::config::settings::EmbedConfig>,
    ) -> AppResult<Self> {
        let index_dir = project_root.join(INDEX_DIR);
        std::fs::create_dir_all(&index_dir)?;

        let db_path = index_dir.join("knowledge_base.db");
        let conn = Connection::open(&db_path)?;
        let shared_conn = Arc::new(Mutex::new(conn));

        let file_cache = FileCache::from_shared_conn(Arc::clone(&shared_conn))?;

        let dim = embed_config.map(|c| c.effective_dim()).unwrap_or(1024);
        let search_path = project_root.join(PROJECT_META_DIR).join("search.zvec");
        let search_engine = SearchEngine::open(&search_path, dim)?;

        {
            let guard = shared_conn.lock().map_err(|e| e.to_string())?;
            guard.execute_batch(
                "PRAGMA journal_mode=WAL;
                 PRAGMA busy_timeout=5000;
                 PRAGMA wal_autocheckpoint=1000;",
            )?;
            setup_figure_annotations_schema(&guard)?;
        }

        let tree_index = DocumentTreeIndex::new(project_root);

        let embedder = embed_config.and_then(|config| {
            if !config.api_key.is_empty() || config.provider == "qwen3" {
                Some(Embedder::new(config))
            } else {
                None
            }
        });

        Ok(Self {
            search_engine,
            fts_conn: shared_conn,
            tree_index: Mutex::new(tree_index),
            file_cache,
            embedder,
        })
    }

    /// 从 DbManager 共享连接初始化。
    pub fn with_shared_conn(
        project_root: &Path,
        embed_config: Option<&mbforge_infra::config::settings::EmbedConfig>,
        shared_conn: SharedConn,
    ) -> AppResult<Self> {
        let index_dir = project_root.join(INDEX_DIR);
        std::fs::create_dir_all(&index_dir)?;

        let file_cache = FileCache::from_shared_conn(Arc::clone(&shared_conn))?;

        let dim = embed_config.map(|c| c.effective_dim()).unwrap_or(1024);
        let search_path = project_root.join(PROJECT_META_DIR).join("search.zvec");
        let search_engine = SearchEngine::open(&search_path, dim)?;

        {
            let guard = shared_conn.lock().map_err(|e| e.to_string())?;
            guard.execute_batch(
                "PRAGMA journal_mode=WAL;
                 PRAGMA busy_timeout=5000;
                 PRAGMA wal_autocheckpoint=1000;",
            )?;
            setup_figure_annotations_schema(&guard)?;
        }

        let tree_index = DocumentTreeIndex::new(project_root);

        let embedder = embed_config.and_then(|config| {
            if !config.api_key.is_empty() || config.provider == "qwen3" {
                Some(Embedder::new(config))
            } else {
                None
            }
        });

        Ok(Self {
            search_engine,
            fts_conn: shared_conn,
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
    ) -> AppResult<usize> {
        let chunk_ids: Vec<String> = sections
            .iter()
            .enumerate()
            .map(|(i, _)| format!("{}__sec{}", doc_id, i))
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
        let dim = self.search_engine.dim();
        let vectors: Vec<Vec<f32>> = if let Some(embedder) = &self.embedder {
            match embedder.embed(texts.clone()) {
                Ok(v) => v,
                Err(e) => {
                    log::warn!("Embedding failed for {}: {}, using zero vectors", doc_id, e);
                    vec![vec![0.0; dim]; sections.len()]
                }
            }
        } else {
            vec![vec![0.0; dim]; sections.len()]
        };

        // 写入 Zvec
        self.search_engine
            .index_document(doc_id, &chunk_ids, &texts, &metadatas, &vectors)?;

        // 更新文档树
        let tree = self.tree_index.lock().map_err(|e| e.to_string())?;
        tree.index_document(doc_id, sections, page_texts)
            .map_err(|e| AppError::new(ErrorCode::Unknown, e))?;

        Ok(sections.len())
    }

    /// 搜索：有 Embedder 时用混合搜索，否则纯 FTS。
    pub fn search(&self, query: &str, top_k: usize) -> AppResult<Vec<SearchResult>> {
        if self.has_vector_search() {
            self.hybrid_search(query, top_k)
        } else {
            self.search_engine.text_search(query, top_k, None)
        }
    }

    /// 混合搜索：向量 + FTS + RRF 融合。
    fn hybrid_search(&self, query: &str, top_k: usize) -> AppResult<Vec<SearchResult>> {
        if let Some(embedder) = &self.embedder {
            match embedder.embed_single(query) {
                Ok(embedding) => self
                    .search_engine
                    .hybrid_search(&embedding, query, top_k, None),
                Err(e) => {
                    log::warn!("Embedding failed, FTS-only: {}", e);
                    self.search_engine.text_search(query, top_k, None)
                }
            }
        } else {
            self.search_engine.text_search(query, top_k, None)
        }
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
        self.search_engine.delete_document(doc_id)?;

        let tree = self.tree_index.lock().map_err(|e| e.to_string())?;
        tree.remove_document(doc_id)
            .map_err(|e| AppError::new(ErrorCode::Unknown, e))
    }

    pub fn stats(&self) -> KbStats {
        let total_sections = self.search_engine.count().unwrap_or(0);
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

    // ========================================================================
    // Coref 持久化 CRUD
    // ========================================================================

    /// 插入图内 label 标注（按 (doc_id, page, label_bbox, label_text) 去重）
    pub fn insert_figure_labels(
        &self,
        doc_id: &str,
        page: i64,
        labels: &[(Vec<f64>, String, f64, Option<String>)], // (bbox, text, ocr_conf, image_path)
    ) -> AppResult<usize> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut inserted = 0;
        for (bbox, text, ocr_conf, image_path) in labels {
            let bbox_json = serde_json::to_string(bbox).unwrap_or_else(|_| "[]".to_string());
            let res = conn.execute(
                "INSERT OR IGNORE INTO figure_labels
                 (doc_id, page, label_bbox, label_text, ocr_conf, image_path)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                rusqlite::params![doc_id, page, bbox_json, text, ocr_conf, image_path],
            )?;
            if res > 0 {
                inserted += 1;
            }
        }
        Ok(inserted)
    }

    /// 插入/更新 coref 配对预测（按 (doc_id, page, label_id) 去重更新）
    pub fn upsert_coref_predictions(
        &self,
        doc_id: &str,
        page: i64,
        predictions: &[CorefPrediction],
    ) -> AppResult<usize> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut upserted = 0;
        for p in predictions {
            let mol_bbox_json = p
                .mol_bbox
                .as_ref()
                .and_then(|b| serde_json::to_string(b).ok());
            let label_bbox_json = p
                .label_bbox
                .as_ref()
                .and_then(|b| serde_json::to_string(b).ok());
            let is_confirmed_i = if p.is_confirmed { 1 } else { 0 };
            // 用 (doc_id, page, mol_smiles, label_text) 作为唯一键 — 允许更新
            // 同 mol+label 多次配对只保留最新
            let res = conn.execute(
                "INSERT INTO coref_predictions
                 (doc_id, page, mol_smiles, mol_bbox, mol_conf, label_id,
                  label_text, label_bbox, confidence, source, is_confirmed, image_path)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)
                 ON CONFLICT(doc_id, page, mol_smiles, label_text) DO UPDATE SET
                  confidence = excluded.confidence,
                  source = excluded.source,
                  is_confirmed = excluded.is_confirmed,
                  image_path = excluded.image_path,
                  updated_at = CURRENT_TIMESTAMP",
                rusqlite::params![
                    doc_id,
                    page,
                    p.mol_smiles,
                    mol_bbox_json,
                    p.mol_conf,
                    p.label_id,
                    p.label_text,
                    label_bbox_json,
                    p.confidence,
                    p.source,
                    is_confirmed_i,
                    p.image_path,
                ],
            )?;
            upserted += res;
        }
        Ok(upserted)
    }

    /// 查询指定 (doc_id, page) 的所有 label 标注
    pub fn get_figure_labels(&self, doc_id: &str, page: i64) -> AppResult<Vec<FigureLabel>> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut stmt = conn.prepare(
            "SELECT id, doc_id, page, label_bbox, label_text, ocr_conf, image_path
             FROM figure_labels
             WHERE doc_id = ?1 AND page = ?2
             ORDER BY id",
        )?;
        let rows = stmt.query_map(rusqlite::params![doc_id, page], |row| {
            let bbox_str: String = row.get(3)?;
            let bbox: Vec<f64> = serde_json::from_str(&bbox_str).unwrap_or_default();
            Ok(FigureLabel {
                id: row.get(0)?,
                doc_id: row.get(1)?,
                page: row.get(2)?,
                label_bbox: bbox,
                label_text: row.get(4)?,
                ocr_conf: row.get(5)?,
                image_path: row.get(6)?,
            })
        })?;
        let mut results = Vec::new();
        for row in rows {
            results.push(row?);
        }
        Ok(results)
    }

    /// 查询指定 (doc_id, page) 的所有 coref 预测
    pub fn get_coref_predictions(
        &self,
        doc_id: &str,
        page: i64,
    ) -> AppResult<Vec<CorefPrediction>> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut stmt = conn.prepare(
            "SELECT id, doc_id, page, mol_smiles, mol_bbox, mol_conf, label_id,
                    label_text, label_bbox, confidence, source, is_confirmed, image_path
             FROM coref_predictions
             WHERE doc_id = ?1 AND page = ?2
             ORDER BY confidence DESC, id",
        )?;
        let rows = stmt.query_map(rusqlite::params![doc_id, page], |row| {
            let mol_bbox_str: Option<String> = row.get(4)?;
            let mol_bbox: Option<Vec<f64>> =
                mol_bbox_str.and_then(|s| serde_json::from_str(&s).ok());
            let label_bbox_str: Option<String> = row.get(8)?;
            let label_bbox: Option<Vec<f64>> =
                label_bbox_str.and_then(|s| serde_json::from_str(&s).ok());
            let is_confirmed_i: i64 = row.get(11)?;
            Ok(CorefPrediction {
                id: row.get(0)?,
                doc_id: row.get(1)?,
                page: row.get(2)?,
                mol_smiles: row.get(3)?,
                mol_bbox,
                mol_conf: row.get(5)?,
                label_id: row.get(6)?,
                label_text: row.get(7)?,
                label_bbox,
                confidence: row.get(9)?,
                source: row.get(10)?,
                is_confirmed: is_confirmed_i != 0,
                image_path: row.get(12)?,
            })
        })?;
        let mut results = Vec::new();
        for row in rows {
            results.push(row?);
        }
        Ok(results)
    }

    /// 按 label_text 找所有关联的 coref 预测（跨文档隔离：必须传 doc_id）
    pub fn get_predictions_by_label(
        &self,
        doc_id: &str,
        label_text: &str,
    ) -> AppResult<Vec<CorefPrediction>> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let mut stmt = conn.prepare(
            "SELECT id, doc_id, page, mol_smiles, mol_bbox, mol_conf, label_id,
                    label_text, label_bbox, confidence, source, is_confirmed, image_path
             FROM coref_predictions
             WHERE doc_id = ?1 AND label_text = ?2
             ORDER BY confidence DESC, id",
        )?;
        let rows = stmt.query_map(rusqlite::params![doc_id, label_text], |row| {
            let mol_bbox_str: Option<String> = row.get(4)?;
            let mol_bbox: Option<Vec<f64>> =
                mol_bbox_str.and_then(|s| serde_json::from_str(&s).ok());
            let label_bbox_str: Option<String> = row.get(8)?;
            let label_bbox: Option<Vec<f64>> =
                label_bbox_str.and_then(|s| serde_json::from_str(&s).ok());
            let is_confirmed_i: i64 = row.get(11)?;
            Ok(CorefPrediction {
                id: row.get(0)?,
                doc_id: row.get(1)?,
                page: row.get(2)?,
                mol_smiles: row.get(3)?,
                mol_bbox,
                mol_conf: row.get(5)?,
                label_id: row.get(6)?,
                label_text: row.get(7)?,
                label_bbox,
                confidence: row.get(9)?,
                source: row.get(10)?,
                is_confirmed: is_confirmed_i != 0,
                image_path: row.get(12)?,
            })
        })?;
        let mut results = Vec::new();
        for row in rows {
            results.push(row?);
        }
        Ok(results)
    }

    /// 标记某预测为人工确认（is_confirmed=1, source='manual'）
    pub fn confirm_coref_prediction(
        &self,
        prediction_id: i64,
        is_confirmed: bool,
    ) -> AppResult<()> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let new_source = if is_confirmed { "manual" } else { "geometric" };
        let v = if is_confirmed { 1 } else { 0 };
        conn.execute(
            "UPDATE coref_predictions
             SET is_confirmed = ?1, source = ?2, updated_at = CURRENT_TIMESTAMP
             WHERE id = ?3",
            rusqlite::params![v, new_source, prediction_id],
        )?;
        Ok(())
    }

    /// 删除指定 (doc_id, page) 的所有 predictions（重跑用）
    pub fn delete_coref_predictions(&self, doc_id: &str, page: i64) -> AppResult<usize> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let n = conn.execute(
            "DELETE FROM coref_predictions WHERE doc_id = ?1 AND page = ?2",
            rusqlite::params![doc_id, page],
        )?;
        Ok(n)
    }

    /// 删除指定 (doc_id, page, mol_smiles, label_text) 的单个配对
    pub fn delete_predictions_by_pair(
        &self,
        doc_id: &str,
        page: i64,
        mol_smiles: &str,
        label_text: &str,
    ) -> AppResult<usize> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        let n = conn.execute(
            "DELETE FROM coref_predictions
             WHERE doc_id = ?1 AND page = ?2
               AND mol_smiles = ?3 AND label_text = ?4",
            rusqlite::params![doc_id, page, mol_smiles, label_text],
        )?;
        Ok(n)
    }

    /// 删除指定 doc 的所有 figure_labels + coref_predictions（文档级清除）
    pub fn delete_figure_annotations(&self, doc_id: &str) -> AppResult<()> {
        let conn = self.fts_conn.lock().map_err(|e| e.to_string())?;
        conn.execute(
            "DELETE FROM figure_labels WHERE doc_id = ?1",
            rusqlite::params![doc_id],
        )?;
        conn.execute(
            "DELETE FROM coref_predictions WHERE doc_id = ?1",
            rusqlite::params![doc_id],
        )?;
        Ok(())
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
    let cache = KB_CACHE.get_or_init(DashMap::new);
    if let Some(entry) = cache.get(root) {
        return Ok(entry);
    }

    let config = mbforge_infra::config::settings::AppConfig::load();
    let project_path = std::path::Path::new(root);

    // Phase 2: 优先使用 DbManager 共享连接
    let kb = if let Ok(db) = mbforge_infra::db::get_or_init_db(project_path) {
        KnowledgeBase::with_shared_conn(project_path, Some(&config.embed), db.knowledge_base())?
    } else {
        log::warn!(
            "DbManager unavailable for KB at {}, falling back to self-managed connection",
            root
        );
        KnowledgeBase::new(project_path, Some(&config.embed))?
    };

    cache.insert(root.to_string(), kb);
    Ok(cache.get(root).expect("just inserted"))
}

fn get_or_init_semantic_cache(
    root: &str,
) -> dashmap::mapref::one::Ref<'static, String, SemanticCache> {
    let cache = SEMANTIC_CACHE.get_or_init(DashMap::new);
    if let Some(entry) = cache.get(root) {
        return entry;
    }

    // Phase 2: 优先使用 DbManager 共享连接，消除每操作自开连接
    let project_path = std::path::Path::new(root);
    let sc = if let Ok(db) = mbforge_infra::db::get_or_init_db(project_path) {
        SemanticCache::with_db_manager(
            SemanticCacheConfig::default(),
            db.knowledge_base(),
            project_path,
        )
    } else {
        log::warn!("DbManager unavailable for semantic cache at {}, falling back to self-managed connection", root);
        SemanticCache::new(project_path, SemanticCacheConfig::default())
    };

    cache.insert(root.to_string(), sc);
    cache.get(root).expect("just inserted")
}

/// 搜索核心逻辑
pub async fn search_with_cache(
    root: &str,
    query: &str,
    top_k: usize,
) -> AppResult<(Vec<serde_json::Value>, Vec<StreamingResult>)> {
    // 1. L1 缓存命中？
    {
        let sc = get_or_init_semantic_cache(root);
        if let Some(cached) = sc.value().get_l1(query).await {
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
        sc.value().store(query, json_results.clone()).await;
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
pub async fn kb_search(
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<Vec<serde_json::Value>, String> {
    let top_k = top_k.unwrap_or(5);
    let (results, _) = search_with_cache(&root, &query, top_k)
        .await
        .map_err(|e| e.to_string())?;
    Ok(results)
}

#[tauri::command]
pub async fn kb_search_stream(
    app: tauri::AppHandle<tauri::Wry>,
    root: String,
    query: String,
    top_k: Option<usize>,
) -> Result<(), String> {
    let top_k = top_k.unwrap_or(5);
    let (_results, chunks) = search_with_cache(&root, &query, top_k)
        .await
        .map_err(|e| e.to_string())?;

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
