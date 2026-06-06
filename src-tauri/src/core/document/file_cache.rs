//! 文件内容缓存 — 避免重复解析 PDF
//!
//! 在 knowledge_base.db 同库中新增 file_cache 表，使用 SHA-256 + mtime 两级检查。
//! 命中缓存时直接返回已提取的文本和 sections，跳过昂贵的 PDF 解析。

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::core::error::AppResult;

/// 缓存条目：完整的文件解析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedDoc {
    pub file_hash: String,
    pub file_path: String,
    pub mtime: f64,
    pub text: String,
    pub sections_json: String,  // Vec<SectionChunk> 的 JSON
    pub metadata_json: String,  // parser, page_count, images 等
    pub created_at: f64,
    pub hit_count: i64,
}

/// 文件内容缓存
pub struct FileCache {
    conn: Mutex<Connection>,
}

impl FileCache {
    /// 在已有 SQLite 连接上创建 file_cache 表（复用 knowledge_base.db）
    pub fn new(conn: Connection) -> AppResult<Self> {
        Self::setup_schema(&conn)?;
        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    /// 初始化表结构（pub 供 KnowledgeBase 迁移时调用）
    pub fn setup_schema(conn: &Connection) -> AppResult<()> {
        conn.execute(
            "CREATE TABLE IF NOT EXISTS file_cache (
                file_hash      TEXT PRIMARY KEY,
                file_path      TEXT NOT NULL,
                mtime          REAL NOT NULL,
                text           TEXT NOT NULL,
                sections_json  TEXT NOT NULL,
                metadata_json  TEXT NOT NULL,
                created_at     REAL NOT NULL,
                hit_count      INTEGER DEFAULT 0
            )",
            [],
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_cache_path ON file_cache(file_path)",
            [],
        )?;

        Ok(())
    }

    /// 查询缓存：先比对 mtime，再比对 hash
    ///
    /// 返回 Some(CachedDoc) 表示命中缓存，None 表示需要重新解析。
    pub fn get(&self, path: &Path) -> AppResult<Option<CachedDoc>> {
        let path_str = path.to_string_lossy().to_string();

        // 读取当前文件 mtime
        let current_mtime = match std::fs::metadata(path) {
            Ok(m) => m
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs_f64())
                .unwrap_or(0.0),
            Err(_) => return Ok(None), // 文件不存在，缓存无效
        };

        let conn = self.conn.lock().map_err(|e| e.to_string())?;

        // 先按 file_path 查找
        let result = conn.query_row(
            "SELECT file_hash, file_path, mtime, text, sections_json, metadata_json, created_at, hit_count
             FROM file_cache WHERE file_path = ?1",
            params![path_str],
            |row| {
                Ok(CachedDoc {
                    file_hash: row.get(0)?,
                    file_path: row.get(1)?,
                    mtime: row.get(2)?,
                    text: row.get(3)?,
                    sections_json: row.get(4)?,
                    metadata_json: row.get(5)?,
                    created_at: row.get(6)?,
                    hit_count: row.get(7)?,
                })
            },
        );

        match result {
            Ok(cached) => {
                // mtime 相同 → 命中（容差 1ms，避免快速测试中误判）
                if (cached.mtime - current_mtime).abs() < 0.001 {
                    // 更新 hit_count
                    conn.execute(
                        "UPDATE file_cache SET hit_count = hit_count + 1 WHERE file_path = ?1",
                        params![path_str],
                    )
                    .ok();
                    let mut cached = cached;
                    cached.hit_count += 1;
                    log::debug!("file_cache: HIT (mtime match) for {}", path_str);
                    return Ok(Some(cached));
                }

                // mtime 不同 → 计算 hash
                let current_hash = crate::core::helpers::sha256_file(path)?;

                if cached.file_hash == current_hash {
                    // hash 相同，更新 mtime
                    conn.execute(
                        "UPDATE file_cache SET mtime = ?1, hit_count = hit_count + 1 WHERE file_path = ?2",
                        params![current_mtime, path_str],
                    )
                    .ok();
                    let mut cached = cached;
                    cached.hit_count += 1;
                    cached.mtime = current_mtime;
                    log::debug!("file_cache: HIT (hash match) for {}", path_str);
                    return Ok(Some(cached));
                }

                // hash 不同 → 缓存失效，删除旧条目
                conn.execute(
                    "DELETE FROM file_cache WHERE file_path = ?1",
                    params![path_str],
                )
                .ok();
                log::debug!("file_cache: MISS (hash changed) for {}", path_str);
                Ok(None)
            }
            Err(rusqlite::Error::QueryReturnedNoRows) => {
                log::debug!("file_cache: MISS (not found) for {}", path_str);
                Ok(None)
            }
            Err(e) => Err(e.into()),
        }
    }

    /// 写入缓存
    pub fn put(
        &self,
        path: &Path,
        text: &str,
        sections_json: &str,
        metadata_json: &str,
    ) -> AppResult<()> {
        let path_str = path.to_string_lossy().to_string();
        let file_hash = crate::core::helpers::sha256_file(path)?;

        let mtime = std::fs::metadata(path)
            .ok()
            .and_then(|m| m.modified().ok())
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);

        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT OR REPLACE INTO file_cache (file_hash, file_path, mtime, text, sections_json, metadata_json, created_at, hit_count)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, 0)",
            params![file_hash, path_str, mtime, text, sections_json, metadata_json, now],
        )?;

        log::info!("file_cache: STORE for {}", path_str);
        Ok(())
    }

    /// 手动失效某文件的缓存
    pub fn invalidate(&self, path: &Path) -> AppResult<()> {
        let path_str = path.to_string_lossy().to_string();
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        conn.execute(
            "DELETE FROM file_cache WHERE file_path = ?1",
            params![path_str],
        )?;
        Ok(())
    }

    /// 清空所有缓存
    pub fn clear(&self) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        conn.execute("DELETE FROM file_cache", [])?;
        Ok(())
    }

    /// 缓存统计
    pub fn stats(&self) -> AppResult<CacheStats> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM file_cache", [], |r| r.get(0))?;
        let total_hits: i64 = conn
            .query_row("SELECT COALESCE(SUM(hit_count), 0) FROM file_cache", [], |r| {
                r.get(0)
            })?;
        Ok(CacheStats {
            entry_count: count as usize,
            total_hits: total_hits as usize,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheStats {
    pub entry_count: usize,
    pub total_hits: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_file_cache_roundtrip() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("test.pdf");
        std::fs::write(&file_path, b"fake pdf content").unwrap();

        let db_path = dir.path().join("test.db");
        let conn = Connection::open(&db_path).unwrap();
        let cache = FileCache::new(conn).unwrap();

        // 第一次查询：MISS
        assert!(cache.get(&file_path).unwrap().is_none());

        // 写入缓存
        cache
            .put(&file_path, "extracted text", "[]", "{}")
            .unwrap();

        // 第二次查询：HIT
        let cached = cache.get(&file_path).unwrap().unwrap();
        assert_eq!(cached.text, "extracted text");
        assert_eq!(cached.hit_count, 1); // get() 会 +1
    }

    #[test]
    fn test_file_cache_invalidate() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("test.pdf");
        std::fs::write(&file_path, b"content").unwrap();

        let db_path = dir.path().join("test.db");
        let conn = Connection::open(&db_path).unwrap();
        let cache = FileCache::new(conn).unwrap();

        cache.put(&file_path, "text", "[]", "{}").unwrap();
        assert!(cache.get(&file_path).unwrap().is_some());

        cache.invalidate(&file_path).unwrap();
        assert!(cache.get(&file_path).unwrap().is_none());
    }

    #[test]
    fn test_file_cache_mtime_change() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("test.pdf");
        std::fs::write(&file_path, b"v1 content here").unwrap();

        let db_path = dir.path().join("test.db");
        let conn = Connection::open(&db_path).unwrap();
        let cache = FileCache::new(conn).unwrap();

        cache.put(&file_path, "v1 text", "[]", "{}").unwrap();

        // 等待确保 mtime 变化（Windows NTFS 精度问题）
        std::thread::sleep(std::time::Duration::from_millis(50));

        // 修改文件内容（mtime 会变，hash 也会变）
        std::fs::write(&file_path, b"v2 different content").unwrap();

        // 缓存应失效
        assert!(cache.get(&file_path).unwrap().is_none());
    }
}
