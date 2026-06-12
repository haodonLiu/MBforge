#![allow(dead_code)]
//! 提取队列 — 持久化的文档处理队列，支持重试和取消
//!
//! 使用 SQLite 存储（共享 knowledge_base.db），替代旧的 JSON 文件。
//! 相比全量 JSON 重写，SQLite 的优势：
//! - 状态更新只需单条 UPDATE（O(1) vs O(n) 序列化）
//! - 统计查询用 COUNT(*) GROUP BY（无需遍历全表）
//! - 事务保证一致性

use std::path::Path;
use std::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::core::error::AppResult;
use crate::core::helpers::now_secs_f64;

/// 队列任务状态
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum IngestStatus {
    /// 等待处理
    Pending,
    /// 正在处理
    Processing,
    /// 处理成功
    Done,
    /// 处理失败（可重试）
    Failed,
    /// 已取消
    Cancelled,
}

impl IngestStatus {
    fn as_str(&self) -> &'static str {
        match self {
            IngestStatus::Pending => "pending",
            IngestStatus::Processing => "processing",
            IngestStatus::Done => "done",
            IngestStatus::Failed => "failed",
            IngestStatus::Cancelled => "cancelled",
        }
    }

    fn from_str(s: &str) -> Option<Self> {
        match s {
            "pending" => Some(IngestStatus::Pending),
            "processing" => Some(IngestStatus::Processing),
            "done" => Some(IngestStatus::Done),
            "failed" => Some(IngestStatus::Failed),
            "cancelled" => Some(IngestStatus::Cancelled),
            _ => None,
        }
    }
}

/// 单个提取任务
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestTask {
    pub id: String,
    pub file_path: String,
    pub doc_id: String,
    pub status: IngestStatus,
    pub stage: String,
    pub progress_pct: f64,
    pub pages_total: i32,
    pub pages_done: i32,
    pub details: String,
    pub retry_count: u32,
    pub max_retries: u32,
    pub error: Option<String>,
    pub created_at: f64,
    pub updated_at: f64,
}

impl IngestTask {
    pub fn new(file_path: String, doc_id: String) -> Self {
        Self::with_stage(file_path, doc_id, "inspector")
    }

    /// 创建指定阶段的任务。
    pub fn with_stage(file_path: String, doc_id: String, stage: &str) -> Self {
        let now = now_secs_f64();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            file_path,
            doc_id,
            status: IngestStatus::Pending,
            stage: stage.to_string(),
            progress_pct: 0.0,
            pages_total: 0,
            pages_done: 0,
            details: String::new(),
            retry_count: 0,
            max_retries: 3,
            error: None,
            created_at: now,
            updated_at: now,
        }
    }

    /// 是否可以重试
    pub fn can_retry(&self) -> bool {
        self.status == IngestStatus::Failed && self.retry_count < self.max_retries
    }
}

/// 提取队列 — SQLite 后端
pub struct IngestQueue {
    conn: Mutex<Connection>,
}

impl IngestQueue {
    /// 打开或创建队列数据库（共享 knowledge_base.db）
    pub fn new(project_root: &Path) -> AppResult<Self> {
        let db_path = project_root
            .join(crate::core::constants::INDEX_DIR)
            .join("knowledge_base.db");
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let conn = Connection::open(&db_path)?;
        Self::setup_schema(&conn)?;

        // 向后兼容：从旧 JSON 文件迁移
        let legacy_path = project_root.join(".mbforge").join("ingest-queue.json");
        if legacy_path.exists() {
            Self::migrate_from_json(&conn, &legacy_path)?;
            // 重命名旧文件（保留作为备份）
            let backup = project_root.join(".mbforge").join("ingest-queue.json.bak");
            let _ = std::fs::rename(&legacy_path, &backup);
        }

        Ok(Self {
            conn: Mutex::new(conn),
        })
    }

    fn setup_schema(conn: &Connection) -> AppResult<()> {
        conn.execute_batch(
            "PRAGMA journal_mode=WAL;
             PRAGMA busy_timeout=5000;",
        )?;

        conn.execute(
            "CREATE TABLE IF NOT EXISTS ingest_queue (
                id          TEXT PRIMARY KEY,
                file_path   TEXT NOT NULL,
                doc_id      TEXT NOT NULL,
                status      TEXT NOT NULL,
                stage       TEXT NOT NULL DEFAULT 'inspector',
                progress_pct REAL NOT NULL DEFAULT 0,
                pages_total INTEGER NOT NULL DEFAULT 0,
                pages_done  INTEGER NOT NULL DEFAULT 0,
                details     TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                error       TEXT,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            )",
            [],
        )?;

        // 向后兼容：新增列（旧表已存在时跳过）。
        // SQLite 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，需手动检查。
        Self::add_column_if_missing(conn, "ingest_queue", "stage", "TEXT NOT NULL DEFAULT 'inspector'")?;
        Self::add_column_if_missing(conn, "ingest_queue", "progress_pct", "REAL NOT NULL DEFAULT 0")?;
        Self::add_column_if_missing(conn, "ingest_queue", "pages_total", "INTEGER NOT NULL DEFAULT 0")?;
        Self::add_column_if_missing(conn, "ingest_queue", "pages_done", "INTEGER NOT NULL DEFAULT 0")?;
        Self::add_column_if_missing(conn, "ingest_queue", "details", "TEXT NOT NULL DEFAULT ''")?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_queue(status)",
            [],
        )?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ingest_doc_id ON ingest_queue(doc_id)",
            [],
        )?;

        Ok(())
    }

    fn add_column_if_missing(
        conn: &Connection,
        table: &str,
        column: &str,
        def: &str,
    ) -> AppResult<()> {
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM pragma_table_info(?1) WHERE name = ?2",
            params![table, column],
            |row| row.get(0),
        )?;
        if count == 0 {
            let sql = format!("ALTER TABLE {} ADD COLUMN {} {}", table, column, def);
            conn.execute(&sql, [])?;
        }
        Ok(())
    }

    fn migrate_from_json(conn: &Connection, path: &Path) -> AppResult<()> {
        let data = std::fs::read_to_string(path).ok();
        if let Some(data) = data {
            #[derive(Deserialize)]
            struct QueueData {
                tasks: Vec<IngestTask>,
            }
            if let Ok(queue_data) = serde_json::from_str::<QueueData>(&data) {
                let tx = conn.unchecked_transaction()?;
                let task_count = queue_data.tasks.len();
                for task in queue_data.tasks {
                    tx.execute(
                        "INSERT OR IGNORE INTO ingest_queue
                         (id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, created_at, updated_at)
                         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
                        params![
                            task.id,
                            task.file_path,
                            task.doc_id,
                            task.status.as_str(),
                            task.stage,
                            task.progress_pct,
                            task.pages_total,
                            task.pages_done,
                            task.details,
                            task.retry_count as i64,
                            task.max_retries as i64,
                            task.error,
                            task.created_at,
                            task.updated_at,
                        ],
                    )?;
                }
                tx.commit()?;
                log::info!("Migrated {} tasks from ingest-queue.json", task_count);
            }
        }
        Ok(())
    }

    fn row_to_task(row: &rusqlite::Row) -> Result<IngestTask, rusqlite::Error> {
        Ok(IngestTask {
            id: row.get(0)?,
            file_path: row.get(1)?,
            doc_id: row.get(2)?,
            status: IngestStatus::from_str(&row.get::<_, String>(3)?)
                .unwrap_or(IngestStatus::Pending),
            stage: row.get(4)?,
            progress_pct: row.get(5)?,
            pages_total: row.get(6)?,
            pages_done: row.get(7)?,
            details: row.get(8)?,
            retry_count: row.get::<_, i64>(9)? as u32,
            max_retries: row.get::<_, i64>(10)? as u32,
            error: row.get(11)?,
            created_at: row.get(12)?,
            updated_at: row.get(13)?,
        })
    }

    /// 入队一个文件
    pub fn enqueue(&self, file_path: String, doc_id: String) -> AppResult<String> {
        let task = IngestTask::new(file_path, doc_id);
        let id = task.id.clone();
        let now = task.created_at;

        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT INTO ingest_queue
             (id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            params![
                &task.id,
                &task.file_path,
                &task.doc_id,
                task.status.as_str(),
                &task.stage,
                task.progress_pct,
                task.pages_total,
                task.pages_done,
                &task.details,
                task.retry_count as i64,
                task.max_retries as i64,
                task.error.as_ref(),
                now,
                now,
            ],
        )?;

        log::info!("IngestQueue: enqueued {}", id);
        Ok(id)
    }

    /// 入队一个指定阶段的文件
    pub fn enqueue_with_stage(&self, file_path: String, doc_id: String, stage: &str) -> AppResult<String> {
        let task = IngestTask::with_stage(file_path, doc_id, stage);
        let id = task.id.clone();
        let now = task.created_at;

        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        conn.execute(
            "INSERT INTO ingest_queue
             (id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, created_at, updated_at)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14)",
            params![
                &task.id,
                &task.file_path,
                &task.doc_id,
                task.status.as_str(),
                &task.stage,
                task.progress_pct,
                task.pages_total,
                task.pages_done,
                &task.details,
                task.retry_count as i64,
                task.max_retries as i64,
                task.error.as_ref(),
                now,
                now,
            ],
        )?;

        log::info!("IngestQueue: enqueued {} stage={}", id, stage);
        Ok(id)
    }

    /// 取出下一个待处理任务
    pub fn dequeue(&self) -> AppResult<Option<IngestTask>> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;

        // 找第一个 Pending 或可重试的 Failed 任务
        let mut stmt = conn.prepare(
            "SELECT id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, created_at, updated_at
             FROM ingest_queue
             WHERE status = 'pending'
                OR (status = 'failed' AND retry_count < max_retries)
             ORDER BY created_at ASC
             LIMIT 1",
        )?;

        let mut rows = stmt.query([])?;
        let mut task = if let Some(row) = rows.next()? {
            Some(Self::row_to_task(row)?)
        } else {
            None
        };

        drop(rows);
        drop(stmt);

        if let Some(ref mut task) = task {
            let now = now_secs_f64();
            conn.execute(
                "UPDATE ingest_queue
                 SET status = 'processing', updated_at = ?1
                 WHERE id = ?2",
                params![now, &task.id],
            )?;
            task.status = IngestStatus::Processing;
            task.updated_at = now;
        }

        Ok(task)
    }

    /// 标记任务完成
    pub fn mark_done(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue
             SET status = 'done', error = NULL, updated_at = ?1
             WHERE id = ?2",
            params![now, task_id],
        )?;
        Ok(())
    }

    /// 标记任务失败（自动判断是否可重试）
    pub fn mark_failed(&self, task_id: &str, error: String) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();

        // 先读取当前重试次数和上限
        let (retry_count, max_retries): (i64, i64) = conn.query_row(
            "SELECT retry_count, max_retries FROM ingest_queue WHERE id = ?1",
            params![task_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )?;

        let new_retry = retry_count + 1;
        let new_status = if new_retry >= max_retries {
            log::warn!(
                "IngestQueue: task {} permanently failed after {} retries: {}",
                task_id,
                new_retry,
                error
            );
            "failed"
        } else {
            log::info!(
                "IngestQueue: task {} will retry ({}/{}): {}",
                task_id,
                new_retry,
                max_retries,
                error
            );
            "pending"
        };

        conn.execute(
            "UPDATE ingest_queue
             SET status = ?1, retry_count = ?2, error = ?3, updated_at = ?4
             WHERE id = ?5",
            params![new_status, new_retry, &error, now, task_id],
        )?;

        Ok(())
    }

    /// 取消一个任务
    pub fn cancel(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue
             SET status = 'cancelled', updated_at = ?1
             WHERE id = ?2",
            params![now, task_id],
        )?;
        Ok(())
    }

    /// 取消所有待处理任务（项目切换时暂停）
    pub fn cancel_all_pending(&self) -> AppResult<usize> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        let changed = conn.execute(
            "UPDATE ingest_queue
             SET status = 'cancelled', updated_at = ?1
             WHERE status IN ('pending', 'processing')",
            params![now],
        )?;
        Ok(changed)
    }

    /// 清理已完成/取消的任务
    pub fn cleanup(&self) -> AppResult<usize> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let changed = conn.execute(
            "DELETE FROM ingest_queue
             WHERE status IN ('done', 'cancelled')",
            [],
        )?;
        Ok(changed)
    }

    /// 队列统计
    pub fn stats(&self) -> AppResult<QueueStats> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;

        let total: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ingest_queue",
            [],
            |r| r.get(0),
        )?;

        let mut stmt = conn.prepare(
            "SELECT status, COUNT(*) FROM ingest_queue GROUP BY status",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, i64>(1)?))
        })?;

        let mut pending = 0usize;
        let mut processing = 0usize;
        let mut done = 0usize;
        let mut failed = 0usize;
        let mut cancelled = 0usize;

        for row in rows {
            let (status, count) = row?;
            let count = count as usize;
            match status.as_str() {
                "pending" => pending = count,
                "processing" => processing = count,
                "done" => done = count,
                "failed" => failed = count,
                "cancelled" => cancelled = count,
                _ => {}
            }
        }

        Ok(QueueStats {
            total: total as usize,
            pending,
            processing,
            done,
            failed,
            cancelled,
        })
    }

    /// 获取所有任务（用于 UI 展示）
    pub fn list_all(&self) -> AppResult<Vec<IngestTask>> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let mut stmt = conn.prepare(
            "SELECT id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, created_at, updated_at
             FROM ingest_queue
             ORDER BY created_at ASC",
        )?;

        let rows = stmt.query_map([], Self::row_to_task)?;
        let mut tasks = Vec::new();
        for row in rows {
            tasks.push(row?);
        }
        Ok(tasks)
    }

    /// 检查文件是否已在队列中（Pending/Processing/Done 状态）
    pub fn contains_file(&self, file_path: &str) -> AppResult<bool> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ingest_queue
             WHERE file_path = ?1 AND status IN ('pending', 'processing', 'done')",
            params![file_path],
            |r| r.get(0),
        )?;
        Ok(count > 0)
    }

    /// 更新任务进度与阶段（worker 使用）
    pub fn update_progress(
        &self,
        task_id: &str,
        stage: &str,
        progress_pct: f64,
        pages_done: i32,
        pages_total: i32,
        details: &str,
    ) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue
             SET stage = ?1, progress_pct = ?2, pages_done = ?3, pages_total = ?4, details = ?5, updated_at = ?6
             WHERE id = ?7",
            params![stage, progress_pct, pages_done, pages_total, details, now, task_id],
        )?;
        Ok(())
    }

    /// 仅更新任务阶段（worker 阶段切换使用）
    pub fn set_stage(&self, task_id: &str, stage: &str) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue
             SET stage = ?1, updated_at = ?2
             WHERE id = ?3",
            params![stage, now, task_id],
        )?;
        Ok(())
    }

    /// 把任务状态重置为 pending（worker 阶段切换使用）。
    pub fn set_pending(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue
             SET status = 'pending', updated_at = ?1
             WHERE id = ?2",
            params![now, task_id],
        )?;
        Ok(())
    }

    /// 重试一个失败任务（仅当 retry_count < max_retries 时生效）。
    pub fn retry(&self, task_id: &str) -> AppResult<bool> {
        let conn = self.conn.lock().map_err(|e| e.to_string())?;
        let now = now_secs_f64();
        let changed = conn.execute(
            "UPDATE ingest_queue
             SET status = 'pending', error = NULL, updated_at = ?1
             WHERE id = ?2 AND status = 'failed' AND retry_count < max_retries",
            params![now, task_id],
        )?;
        Ok(changed > 0)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QueueStats {
    pub total: usize,
    pub pending: usize,
    pub processing: usize,
    pub done: usize,
    pub failed: usize,
    pub cancelled: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn setup_queue() -> (tempfile::TempDir, IngestQueue) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();
        let queue = IngestQueue::new(root).unwrap();
        (dir, queue)
    }

    #[test]
    fn test_queue_enqueue_dequeue() {
        let (_dir, queue) = setup_queue();

        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        assert_eq!(queue.stats().unwrap().pending, 1);

        let task = queue.dequeue().unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.status, IngestStatus::Processing);
        assert_eq!(task.stage, "inspector");

        queue.mark_done(&id).unwrap();
        assert_eq!(queue.stats().unwrap().done, 1);
    }

    #[test]
    fn test_queue_with_stage() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue_with_stage("test.pdf".into(), "doc1".into(), "ocr")
            .unwrap();
        let task = queue.dequeue().unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.stage, "ocr");
    }

    #[test]
    fn test_queue_update_progress() {
        let (_dir, queue) = setup_queue();
        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        queue
            .update_progress(&id, "text_extract", 0.5, 3, 6, "extracting")
            .unwrap();
        let task = queue.list_all().unwrap().pop().unwrap();
        assert_eq!(task.stage, "text_extract");
        assert_eq!(task.progress_pct, 0.5);
        assert_eq!(task.pages_done, 3);
        assert_eq!(task.pages_total, 6);
        assert_eq!(task.details, "extracting");
    }

    #[test]
    fn test_queue_retry() {
        let (_dir, queue) = setup_queue();
        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();

        // 第一次失败 → 重试
        queue.mark_failed(&id, "LLM timeout".into()).unwrap();
        assert_eq!(queue.stats().unwrap().pending, 1);

        // 第二次失败 → 重试
        let task = queue.dequeue().unwrap().unwrap();
        queue.mark_failed(&task.id, "LLM timeout".into()).unwrap();
        assert_eq!(queue.stats().unwrap().pending, 1);

        // 第三次失败 → 永久失败
        let task = queue.dequeue().unwrap().unwrap();
        queue.mark_failed(&task.id, "LLM timeout".into()).unwrap();
        assert_eq!(queue.stats().unwrap().failed, 1);
        assert_eq!(queue.stats().unwrap().pending, 0);
    }

    #[test]
    fn test_queue_contains_file() {
        let (_dir, queue) = setup_queue();
        assert!(!queue.contains_file("test.pdf").unwrap());

        queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        assert!(queue.contains_file("test.pdf").unwrap());
    }

    #[test]
    fn test_queue_persistence() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        // 写入
        {
            let queue = IngestQueue::new(root).unwrap();
            queue.enqueue("a.pdf".into(), "d1".into()).unwrap();
            queue.enqueue("b.pdf".into(), "d2".into()).unwrap();
        }

        // 重新加载
        {
            let queue = IngestQueue::new(root).unwrap();
            assert_eq!(queue.stats().unwrap().total, 2);
        }
    }

    #[test]
    fn test_queue_cleanup() {
        let (_dir, queue) = setup_queue();
        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        queue.mark_done(&id).unwrap();

        queue.enqueue("test2.pdf".into(), "doc2".into()).unwrap();

        let removed = queue.cleanup().unwrap();
        assert_eq!(removed, 1);
        assert_eq!(queue.stats().unwrap().total, 1);
    }

    #[test]
    fn test_legacy_migration() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        // 写入旧格式 JSON
        let legacy = serde_json::json!({
            "tasks": [
                {
                    "id": "legacy-1",
                    "file_path": "old.pdf",
                    "doc_id": "doc-old",
                    "status": "pending",
                    "stage": "inspector",
                    "progress_pct": 0.0,
                    "pages_total": 0,
                    "pages_done": 0,
                    "details": "",
                    "retry_count": 0,
                    "max_retries": 3,
                    "error": null,
                    "created_at": 1234567890.0,
                    "updated_at": 1234567890.0
                }
            ]
        });
        std::fs::write(
            root.join(".mbforge").join("ingest-queue.json"),
            serde_json::to_string_pretty(&legacy).unwrap(),
        ).unwrap();

        // 新队列应自动迁移
        let queue = IngestQueue::new(root).unwrap();
        let stats = queue.stats().unwrap();
        assert_eq!(stats.total, 1);
        assert_eq!(stats.pending, 1);

        // 旧文件应被重命名
        assert!(!root.join(".mbforge").join("ingest-queue.json").exists());
        assert!(root.join(".mbforge").join("ingest-queue.json.bak").exists());
    }
}
