//! 提取队列 — 持久化的文档处理队列，支持重试和取消
//!
//! 灵感来自 wiki 应用的 ingest-queue 模式：
//! - 文件进入项目目录 → 入队
//! - 异步处理 → 重试（最多 3 次）→ 完成/失败
//! - 支持取消、暂停（项目切换时）
//! - 持久化到 .mbforge/ingest-queue.json

use std::collections::VecDeque;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

/// 队列任务状态
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

/// 单个提取任务
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IngestTask {
    pub id: String,
    pub file_path: String,
    pub doc_id: String,
    pub status: IngestStatus,
    pub retry_count: u32,
    pub max_retries: u32,
    pub error: Option<String>,
    pub created_at: f64,
    pub updated_at: f64,
}

impl IngestTask {
    pub fn new(file_path: String, doc_id: String) -> Self {
        let now = now_secs();
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            file_path,
            doc_id,
            status: IngestStatus::Pending,
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

/// 队列持久化格式
#[derive(Debug, Clone, Serialize, Deserialize)]
struct QueueData {
    tasks: Vec<IngestTask>,
}

/// 提取队列
pub struct IngestQueue {
    tasks: Arc<Mutex<VecDeque<IngestTask>>>,
    queue_path: PathBuf,
}

impl IngestQueue {
    pub fn new(project_root: &PathBuf) -> Self {
        let queue_path = project_root.join(".mbforge").join("ingest-queue.json");
        let tasks = Self::load_from_disk(&queue_path);
        Self {
            tasks: Arc::new(Mutex::new(tasks)),
            queue_path,
        }
    }

    /// 从磁盘加载队列
    fn load_from_disk(path: &PathBuf) -> VecDeque<IngestTask> {
        match std::fs::read_to_string(path) {
            Ok(data) => serde_json::from_str::<QueueData>(&data)
                .map(|d| d.tasks.into())
                .unwrap_or_default(),
            Err(_) => VecDeque::new(),
        }
    }

    /// 保存到磁盘
    fn save_to_disk(&self) -> Result<(), String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        let data = QueueData {
            tasks: tasks.iter().cloned().collect(),
        };
        let json =
            serde_json::to_string_pretty(&data).map_err(|e| format!("Serialize error: {}", e))?;

        if let Some(parent) = self.queue_path.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|e| format!("Create dir failed: {}", e))?;
        }
        std::fs::write(&self.queue_path, json)
            .map_err(|e| format!("Write queue failed: {}", e))?;
        Ok(())
    }

    /// 入队一个文件
    pub fn enqueue(&self, file_path: String, doc_id: String) -> Result<String, String> {
        let task = IngestTask::new(file_path, doc_id);
        let id = task.id.clone();

        {
            let mut tasks = self
                .tasks
                .lock()
                .map_err(|e| format!("Lock error: {}", e))?;
            tasks.push_back(task);
        }

        self.save_to_disk()?;
        log::info!("IngestQueue: enqueued {}", id);
        Ok(id)
    }

    /// 取出下一个待处理任务
    pub fn dequeue(&self) -> Result<Option<IngestTask>, String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        // 找第一个 Pending 或可重试的 Failed 任务
        let idx = tasks.iter().position(|t| {
            t.status == IngestStatus::Pending || t.can_retry()
        });

        if let Some(idx) = idx {
            let mut task = tasks[idx].clone();
            task.status = IngestStatus::Processing;
            task.updated_at = now_secs();
            tasks[idx] = task.clone();
            self.save_to_disk()?;
            Ok(Some(task))
        } else {
            Ok(None)
        }
    }

    /// 标记任务完成
    pub fn mark_done(&self, task_id: &str) -> Result<(), String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        if let Some(task) = tasks.iter_mut().find(|t| t.id == task_id) {
            task.status = IngestStatus::Done;
            task.error = None;
            task.updated_at = now_secs();
        }

        self.save_to_disk()?;
        Ok(())
    }

    /// 标记任务失败（自动判断是否可重试）
    pub fn mark_failed(&self, task_id: &str, error: String) -> Result<(), String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        if let Some(task) = tasks.iter_mut().find(|t| t.id == task_id) {
            task.retry_count += 1;
            task.error = Some(error.clone());
            task.updated_at = now_secs();

            if task.retry_count >= task.max_retries {
                task.status = IngestStatus::Failed; // 永久失败
                log::warn!(
                    "IngestQueue: task {} permanently failed after {} retries: {}",
                    task_id,
                    task.retry_count,
                    error
                );
            } else {
                task.status = IngestStatus::Pending; // 重新入队
                log::info!(
                    "IngestQueue: task {} will retry ({}/{}): {}",
                    task_id,
                    task.retry_count,
                    task.max_retries,
                    error
                );
            }
        }

        self.save_to_disk()?;
        Ok(())
    }

    /// 取消一个任务
    pub fn cancel(&self, task_id: &str) -> Result<(), String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        if let Some(task) = tasks.iter_mut().find(|t| t.id == task_id) {
            task.status = IngestStatus::Cancelled;
            task.updated_at = now_secs();
        }

        self.save_to_disk()?;
        Ok(())
    }

    /// 取消所有待处理任务（项目切换时暂停）
    pub fn cancel_all_pending(&self) -> Result<usize, String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        let mut cancelled = 0;
        for task in tasks.iter_mut() {
            if task.status == IngestStatus::Pending || task.status == IngestStatus::Processing {
                task.status = IngestStatus::Cancelled;
                task.updated_at = now_secs();
                cancelled += 1;
            }
        }

        self.save_to_disk()?;
        Ok(cancelled)
    }

    /// 清理已完成/取消的任务
    pub fn cleanup(&self) -> Result<usize, String> {
        let mut tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        let before = tasks.len();
        tasks.retain(|t| t.status == IngestStatus::Pending || t.status == IngestStatus::Processing || t.can_retry());
        let removed = before - tasks.len();

        if removed > 0 {
            self.save_to_disk()?;
        }

        Ok(removed)
    }

    /// 队列统计
    pub fn stats(&self) -> Result<QueueStats, String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;

        Ok(QueueStats {
            total: tasks.len(),
            pending: tasks.iter().filter(|t| t.status == IngestStatus::Pending).count(),
            processing: tasks.iter().filter(|t| t.status == IngestStatus::Processing).count(),
            done: tasks.iter().filter(|t| t.status == IngestStatus::Done).count(),
            failed: tasks.iter().filter(|t| t.status == IngestStatus::Failed).count(),
            cancelled: tasks.iter().filter(|t| t.status == IngestStatus::Cancelled).count(),
        })
    }

    /// 获取所有任务（用于 UI 展示）
    pub fn list_all(&self) -> Result<Vec<IngestTask>, String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        Ok(tasks.iter().cloned().collect())
    }

    /// 检查文件是否已在队列中（避免重复入队）
    pub fn contains_file(&self, file_path: &str) -> Result<bool, String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|e| format!("Lock error: {}", e))?;
        Ok(tasks.iter().any(|t| {
            t.file_path == file_path
                && (t.status == IngestStatus::Pending
                    || t.status == IngestStatus::Processing
                    || t.status == IngestStatus::Done)
        }))
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

fn now_secs() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_queue_enqueue_dequeue() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().to_path_buf();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        let queue = IngestQueue::new(&root);

        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        assert_eq!(queue.stats().unwrap().pending, 1);

        let task = queue.dequeue().unwrap().unwrap();
        assert_eq!(task.id, id);
        assert_eq!(task.status, IngestStatus::Processing);

        queue.mark_done(&id).unwrap();
        assert_eq!(queue.stats().unwrap().done, 1);
    }

    #[test]
    fn test_queue_retry() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().to_path_buf();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        let queue = IngestQueue::new(&root);
        let id = queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();

        // 第一次失败 → 重试
        queue.mark_failed(&id, "LLM timeout".into()).unwrap();
        assert_eq!(queue.stats().unwrap().pending, 1); // 重新入队

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
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().to_path_buf();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        let queue = IngestQueue::new(&root);
        assert!(!queue.contains_file("test.pdf").unwrap());

        queue.enqueue("test.pdf".into(), "doc1".into()).unwrap();
        assert!(queue.contains_file("test.pdf").unwrap());
    }

    #[test]
    fn test_queue_persistence() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().to_path_buf();
        std::fs::create_dir_all(root.join(".mbforge")).unwrap();

        // 写入
        {
            let queue = IngestQueue::new(&root);
            queue.enqueue("a.pdf".into(), "d1".into()).unwrap();
            queue.enqueue("b.pdf".into(), "d2".into()).unwrap();
        }

        // 重新加载
        {
            let queue = IngestQueue::new(&root);
            assert_eq!(queue.stats().unwrap().total, 2);
        }
    }
}
