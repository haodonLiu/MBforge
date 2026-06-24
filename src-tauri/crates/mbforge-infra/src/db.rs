#![allow(dead_code)]
//! 统一数据库连接管理器（Phase 2 重构）
//!
//! 解决问题：先前多个模块各自 `Connection::open()`，导致：
//! - `knowledge_base.rs` 同一文件开 3 个连接
//! - `molecule_store.rs` + `molecule_db.rs` 同一文件开 2 个连接
//! - `semantic_cache.rs` 每次操作都 open，且 `thread::spawn` 各自开
//! - `ingest_queue.rs` 独立 open
//!
//! 设计：
//! - 每个项目根对应一个 `DbManager`，缓存为 `Arc<Mutex<Connection>>`
//! - WAL 模式下，SQLite 允许多个连接并发读 + 单一写
//! - 模块需要连接时从 `DbManager` 借用 `Arc<Mutex<Connection>>`
//!
//! 当前阶段：基础设施已就绪。迁移工作分批进行（先语义缓存，后 KB，后分子）。
//! 未迁移的模块继续使用各自的 `Connection::open()`，新旧路径并存。

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};

use rusqlite::Connection;

use crate::config::constants::INDEX_DIR;
use crate::error::{AppError, AppResult, ErrorCode};

/// 共享的 SQLite 连接，WAL 模式配置。
///
/// WAL 模式下：
/// - 多个 reader 可并发
/// - 同一时刻只有一个 writer
/// - 跨连接的读不阻塞写
pub type SharedConn = Arc<Mutex<Connection>>;

/// 统一管理项目内的两个核心数据库：
/// - `molecules.db`：分子存储 + 关系
/// - `knowledge_base.db`：向量 + FTS5 + 文件缓存
pub struct DbManager {
    project_root: PathBuf,
    molecules: SharedConn,
    knowledge_base: SharedConn,
}

impl DbManager {
    /// 打开（或创建）项目根下的两个数据库，启用 WAL 模式。
    pub fn new(project_root: &Path) -> AppResult<Self> {
        let index_dir = project_root.join(INDEX_DIR);
        std::fs::create_dir_all(&index_dir)?;

        let mol_path = index_dir.join("molecules.db");
        let kb_path = index_dir.join("knowledge_base.db");

        let molecules = open_wal_connection(&mol_path)?;
        let knowledge_base = open_wal_connection(&kb_path)?;

        log::info!(
            "DbManager initialized for project_root={}",
            project_root.display()
        );

        Ok(Self {
            project_root: project_root.to_path_buf(),
            molecules,
            knowledge_base,
        })
    }

    /// 借用 molecules.db 连接（短期锁，调用方应尽快完成操作）。
    pub fn molecules(&self) -> SharedConn {
        Arc::clone(&self.molecules)
    }

    /// 借用 knowledge_base.db 连接。
    pub fn knowledge_base(&self) -> SharedConn {
        Arc::clone(&self.knowledge_base)
    }

    pub fn project_root(&self) -> &Path {
        &self.project_root
    }
}

/// 打开连接并配置 WAL 模式 + busy_timeout。
///
/// `busy_timeout` 让 SQLite 在遇到锁竞争时自动重试 5 秒，避免
/// 多个连接互相等待时立即返回 `SQLITE_BUSY`。
fn open_wal_connection(path: &Path) -> AppResult<SharedConn> {
    let conn = Connection::open(path).map_err(|e| AppError {
        code: ErrorCode::Unknown,
        message: format!("Failed to open {}: {}", path.display(), e),
        path: Some(path.display().to_string()),
        suggestion: None,
    })?;
    conn.execute_batch(
        "PRAGMA journal_mode=WAL;
         PRAGMA busy_timeout=5000;
         PRAGMA wal_autocheckpoint=1000;",
    )
    .map_err(|e| AppError {
        code: ErrorCode::Unknown,
        message: format!("PRAGMA setup failed: {}", e),
        path: Some(path.display().to_string()),
        suggestion: None,
    })?;
    Ok(Arc::new(Mutex::new(conn)))
}

/// 项目级 DbManager 缓存。每个 project_root 对应一个 DbManager。
///
/// 用 `Mutex<HashMap>`（而非 `DashMap`）因为：
/// - 写不频繁（只在新建项目时插入）
/// - 简单即可，避免引入额外依赖
static DB_CACHE: OnceLock<Mutex<std::collections::HashMap<PathBuf, Arc<DbManager>>>> =
    OnceLock::new();

/// 获取或创建项目的 DbManager（缓存的）。
pub fn get_or_init_db(project_root: &Path) -> AppResult<Arc<DbManager>> {
    let cache = DB_CACHE.get_or_init(|| Mutex::new(std::collections::HashMap::new()));
    let mut map = cache.lock().expect("DbManager cache mutex poisoned");
    if let Some(existing) = map.get(project_root) {
        return Ok(Arc::clone(existing));
    }
    let db = Arc::new(DbManager::new(project_root)?);
    map.insert(project_root.to_path_buf(), Arc::clone(&db));
    Ok(db)
}

/// 测试辅助：清空 DbManager 缓存。仅供测试使用。
#[cfg(test)]
pub fn clear_db_cache_for_test() {
    if let Some(cache) = DB_CACHE.get() {
        cache
            .lock()
            .expect("DbManager cache mutex poisoned")
            .clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn db_manager_creates_two_files() {
        let dir = TempDir::new().expect("tempdir");
        let db = DbManager::new(dir.path()).expect("new");
        // Both connections should be open and ready.
        let _ = db.molecules();
        let _ = db.knowledge_base();
    }

    #[test]
    fn get_or_init_caches_per_root() {
        clear_db_cache_for_test();
        let dir = TempDir::new().expect("tempdir");
        let a = get_or_init_db(dir.path()).expect("init");
        let b = get_or_init_db(dir.path()).expect("cached");
        assert!(
            Arc::ptr_eq(&a, &b),
            "same root should return same DbManager"
        );
    }

    #[test]
    fn different_roots_get_different_managers() {
        clear_db_cache_for_test();
        let dir_a = TempDir::new().expect("tempdir a");
        let dir_b = TempDir::new().expect("tempdir b");
        let a = get_or_init_db(dir_a.path()).expect("init a");
        let b = get_or_init_db(dir_b.path()).expect("init b");
        assert!(!Arc::ptr_eq(&a, &b));
    }
}
