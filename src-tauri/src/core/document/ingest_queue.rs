#![allow(dead_code)]
//! 提取队列 — 持久化的文档处理队列，支持重试和取消
//!
//! 使用 SQLite 存储（共享 knowledge_base.db），替代旧的 JSON 文件。
//! 相比全量 JSON 重写，SQLite 的优势：
//! - 状态更新只需单条 UPDATE（O(1) vs O(n) 序列化）
//! - 统计查询用 COUNT(*) GROUP BY（无需遍历全表）
//! - 事务保证一致性

use std::path::Path;
use tokio::sync::Mutex;

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};

use crate::core::error::{AppError, AppResult, ErrorCode};
use crate::core::helpers::now_secs_f64;

/// 队列中 pending + processing 任务的最大数量。
const MAX_ACTIVE_QUEUE_SIZE: usize = 100;

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
    pub file_size_bytes: Option<u64>,
    pub started_at: Option<f64>,
    pub created_at: f64,
    pub updated_at: f64,
    #[serde(default)]
    pub priority: i32,
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
            file_size_bytes: None,
            started_at: None,
            created_at: now,
            updated_at: now,
            priority: 0,
        }
    }

    /// 是否可以重试
    pub fn can_retry(&self) -> bool {
        self.status == IngestStatus::Failed && self.retry_count < self.max_retries
    }
}

/// 单条 ingest 日志（DB 兜底通道，事件通道的镜像）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestLogRecord {
    pub doc_id: String,
    pub stage: String,
    pub level: String,
    pub message: String,
    pub ts_ms: u64,
    /// 关联 task id（nullable，便于跨 task 聚合日志）
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub task_id: Option<String>,
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
                file_hash   TEXT,
                file_size_bytes INTEGER,
                started_at  REAL,
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL,
                priority    INTEGER NOT NULL DEFAULT 0
            )",
            [],
        )?;

        // 向后兼容：新增列（旧表已存在时跳过）。
        // SQLite 不支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS，需手动检查。
        Self::add_column_if_missing(
            conn,
            "ingest_queue",
            "stage",
            "TEXT NOT NULL DEFAULT 'inspector'",
        )?;
        Self::add_column_if_missing(
            conn,
            "ingest_queue",
            "progress_pct",
            "REAL NOT NULL DEFAULT 0",
        )?;
        Self::add_column_if_missing(
            conn,
            "ingest_queue",
            "pages_total",
            "INTEGER NOT NULL DEFAULT 0",
        )?;
        Self::add_column_if_missing(
            conn,
            "ingest_queue",
            "pages_done",
            "INTEGER NOT NULL DEFAULT 0",
        )?;
        Self::add_column_if_missing(conn, "ingest_queue", "details", "TEXT NOT NULL DEFAULT ''")?;
        Self::add_column_if_missing(conn, "ingest_queue", "file_hash", "TEXT")?;
        Self::add_column_if_missing(conn, "ingest_queue", "file_size_bytes", "INTEGER")?;
        Self::add_column_if_missing(conn, "ingest_queue", "started_at", "REAL")?;
        Self::add_column_if_missing(
            conn,
            "ingest_queue",
            "priority",
            "INTEGER NOT NULL DEFAULT 0",
        )?;

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_queue(status)",
            [],
        )?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ingest_doc_id ON ingest_queue(doc_id)",
            [],
        )?;

        // 阶段耗时分析表（只读分析，不阻塞主流程）
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ingest_stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL,
                duration_secs REAL,
                success INTEGER DEFAULT 1
            )",
            [],
        )?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stage_history_task ON ingest_stage_history(task_id)",
            [],
        )?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_stage_history_stage ON ingest_stage_history(stage)",
            [],
        )?;

        // ingest 日志表（事件通道的 DB 兜底 — 即使 Tauri 事件丢失/订阅失败，UI 也能拉到）
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ingest_logs (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id  TEXT NOT NULL,
                stage   TEXT NOT NULL,
                level   TEXT NOT NULL,
                message TEXT NOT NULL,
                ts_ms   INTEGER NOT NULL,
                task_id TEXT
            )",
            [],
        )?;
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ingest_logs_doc_id ON ingest_logs(doc_id, ts_ms)",
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
                         (id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, file_hash, file_size_bytes, started_at, created_at, updated_at, priority)
                         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)",
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
                            "",
                            task.file_size_bytes,
                            task.started_at,
                            task.created_at,
                            task.updated_at,
                            task.priority,
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
            file_size_bytes: row.get::<_, Option<i64>>(12)?.map(|n| n as u64),
            started_at: row.get(13)?,
            created_at: row.get(14)?,
            updated_at: row.get(15)?,
            priority: row.get::<_, i32>(16)?,
        })
    }

    /// 入队一个文件
    pub async fn enqueue(&self, file_path: String, doc_id: String) -> AppResult<String> {
        self.enqueue_with_stage(file_path, doc_id, "inspector", false)
            .await
    }

    /// 入队一个指定阶段的文件。
    ///
    /// 幂等：同文件 hash 且未失败/未取消的任务已存在时，直接返回已有任务 id。
    /// `force=true` 跳过幂等检查 — 用于对已索引文件强制重新入队，保留历史记录。
    /// 背压：pending + processing 任务数达到 `MAX_ACTIVE_QUEUE_SIZE` 时拒绝入队。
    pub async fn enqueue_with_stage(
        &self,
        file_path: String,
        doc_id: String,
        stage: &str,
        force: bool,
    ) -> AppResult<String> {
        let conn = self.conn.lock().await;
        let file_hash =
            crate::core::helpers::sha256_file(Path::new(&file_path)).unwrap_or_default();

        // 容量控制：pending + processing 不超过上限
        let active_count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ingest_queue WHERE status IN ('pending', 'processing')",
            [],
            |row| row.get(0),
        )?;
        if active_count as usize >= MAX_ACTIVE_QUEUE_SIZE {
            return Err(AppError::new(
                ErrorCode::QueueFull,
                format!(
                    "Ingest queue is full ({} active tasks)",
                    MAX_ACTIVE_QUEUE_SIZE
                ),
            )
            .with_suggestion("等待当前任务完成后再导入，或清理队列"));
        }

        // 幂等：同 hash 且未失败/未取消的任务直接返回已有 id
        if !force && !file_hash.is_empty() {
            let existing = conn.query_row(
                "SELECT id, status FROM ingest_queue WHERE file_hash = ?1 ORDER BY created_at DESC LIMIT 1",
                params![file_hash],
                |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
            );
            if let Ok((id, status)) = existing {
                if status != "failed" && status != "cancelled" {
                    log::info!("IngestQueue: skip duplicate hash, existing task {}", id);
                    return Ok(id);
                }
            }
        }

        let mut task = IngestTask::with_stage(file_path.clone(), doc_id, stage);
        task.file_size_bytes = std::fs::metadata(&file_path).map(|m| m.len()).ok();
        let id = task.id.clone();
        let now = task.created_at;

        conn.execute(
            "INSERT INTO ingest_queue
             (id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, file_hash, file_size_bytes, started_at, created_at, updated_at, priority)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12, ?13, ?14, ?15, ?16, ?17, ?18)",
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
                file_hash,
                task.file_size_bytes,
                task.started_at,
                now,
                now,
                task.priority,
            ],
        )?;

        log::info!("IngestQueue: enqueued {} stage={}", id, stage);
        Ok(id)
    }

    /// 取出下一个待处理任务
    pub async fn dequeue(&self) -> AppResult<Option<IngestTask>> {
        let conn = self.conn.lock().await;

        // 找第一个 Pending 或可重试的 Failed 任务
        let mut stmt = conn.prepare(
            "SELECT id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, file_size_bytes, started_at, created_at, updated_at, priority
             FROM ingest_queue
             WHERE status = 'pending'
                OR (status = 'failed' AND retry_count < max_retries)
             ORDER BY priority DESC, created_at ASC
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
                 SET status = 'processing', started_at = ?1, updated_at = ?1
                 WHERE id = ?2",
                params![now, &task.id],
            )?;
            task.status = IngestStatus::Processing;
            task.started_at = Some(now);
            task.updated_at = now;
        }

        Ok(task)
    }

    /// 标记任务完成
    pub async fn mark_done(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn mark_failed(&self, task_id: &str, error: String) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn cancel(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn cancel_all_pending(&self) -> AppResult<usize> {
        let conn = self.conn.lock().await;
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
    pub async fn cleanup(&self) -> AppResult<usize> {
        let conn = self.conn.lock().await;
        let changed = conn.execute(
            "DELETE FROM ingest_queue
             WHERE status IN ('done', 'cancelled')",
            [],
        )?;
        Ok(changed)
    }

    /// 队列统计
    pub async fn stats(&self) -> AppResult<QueueStats> {
        let (total, pending, processing, done, failed, cancelled) = {
            let conn = self.conn.lock().await;

            let total: i64 =
                conn.query_row("SELECT COUNT(*) FROM ingest_queue", [], |r| r.get(0))?;

            let mut stmt =
                conn.prepare("SELECT status, COUNT(*) FROM ingest_queue GROUP BY status")?;
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

            (total, pending, processing, done, failed, cancelled)
        };

        let avg_stage_durations_ms = self.avg_stage_durations_ms(5).await.unwrap_or([0; 5]);

        Ok(QueueStats {
            total: total as usize,
            pending,
            processing,
            done,
            failed,
            cancelled,
            avg_stage_durations_ms,
        })
    }

    /// 获取所有任务（用于 UI 展示）
    pub async fn list_all(&self) -> AppResult<Vec<IngestTask>> {
        let conn = self.conn.lock().await;
        let mut stmt = conn.prepare(
            "SELECT id, file_path, doc_id, status, stage, progress_pct, pages_total, pages_done, details, retry_count, max_retries, error, file_size_bytes, started_at, created_at, updated_at, priority
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

    /// 追加一条 ingest 日志（事件通道的 DB 兜底）
    /// `task_id` 可选 — 兼容历史调用。
    pub async fn add_log(
        &self,
        doc_id: &str,
        stage: &str,
        level: &str,
        message: &str,
        ts_ms: u64,
        task_id: Option<&str>,
    ) -> AppResult<()> {
        let conn = self.conn.lock().await;
        conn.execute(
            "INSERT INTO ingest_logs (doc_id, stage, level, message, ts_ms, task_id)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
            params![
                doc_id,
                stage,
                level,
                message,
                ts_ms as i64,
                task_id,
            ],
        )?;
        Ok(())
    }

    /// 获取某 doc_id 的最近 N 条日志，按 ts_ms 升序返回。
    pub async fn list_logs(
        &self,
        doc_id: &str,
        limit: usize,
    ) -> AppResult<Vec<IngestLogRecord>> {
        let conn = self.conn.lock().await;
        let mut stmt = conn.prepare(
            "SELECT doc_id, stage, level, message, ts_ms, task_id
             FROM ingest_logs WHERE doc_id = ?1
             ORDER BY ts_ms DESC LIMIT ?2",
        )?;
        let rows = stmt.query_map(params![doc_id, limit as i64], |row| {
            Ok(IngestLogRecord {
                doc_id: row.get(0)?,
                stage: row.get(1)?,
                level: row.get(2)?,
                message: row.get(3)?,
                ts_ms: row.get::<_, i64>(4)? as u64,
                task_id: row.get(5)?,
            })
        })?;
        let mut out: Vec<IngestLogRecord> = Vec::new();
        for r in rows {
            out.push(r?);
        }
        out.reverse();
        Ok(out)
    }

    /// 检查文件是否已在队列中（Pending/Processing/Done 状态）
    pub async fn contains_file(&self, file_path: &str) -> AppResult<bool> {
        let conn = self.conn.lock().await;
        let count: i64 = conn.query_row(
            "SELECT COUNT(*) FROM ingest_queue
             WHERE file_path = ?1 AND status IN ('pending', 'processing', 'done')",
            params![file_path],
            |r| r.get(0),
        )?;
        Ok(count > 0)
    }

    /// 更新任务进度与阶段（worker 使用）
    pub async fn update_progress(
        &self,
        task_id: &str,
        stage: &str,
        progress_pct: f64,
        pages_done: i32,
        pages_total: i32,
        details: &str,
    ) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn set_stage(&self, task_id: &str, stage: &str) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn set_pending(&self, task_id: &str) -> AppResult<()> {
        let conn = self.conn.lock().await;
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
    pub async fn retry(&self, task_id: &str) -> AppResult<bool> {
        let conn = self.conn.lock().await;
        let now = now_secs_f64();
        let changed = conn.execute(
            "UPDATE ingest_queue
             SET status = 'pending', error = NULL, updated_at = ?1
             WHERE id = ?2 AND status = 'failed' AND retry_count < max_retries",
            params![now, task_id],
        )?;
        Ok(changed > 0)
    }

    /// 修改任务优先级（越高越优先）。
    pub async fn set_priority(&self, task_id: &str, priority: i32) -> AppResult<()> {
        let conn = self.conn.lock().await;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_queue SET priority = ?1, updated_at = ?2 WHERE id = ?3",
            params![priority, now, task_id],
        )?;
        Ok(())
    }

    /// 删除指定任务（仅允许删除 done / cancelled / failed 任务）。
    pub async fn delete_task(&self, task_id: &str) -> AppResult<bool> {
        let conn = self.conn.lock().await;
        let changed = conn.execute(
            "DELETE FROM ingest_queue WHERE id = ?1 AND status IN ('done', 'cancelled', 'failed')",
            params![task_id],
        )?;
        Ok(changed > 0)
    }

    /// 记录阶段开始，返回历史行 id。
    pub async fn record_stage_start(
        &self,
        task_id: &str,
        doc_id: &str,
        stage: &str,
    ) -> AppResult<i64> {
        let conn = self.conn.lock().await;
        let now = now_secs_f64();
        conn.execute(
            "INSERT INTO ingest_stage_history (task_id, doc_id, stage, started_at)
             VALUES (?1, ?2, ?3, ?4)",
            params![task_id, doc_id, stage, now],
        )?;
        Ok(conn.last_insert_rowid())
    }

    /// 回填阶段结束与耗时。
    pub async fn record_stage_end(
        &self,
        row_id: i64,
        duration_secs: f64,
        success: bool,
    ) -> AppResult<()> {
        let conn = self.conn.lock().await;
        let now = now_secs_f64();
        conn.execute(
            "UPDATE ingest_stage_history
             SET completed_at = ?1, duration_secs = ?2, success = ?3
             WHERE id = ?4",
            params![now, duration_secs, if success { 1 } else { 0 }, row_id],
        )?;
        Ok(())
    }

    /// 最近 N 个 done 任务的每阶段平均耗时（毫秒）。
    pub async fn avg_stage_durations_ms(&self, n: usize) -> AppResult<[u64; 5]> {
        let conn = self.conn.lock().await;
        const STAGES: [&str; 5] = ["inspector", "text_extract", "ocr", "moldet", "index"];
        let mut result = [0u64; 5];

        let mut stmt = conn.prepare(
            "SELECT h.stage, AVG(h.duration_secs)
             FROM ingest_stage_history h
             JOIN (
                 SELECT id FROM ingest_queue
                 WHERE status = 'done'
                 ORDER BY updated_at DESC
                 LIMIT ?1
             ) t ON h.task_id = t.id
             WHERE h.success = 1 AND h.duration_secs IS NOT NULL
             GROUP BY h.stage",
        )?;
        let rows = stmt.query_map(params![n as i64], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
        })?;
        for row in rows {
            let (stage, avg_secs) = row?;
            if let Some(pos) = STAGES.iter().position(|&s| s == stage) {
                result[pos] = (avg_secs * 1000.0).round() as u64;
            }
        }
        Ok(result)
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
    pub avg_stage_durations_ms: [u64; 5],
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

    #[tokio::test]
    async fn test_queue_enqueue_dequeue() {
        let (_dir, queue) = setup_queue();

        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();
        assert_eq!(queue.stats().await.unwrap().pending, 1);

        let task = queue.dequeue().await.unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.status, IngestStatus::Processing);
        assert_eq!(task.stage, "inspector");

        queue.mark_done(&id).await.unwrap();
        assert_eq!(queue.stats().await.unwrap().done, 1);
    }

    #[tokio::test]
    async fn test_queue_with_stage() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue_with_stage("test.pdf".into(), "doc1".into(), "ocr", false)
            .await
            .unwrap();
        let task = queue.dequeue().await.unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.stage, "ocr");
    }

    #[tokio::test]
    async fn test_queue_file_size_and_started_at() {
        let (dir, queue) = setup_queue();
        let path = dir.path().join("sample.pdf");
        std::fs::write(&path, b"%PDF sample content").unwrap();
        let path_str = path.to_string_lossy().to_string();

        let id = queue.enqueue(path_str, "doc1".into()).await.unwrap();
        let pending = queue.list_all().await.unwrap().pop().unwrap();
        assert_eq!(pending.file_size_bytes, Some(19));
        assert!(pending.started_at.is_none());

        let task = queue.dequeue().await.unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.file_size_bytes, Some(19));
        assert!(task.started_at.is_some());
    }

    #[tokio::test]
    async fn test_queue_update_progress() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();
        queue
            .update_progress(&id, "text_extract", 0.5, 3, 6, "extracting")
            .await
            .unwrap();
        let task = queue.list_all().await.unwrap().pop().unwrap();
        assert_eq!(task.stage, "text_extract");
        assert_eq!(task.progress_pct, 0.5);
        assert_eq!(task.pages_done, 3);
        assert_eq!(task.pages_total, 6);
        assert_eq!(task.details, "extracting");
    }

    #[tokio::test]
    async fn test_queue_retry() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();

        // 第一次失败 → 重试
        queue.mark_failed(&id, "LLM timeout".into()).await.unwrap();
        assert_eq!(queue.stats().await.unwrap().pending, 1);

        // 第二次失败 → 重试
        let task = queue.dequeue().await.unwrap().unwrap();
        queue
            .mark_failed(&task.id, "LLM timeout".into())
            .await
            .unwrap();
        assert_eq!(queue.stats().await.unwrap().pending, 1);

        // 第三次失败 → 永久失败
        let task = queue.dequeue().await.unwrap().unwrap();
        queue
            .mark_failed(&task.id, "LLM timeout".into())
            .await
            .unwrap();
        assert_eq!(queue.stats().await.unwrap().failed, 1);
        assert_eq!(queue.stats().await.unwrap().pending, 0);
    }

    #[tokio::test]
    async fn test_queue_contains_file() {
        let (_dir, queue) = setup_queue();
        assert!(!queue.contains_file("test.pdf").await.unwrap());

        queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();
        assert!(queue.contains_file("test.pdf").await.unwrap());
    }

    #[tokio::test]
    async fn test_queue_persistence() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        // 写入
        {
            let queue = IngestQueue::new(root).unwrap();
            queue.enqueue("a.pdf".into(), "d1".into()).await.unwrap();
            queue.enqueue("b.pdf".into(), "d2".into()).await.unwrap();
        }

        // 重新加载
        {
            let queue = IngestQueue::new(root).unwrap();
            assert_eq!(queue.stats().await.unwrap().total, 2);
        }
    }

    #[tokio::test]
    async fn test_queue_cleanup() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();
        queue.mark_done(&id).await.unwrap();

        queue
            .enqueue("test2.pdf".into(), "doc2".into())
            .await
            .unwrap();

        let removed = queue.cleanup().await.unwrap();
        assert_eq!(removed, 1);
        assert_eq!(queue.stats().await.unwrap().total, 1);
    }

    #[tokio::test]
    async fn test_queue_capacity_backpressure() {
        let (dir, queue) = setup_queue();
        for i in 0..MAX_ACTIVE_QUEUE_SIZE {
            let path = dir.path().join(format!("doc{}.pdf", i));
            std::fs::write(&path, format!("%PDF {}", i)).unwrap();
            queue
                .enqueue(path.to_string_lossy().to_string(), format!("doc{}", i))
                .await
                .unwrap();
        }
        assert_eq!(queue.stats().await.unwrap().pending, MAX_ACTIVE_QUEUE_SIZE);

        let overflow = dir.path().join("overflow.pdf");
        std::fs::write(&overflow, b"%PDF overflow").unwrap();
        let err = queue
            .enqueue(overflow.to_string_lossy().to_string(), "overflow".into())
            .await
            .unwrap_err();
        assert_eq!(err.code, ErrorCode::QueueFull);
    }

    #[tokio::test]
    async fn test_queue_idempotent_by_hash() {
        let (dir, queue) = setup_queue();
        let path = dir.path().join("same.pdf");
        std::fs::write(&path, b"%PDF same").unwrap();
        let path_str = path.to_string_lossy().to_string();

        let id1 = queue
            .enqueue(path_str.clone(), "doc1".into())
            .await
            .unwrap();
        let id2 = queue
            .enqueue(path_str.clone(), "doc2".into())
            .await
            .unwrap();
        assert_eq!(id1, id2);
        assert_eq!(queue.stats().await.unwrap().pending, 1);

        // 失败的任务允许重新入队（先把它标记为永久失败）
        queue.mark_failed(&id1, "timeout".into()).await.unwrap();
        queue.mark_failed(&id1, "timeout".into()).await.unwrap();
        queue.mark_failed(&id1, "timeout".into()).await.unwrap();
        assert_eq!(queue.stats().await.unwrap().failed, 1);
        let id3 = queue.enqueue(path_str, "doc3".into()).await.unwrap();
        assert_ne!(id1, id3);
        assert_eq!(queue.stats().await.unwrap().pending, 1);
        assert_eq!(queue.stats().await.unwrap().failed, 1);
    }

    #[tokio::test]
    async fn test_legacy_migration() {
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
        )
        .unwrap();

        // 新队列应自动迁移
        let queue = IngestQueue::new(root).unwrap();
        let stats = queue.stats().await.unwrap();
        assert_eq!(stats.total, 1);
        assert_eq!(stats.pending, 1);

        // 旧文件应被重命名
        assert!(!root.join(".mbforge").join("ingest-queue.json").exists());
        assert!(root.join(".mbforge").join("ingest-queue.json.bak").exists());
    }

    #[tokio::test]
    async fn test_priority_dequeue_order() {
        let (_dir, queue) = setup_queue();
        let low = queue
            .enqueue("low.pdf".into(), "doc-low".into())
            .await
            .unwrap();
        let high = queue
            .enqueue("high.pdf".into(), "doc-high".into())
            .await
            .unwrap();
        queue.set_priority(&low, 0).await.unwrap();
        queue.set_priority(&high, 5).await.unwrap();

        let first = queue.dequeue().await.unwrap().unwrap();
        assert_eq!(first.id, high);

        queue.mark_done(&first.id).await.unwrap();
        let second = queue.dequeue().await.unwrap().unwrap();
        assert_eq!(second.id, low);
    }

    #[tokio::test]
    async fn test_avg_stage_durations_ms() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();
        let task = queue.dequeue().await.unwrap().unwrap();

        let row_id = queue
            .record_stage_start(&task.id, &task.doc_id, "inspector")
            .await
            .unwrap();
        queue.record_stage_end(row_id, 1.5, true).await.unwrap();

        queue.mark_done(&id).await.unwrap();
        let avg = queue.avg_stage_durations_ms(5).await.unwrap();
        assert_eq!(avg[0], 1500);
        assert_eq!(avg.iter().skip(1).sum::<u64>(), 0);

        let stats = queue.stats().await.unwrap();
        assert_eq!(stats.avg_stage_durations_ms[0], 1500);
    }

    #[tokio::test]
    async fn test_delete_task() {
        let (_dir, queue) = setup_queue();
        let id = queue
            .enqueue("test.pdf".into(), "doc1".into())
            .await
            .unwrap();

        // pending 任务不允许删除
        assert!(!queue.delete_task(&id).await.unwrap());
        assert!(queue.list_all().await.unwrap().iter().any(|t| t.id == id));

        queue.mark_done(&id).await.unwrap();
        assert!(queue.delete_task(&id).await.unwrap());
        assert!(!queue.list_all().await.unwrap().iter().any(|t| t.id == id));
    }
}
