#![allow(dead_code)]
//! 内容去重缓存 — 避免重复 LLM 调用
//!
//! 基于 SHA-256(input_text + prompt_hash) → LLM 结果 的映射。
//! 与 file_cache 不同：file_cache 缓存的是 PDF 解析结果（Stage 0），
//! content_cache 缓存的是 LLM 处理结果（Stage 1-3），是最贵的操作。

use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::core::helpers::now_secs_f64;

/// 缓存条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentCacheEntry {
    pub content_hash: String,    // SHA-256(input_text + prompt_hash)
    pub stage: String,           // "meta_analysis" | "post_process" | "merge_sar"
    pub input_text: String,      // 原始输入（截断用于调试）
    pub result_json: String,     // LLM 输出 JSON
    pub created_at: f64,
    pub hit_count: i64,
    pub tokens_used: usize,      // 记录 token 消耗
}

/// 内容去重缓存
pub struct ContentCache {
    conn: Mutex<Connection>,
    max_entries: usize,
}

impl ContentCache {
    pub fn new(conn: Connection) -> Result<Self, String> {
        conn.execute(
            "CREATE TABLE IF NOT EXISTS content_cache (
                content_hash  TEXT PRIMARY KEY,
                stage         TEXT NOT NULL,
                input_text    TEXT NOT NULL,
                result_json   TEXT NOT NULL,
                created_at    REAL NOT NULL,
                hit_count     INTEGER DEFAULT 0,
                tokens_used   INTEGER DEFAULT 0
            )",
            [],
        )
        .map_err(|e| format!("Failed to create content_cache: {}", e))?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_content_cache_stage ON content_cache(stage)",
            [],
        )
        .map_err(|e| format!("Failed to create stage index: {}", e))?;

        Ok(Self {
            conn: Mutex::new(conn),
            max_entries: 500,
        })
    }

    /// 计算缓存 key：SHA-256(stage + input_text)
    pub fn compute_key(stage: &str, input_text: &str) -> String {
        use sha2::{Digest, Sha256};
        let mut hasher = Sha256::new();
        hasher.update(stage.as_bytes());
        hasher.update(b"\0");
        hasher.update(input_text.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    /// 查询缓存
    pub fn get(&self, stage: &str, input_text: &str) -> Option<String> {
        let key = Self::compute_key(stage, input_text);
        let conn = self.conn.lock().ok()?;

        let result = conn.query_row(
            "SELECT result_json FROM content_cache WHERE content_hash = ?1",
            params![key],
            |row| row.get::<_, String>(0),
        );

        match result {
            Ok(json) => {
                // 更新 hit_count
                conn.execute(
                    "UPDATE content_cache SET hit_count = hit_count + 1 WHERE content_hash = ?1",
                    params![key],
                )
                .ok();
                log::debug!("content_cache: HIT for stage={}", stage);
                Some(json)
            }
            Err(_) => None,
        }
    }

    /// 写入缓存
    pub fn put(
        &self,
        stage: &str,
        input_text: &str,
        result_json: &str,
        tokens_used: usize,
    ) -> Result<(), String> {
        let key = Self::compute_key(stage, input_text);
        let now = now_secs_f64();

        // 截断输入用于调试（保留前 500 字符）
        let truncated_input: String = input_text.chars().take(500).collect();

        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;

        // LRU 驱逐：超过上限时删除最旧的
        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM content_cache", [], |r| r.get(0))
            .unwrap_or(0);

        if count >= self.max_entries as i64 {
            conn.execute(
                "DELETE FROM content_cache WHERE content_hash IN (
                    SELECT content_hash FROM content_cache
                    ORDER BY hit_count ASC, created_at ASC
                    LIMIT ?1
                )",
                params![(count - self.max_entries as i64 + 1) as i64],
            )
            .ok();
        }

        conn.execute(
            "INSERT OR REPLACE INTO content_cache (content_hash, stage, input_text, result_json, created_at, hit_count, tokens_used)
             VALUES (?1, ?2, ?3, ?4, ?5, 0, ?6)",
            params![key, stage, truncated_input, result_json, now, tokens_used as i64],
        )
        .map_err(|e| format!("content_cache insert failed: {}", e))?;

        log::debug!("content_cache: STORE for stage={}", stage);
        Ok(())
    }

    /// 按 stage 清除缓存
    pub fn clear_stage(&self, stage: &str) -> Result<usize, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        let affected = conn
            .execute("DELETE FROM content_cache WHERE stage = ?1", params![stage])
            .map_err(|e| format!("Clear failed: {}", e))?;
        Ok(affected)
    }

    /// 清空所有
    pub fn clear(&self) -> Result<(), String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;
        conn.execute("DELETE FROM content_cache", [])
            .map_err(|e| format!("Clear failed: {}", e))?;
        Ok(())
    }

    /// 统计
    pub fn stats(&self) -> Result<ContentCacheStats, String> {
        let conn = self.conn.lock().map_err(|e| format!("Lock error: {}", e))?;

        let total: i64 = conn
            .query_row("SELECT COUNT(*) FROM content_cache", [], |r| r.get(0))
            .unwrap_or(0);
        let total_hits: i64 = conn
            .query_row(
                "SELECT COALESCE(SUM(hit_count), 0) FROM content_cache",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);
        let total_tokens_saved: i64 = conn
            .query_row(
                "SELECT COALESCE(SUM(hit_count * tokens_used), 0) FROM content_cache",
                [],
                |r| r.get(0),
            )
            .unwrap_or(0);

        // 按 stage 分组统计
        let mut stmt = conn
            .prepare("SELECT stage, COUNT(*) FROM content_cache GROUP BY stage")
            .map_err(|e| format!("Prepare failed: {}", e))?;
        let by_stage: Vec<(String, usize)> = stmt
            .query_map([], |row| Ok((row.get(0)?, row.get::<_, i64>(1)? as usize)))
            .map_err(|e| format!("Query failed: {}", e))?
            .filter_map(|r| r.ok())
            .collect();

        Ok(ContentCacheStats {
            total_entries: total as usize,
            total_hits: total_hits as usize,
            tokens_saved: total_tokens_saved as usize,
            by_stage,
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ContentCacheStats {
    pub total_entries: usize,
    pub total_hits: usize,
    pub tokens_saved: usize,
    pub by_stage: Vec<(String, usize)>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_content_cache_roundtrip() {
        let conn = Connection::open_in_memory().unwrap();
        let cache = ContentCache::new(conn).unwrap();

        // MISS
        assert!(cache.get("meta_analysis", "test input").is_none());

        // STORE
        cache
            .put("meta_analysis", "test input", r#"{"result":"ok"}"#, 100)
            .unwrap();

        // HIT
        let result = cache.get("meta_analysis", "test input").unwrap();
        assert_eq!(result, r#"{"result":"ok"}"#);

        // 不同 stage 不命中
        assert!(cache.get("merge_sar", "test input").is_none());
    }

    #[test]
    fn test_content_cache_stats() {
        let conn = Connection::open_in_memory().unwrap();
        let cache = ContentCache::new(conn).unwrap();

        cache.put("meta_analysis", "a", "{}", 50).unwrap();
        cache.put("post_process", "b", "{}", 100).unwrap();
        cache.put("meta_analysis", "c", "{}", 80).unwrap();

        let stats = cache.stats().unwrap();
        assert_eq!(stats.total_entries, 3);
        assert!(stats.by_stage.iter().any(|(s, c)| s == "meta_analysis" && *c == 2));
    }
}
