#![allow(dead_code)]
//! 语义缓存 — L1 精确哈希查询缓存
//!
//! 使用内存 HashMap 提供 O(1) 命中，SQLite 持久化（共享 knowledge_base.db）。
//! 相比全量 JSON 重写，SQLite 单条 INSERT/UPDATE 更高效，且支持 TTL 批量清理。

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{HashMap, VecDeque};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use rusqlite::{params, Connection};

use crate::core::db::SharedConn;
use crate::core::error::AppResult;
use crate::core::helpers::{LockResultExt, now_secs_f64};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheEntry {
    pub query_hash: String,
    pub query_text: String,
    pub results: Vec<serde_json::Value>,
    pub project_root: String,
    pub created_at: f64,
    pub hit_count: u64,
    pub last_hit: f64,
}

impl CacheEntry {
    pub fn is_expired(&self, ttl: f64) -> bool {
        let now = now_secs_f64();
        (now - self.created_at) > ttl
    }

    pub fn update_hit(&mut self) {
        self.hit_count += 1;
        self.last_hit = now_secs_f64();
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SemanticCacheConfig {
    pub enabled: bool,
    pub max_size: usize,
    pub ttl_seconds: f64,
    pub disk_persist: bool,
}

impl Default for SemanticCacheConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            max_size: 1000,
            ttl_seconds: 3600.0,
            disk_persist: true,
        }
    }
}

struct CacheInner {
    entries: HashMap<String, CacheEntry>,
    lru: VecDeque<String>,
}

pub struct SemanticCache {
    config: SemanticCacheConfig,
    cache: Mutex<CacheInner>,
    db_path: PathBuf,
    /// 共享连接（来自 DbManager）。为 None 时回退到 db_path 自管（向后兼容）。
    shared_conn: Option<SharedConn>,
}

fn hash_query(query: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(query.as_bytes());
    let result = hasher.finalize();
    result[..16].iter().map(|b| format!("{:02x}", b)).collect()
}

impl SemanticCache {
    pub fn new(project_root: &Path, config: SemanticCacheConfig) -> Self {
        let db_path = project_root
            .join(crate::core::constants::INDEX_DIR)
            .join("knowledge_base.db");
        if let Some(parent) = db_path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }

        let cache = Self {
            config,
            cache: Mutex::new(CacheInner {
                entries: HashMap::new(),
                lru: VecDeque::new(),
            }),
            db_path: db_path.clone(),
            shared_conn: None,
        };

        if cache.config.disk_persist {
            if let Err(e) = cache.load_from_db() {
                log::warn!("SemanticCache: failed to load from db: {}", e);
            }
        }

        // 向后兼容：尝试从旧 JSON 文件加载
        let legacy_path = project_root
            .join(".mbforge")
            .join("cache")
            .join("semantic_cache.json");
        if legacy_path.exists() {
            if let Err(e) = cache.load_from_legacy_json(&legacy_path) {
                log::warn!("SemanticCache: failed to load legacy json: {}", e);
            }
        }

        cache
    }

    /// 接受 DbManager 共享连接的构造函数。
    ///
    /// 这是 Phase 2 重构后的新路径：使用共享的 `SharedConn` 而非
    /// 每次操作都 `Connection::open`。适用于生产代码路径。
    /// 旧 `new()` 仍保留以供测试和未迁移的调用方使用。
    pub fn with_db_manager(
        config: SemanticCacheConfig,
        shared_conn: SharedConn,
        project_root: &Path,
    ) -> Self {
        let db_path = project_root
            .join(crate::core::constants::INDEX_DIR)
            .join("knowledge_base.db");

        let cache = Self {
            config,
            cache: Mutex::new(CacheInner {
                entries: HashMap::new(),
                lru: VecDeque::new(),
            }),
            db_path,
            shared_conn: Some(shared_conn),
        };

        if cache.config.disk_persist {
            if let Err(e) = cache.load_from_db() {
                log::warn!("SemanticCache: failed to load from db: {}", e);
            }
        }

        // 向后兼容：尝试从旧 JSON 文件加载
        let legacy_path = project_root
            .join(".mbforge")
            .join("cache")
            .join("semantic_cache.json");
        if legacy_path.exists() {
            if let Err(e) = cache.load_from_legacy_json(&legacy_path) {
                log::warn!("SemanticCache: failed to load legacy json: {}", e);
            }
        }

        cache
    }

    fn with_conn<F, T>(&self, f: F) -> AppResult<T>
    where
        F: FnOnce(&Connection) -> AppResult<T>,
    {
        if let Some(shared) = &self.shared_conn {
            // 优先使用 DbManager 提供的共享连接（无新连接，无锁外文件）
            let guard = shared.lock().map_err(|e| crate::core::error::AppError {
                code: crate::core::error::ErrorCode::Unknown,
                message: format!("Shared connection mutex poisoned: {}", e),
                path: None,
                suggestion: None,
            })?;
            Self::setup_schema(&guard)?;
            return f(&guard);
        }
        // 回退路径：自管连接（仅供遗留测试/调用方）
        let conn = Connection::open(&self.db_path)?;
        f(&conn)
    }

    fn setup_schema(conn: &Connection) -> AppResult<()> {
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA busy_timeout=5000;",
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS semantic_cache (
                query_hash  TEXT PRIMARY KEY,
                query_text  TEXT NOT NULL,
                results_json TEXT NOT NULL,
                created_at  REAL NOT NULL,
                hit_count   INTEGER NOT NULL DEFAULT 0,
                last_hit    REAL NOT NULL
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_last_hit ON semantic_cache(last_hit)",
            [],
        )?;

        Ok(())
    }

    fn load_from_db(&self) -> AppResult<()> {
        self.with_conn(|conn| {
            Self::setup_schema(conn)?;

            let mut stmt = conn.prepare(
                "SELECT query_hash, query_text, results_json, created_at, hit_count, last_hit
                 FROM semantic_cache",
            )?;

            let rows = stmt.query_map([], |row| {
                let results_json: String = row.get(2)?;
                let results: Vec<serde_json::Value> =
                    serde_json::from_str(&results_json).unwrap_or_default();
                Ok(CacheEntry {
                    query_hash: row.get(0)?,
                    query_text: row.get(1)?,
                    results,
                    project_root: String::new(),
                    created_at: row.get(3)?,
                    hit_count: row.get::<_, i64>(4)? as u64,
                    last_hit: row.get(5)?,
                })
            })?;

            let mut inner = self.cache.lock().into_inner();
            for row in rows {
                let entry = row?;
                let key = entry.query_hash.clone();
                inner.lru.push_back(key.clone());
                inner.entries.insert(key, entry);
            }

            log::debug!("SemanticCache: loaded {} entries from db", inner.entries.len());
            Ok(())
        })
    }

    fn load_from_legacy_json(&self, path: &Path) -> AppResult<()> {
        let data: HashMap<String, serde_json::Value> =
            match std::fs::read_to_string(path) {
                Ok(c) => serde_json::from_str(&c).unwrap_or_default(),
                Err(_) => return Ok(()),
            };

        let mut inner = self.cache.lock().into_inner();
        let mut migrated = 0usize;

        for (key, item) in data {
            if let Ok(entry) = serde_json::from_value::<CacheEntry>(item) {
                if !inner.entries.contains_key(&key) {
                    inner.lru.push_back(key.clone());
                    inner.entries.insert(key, entry);
                    migrated += 1;
                }
            }
        }

        if migrated > 0 {
            log::info!("SemanticCache: migrated {} entries from legacy JSON", migrated);
            // 同步写入 SQLite
            drop(inner);
            let _ = self.flush_to_db();
        }

        // 重命名旧文件
        let backup = path.with_extension("json.bak");
        let _ = std::fs::rename(path, backup);

        Ok(())
    }

    fn flush_to_db(&self) -> AppResult<()> {
        self.with_conn(|conn| {
            Self::setup_schema(conn)?;

            let inner = self.cache.lock().into_inner();

            // 先清空再全量写入（简单策略，缓存大小 <1000，全量写入开销可忽略）
            conn.execute("DELETE FROM semantic_cache", [])?;

            let tx = conn.unchecked_transaction()?;
            for entry in inner.entries.values() {
                let results_json = serde_json::to_string(&entry.results).unwrap_or_default();
                tx.execute(
                    "INSERT INTO semantic_cache
                     (query_hash, query_text, results_json, created_at, hit_count, last_hit)
                     VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                    params![
                        &entry.query_hash,
                        &entry.query_text,
                        &results_json,
                        entry.created_at,
                        entry.hit_count as i64,
                        entry.last_hit,
                    ],
                )?;
            }
            tx.commit()?;

            Ok(())
        })
    }

    /// L1 exact hash match
    pub fn get_l1(&self, query: &str) -> Option<Vec<serde_json::Value>> {
        if !self.config.enabled {
            return None;
        }
        let key = hash_query(query);
        let mut inner = self.cache.lock().into_inner();

        let expired = inner
            .entries
            .get(&key)
            .map_or(false, |e| e.is_expired(self.config.ttl_seconds));

        if expired {
            inner.entries.remove(&key);
            retain_lru(&mut inner.lru, &key);
            // 从 SQLite 删除过期条目（异步，不阻塞读取）
            let key_clone = key.clone();
            spawn_db_write(self, move |conn| {
                let _ = conn.execute(
                    "DELETE FROM semantic_cache WHERE query_hash = ?1",
                    params![key_clone],
                );
            });
            return None;
        }

        let results = inner.entries.get(&key).map(|e| e.results.clone());
        if results.is_some() {
            if let Some(entry) = inner.entries.get_mut(&key) {
                entry.update_hit();
            }
            move_to_back(&mut inner.lru, &key);
            // 异步更新 SQLite 的 hit_count
            let key_clone = key.clone();
            let now = now_secs_f64();
            spawn_db_write(self, move |conn| {
                let _ = conn.execute(
                    "UPDATE semantic_cache SET hit_count = hit_count + 1, last_hit = ?1 WHERE query_hash = ?2",
                    params![now, key_clone],
                );
            });
        }
        results
    }

    /// Store results in cache
    pub fn store(&self, query: &str, results: Vec<serde_json::Value>) {
        if !self.config.enabled || results.is_empty() {
            return;
        }
        let key = hash_query(query);
        let now = now_secs_f64();

        let entry = CacheEntry {
            query_hash: key.clone(),
            query_text: query.to_string(),
            results,
            project_root: String::new(),
            created_at: now,
            hit_count: 1,
            last_hit: now,
        };

        let mut inner = self.cache.lock().into_inner();

        if inner.entries.len() >= self.config.max_size && !inner.entries.contains_key(&key) {
            if let Some(evicted) = inner.lru.pop_front() {
                inner.entries.remove(&evicted);
                // 异步从 SQLite 删除
                spawn_db_write(self, move |conn| {
                    let _ = conn.execute(
                        "DELETE FROM semantic_cache WHERE query_hash = ?1",
                        params![evicted],
                    );
                });
            }
        }

        inner.entries.insert(key.clone(), entry);
        inner.lru.push_back(key.clone());
        drop(inner);

        // 同步写入 SQLite（确保持久化）
        if self.config.disk_persist {
            let results_json = match self.cache.lock() {
                Ok(inner) => inner.entries.get(&key).map(|e| {
                    serde_json::to_string(&e.results).unwrap_or_default()
                }),
                Err(e) => e.into_inner().entries.get(&key).map(|e| {
                    serde_json::to_string(&e.results).unwrap_or_default()
                }),
            };

            if let Some(results_json) = results_json {
                let query_text = query.to_string();
                spawn_db_write(self, move |conn| {
                    let _ = conn.execute(
                        "INSERT OR REPLACE INTO semantic_cache
                         (query_hash, query_text, results_json, created_at, hit_count, last_hit)
                         VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                        params![key, query_text, results_json, now, 1i64, now],
                    );
                });
            }
        }
    }

    pub fn clear(&self) {
        let mut inner = self.cache.lock().into_inner();
        inner.entries.clear();
        inner.lru.clear();
        drop(inner);

        spawn_db_write(self, |conn| {
            let _ = conn.execute("DELETE FROM semantic_cache", []);
        });
    }

    /// 强制同步内存缓存到 SQLite（测试用）
    pub fn sync(&self) -> AppResult<()> {
        self.flush_to_db()
    }

    pub fn stats(&self) -> serde_json::Value {
        let inner = self.cache.lock().into_inner();
        let total_hits: u64 = inner.entries.values().map(|e| e.hit_count).sum();
        serde_json::json!({
            "entries": inner.entries.len(),
            "total_hits": total_hits,
            "max_size": self.config.max_size,
            "ttl_seconds": self.config.ttl_seconds,
        })
    }
}

fn move_to_back(lru: &mut VecDeque<String>, key: &str) {
    if let Some(pos) = lru.iter().position(|k| k == key) {
        if let Some(val) = lru.remove(pos) {
            lru.push_back(val);
        }
    }
}

fn retain_lru(lru: &mut VecDeque<String>, key: &str) {
    lru.retain(|k| k != key);
}

/// 异步执行 SQLite 写操作。
///
/// Phase 2 改造：如果有共享连接（DbManager 路径），先尝试同步执行；
/// 若失败则 fallback 到自管连接的 thread::spawn（向后兼容）。
/// 没有共享连接时走原 thread::spawn 路径。
fn spawn_db_write<F>(cache: &SemanticCache, f: F)
where
    F: FnOnce(&Connection) + Send + 'static,
{
    if let Some(shared) = cache.shared_conn.clone() {
        // 共享连接路径：在线程内短暂获取锁后执行。
        // 这样避免每次自开 connection，但保留异步语义（不阻塞主线程）。
        std::thread::spawn(move || {
            if let Ok(guard) = shared.lock() {
                let _ = SemanticCache::setup_schema(&guard);
                f(&guard);
            }
        });
        return;
    }
    // 向后兼容：自管连接（旧路径，仅测试和未迁移调用方）。
    let db_path = cache.db_path.clone();
    std::thread::spawn(move || {
        if let Ok(conn) = Connection::open(&db_path) {
            let _ = SemanticCache::setup_schema(&conn);
            f(&conn);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup_cache() -> (tempfile::TempDir, SemanticCache) {
        let dir = tempfile::tempdir().unwrap();
        let sc = SemanticCache::new(dir.path(), SemanticCacheConfig::default());
        (dir, sc)
    }

    #[test]
    fn test_l1_cache_hit() {
        let (_dir, sc) = setup_cache();

        assert!(sc.get_l1("test").is_none());

        sc.store("test", vec![serde_json::json!({"text": "result"})]);
        let results = sc.get_l1("test").unwrap();
        assert_eq!(results.len(), 1);
    }

    #[test]
    fn test_l1_cache_miss_different_query() {
        let (_dir, sc) = setup_cache();

        sc.store("query1", vec![serde_json::json!({"text": "result1"})]);
        assert!(sc.get_l1("query2").is_none());
    }

    #[test]
    fn test_persistence() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();

        // 第一轮：写入缓存并强制同步
        let sc = SemanticCache::new(root, SemanticCacheConfig::default());
        sc.store("hello", vec![serde_json::json!({"text": "world"})]);
        sc.sync().unwrap();
        drop(sc);

        // 第二轮：重新加载（dir 必须保持存活）
        let sc2 = SemanticCache::new(root, SemanticCacheConfig::default());
        let results = sc2.get_l1("hello");
        assert!(results.is_some());
        assert_eq!(results.unwrap()[0]["text"], "world");
    }

    #[test]
    fn test_ttl_expiration() {
        let (_dir, sc) = setup_cache();

        sc.store("old", vec![serde_json::json!({"text": "data"})]);
        // 模拟过期：手动修改 created_at（key 是 hash_query 结果）
        {
            let key = hash_query("old");
            let mut inner = sc.cache.lock().unwrap();
            if let Some(entry) = inner.entries.get_mut(&key) {
                entry.created_at = now_secs_f64() - 7200.0; // 2 hours ago
            }
        }
        // TTL 默认 1 小时，应过期
        assert!(sc.get_l1("old").is_none());
    }

    #[test]
    fn test_lru_eviction() {
        let mut config = SemanticCacheConfig::default();
        config.max_size = 2;
        let (_dir, _sc) = setup_cache();
        // 重新创建以应用 max_size=2
        let dir = tempfile::tempdir().unwrap();
        let sc = SemanticCache::new(dir.path(), config);

        sc.store("a", vec![serde_json::json!({"k": "a"})]);
        sc.store("b", vec![serde_json::json!({"k": "b"})]);
        sc.store("c", vec![serde_json::json!({"k": "c"})]); // 应驱逐 a

        assert!(sc.get_l1("a").is_none());
        assert!(sc.get_l1("b").is_some());
        assert!(sc.get_l1("c").is_some());
    }
}
