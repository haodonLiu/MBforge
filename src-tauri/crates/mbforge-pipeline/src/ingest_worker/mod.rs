//! Ingest queue background worker.
//!
//! 一个项目内只启动一个 worker，循环从 `IngestQueue` 取出任务并按阶段处理。
//! 阶段包括：inspector → text_extract/ocr → moldet → index。

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{AppHandle, Emitter};

use crate::pipeline::context::{PipelineContext, PipelineEvent, PipelineReporter};
use crate::pipeline::models::source::SourceInput;
use crate::pipeline::runner::run_pipeline;
use mbforge_domain::ingest_queue::{IngestQueue, IngestTask, QueueStats};
use mbforge_domain::project::document_project::DocumentProject;
use mbforge_domain::project::project::Project;
use mbforge_infra::config::constants::{
    EVT_INGEST_LOG, EVT_INGEST_PROGRESS, EVT_INGEST_QUEUE_UPDATE,
    EVT_INGEST_WORKER_HEARTBEAT,
};

const WORKER_HEARTBEAT_INTERVAL_SECS: u64 = 5;

/// App state that holds the active ingest worker.
#[derive(Default)]
pub struct IngestWorkerState {
    /// Active ingest worker instance.
    pub worker: Mutex<Option<IngestWorker>>,
}

/// 后台 ingest worker。
pub struct IngestWorker {
    project_root: PathBuf,
    running: Arc<AtomicBool>,
    last_heartbeat: Arc<AtomicU64>,
}

impl IngestWorker {
    /// 启动 worker。
    pub fn start(project_root: PathBuf, app_handle: AppHandle) -> Self {
        let running = Arc::new(AtomicBool::new(true));
        let running_clone = Arc::clone(&running);
        let last_heartbeat = Arc::new(AtomicU64::new(mbforge_infra::helpers::now_secs_u64()));
        let last_heartbeat_clone = Arc::clone(&last_heartbeat);
        let root = project_root.clone();

        tauri::async_runtime::spawn(async move {
            worker_loop(root, app_handle, running_clone, last_heartbeat_clone).await;
        });

        Self {
            project_root,
            running,
            last_heartbeat,
        }
    }

    /// 停止 worker（温和停止，当前任务处理完后退出）。
    pub fn stop(&self) {
        self.running.store(false, Ordering::Relaxed);
        log::info!(
            "IngestWorker: stop requested for {}",
            self.project_root.display()
        );
    }

    /// 最近一次心跳时间戳（Unix 秒）。
    pub fn last_heartbeat(&self) -> u64 {
        self.last_heartbeat.load(Ordering::Relaxed)
    }
}

async fn worker_loop(
    project_root: PathBuf,
    app_handle: AppHandle,
    running: Arc<AtomicBool>,
    last_heartbeat: Arc<AtomicU64>,
) {
    let queue = match IngestQueue::new(&project_root) {
        Ok(q) => Arc::new(q),
        Err(e) => {
            log::error!("IngestWorker: failed to open queue: {}", e);
            return;
        }
    };

    log::info!("IngestWorker: started for {}", project_root.display());

    // 后台心跳：即使长时间任务也能保证前端可观测 worker 存活。
    spawn_heartbeat(
        project_root.clone(),
        app_handle.clone(),
        Arc::clone(&running),
        last_heartbeat,
    );

    while running.load(Ordering::Relaxed) {
        let task = match queue.dequeue().await {
            Ok(t) => t,
            Err(e) => {
                log::error!("IngestWorker: dequeue failed: {}", e);
                tokio::time::sleep(Duration::from_millis(500)).await;
                continue;
            }
        };

        let Some(task) = task else {
            tokio::time::sleep(Duration::from_millis(500)).await;
            continue;
        };

        log::info!(
            "IngestWorker: processing task {} doc_id={} stage={}",
            task.id,
            task.doc_id,
            task.stage
        );

        let stage_started_at = mbforge_infra::helpers::now_secs_f64();
        let stage_hist_id = match queue
            .record_stage_start(&task.id, &task.doc_id, &task.stage)
            .await
        {
            Ok(id) => Some(id),
            Err(e) => {
                log::warn!("IngestWorker: record_stage_start failed: {}", e);
                None
            }
        };

        emit_progress(
            &app_handle,
            &task,
            &task.stage,
            task.progress_pct,
            task.pages_done,
            task.pages_total,
            "processing",
        );

        emit_log(
            Some(&queue),
            &app_handle,
            &task.doc_id,
            &task.id,
            &task.stage,
            "info",
            format!("进入 {} 阶段 (task id={})", task.stage, task.id),
        );
        // Single stage: legacy 5-stage names are accepted and routed to
        // the v2 `run_pipeline` (which handles extract → segment → enrich
        // → persist → index internally). Unknown stages are flagged via
        // `mark_failed` with a permanent error to avoid retry loops.
        let result = match task.stage.as_str() {
            "inspector" | "text_extract" | "ocr" | "moldet" | "index" | "run_pipeline" => {
                process_run_pipeline(&project_root, &queue, &task, &app_handle).await
            }
            other => Err(format!(
                "Unknown stage '{other}'; supported: inspector, text_extract, ocr, moldet, index, run_pipeline"
            )),
        };

        // Single unified stage: process_run_pipeline always returns
        // `StageResult::Done` on success or `Err` on failure. The old
        // `Continue` arm (which transitioned to a next stage) is
        // unreachable now.
        let stage_duration_secs = mbforge_infra::helpers::now_secs_f64() - stage_started_at;
        let stage_dur_str = format!("{:.2}s", stage_duration_secs);
        match result {
            Ok(StageResult::Done) => {
                if let Some(id) = stage_hist_id {
                    if let Err(e) = queue.record_stage_end(id, stage_duration_secs, true).await {
                        log::warn!("IngestWorker: record_stage_end failed: {}", e);
                    }
                }
                if let Err(e) = queue.mark_done(&task.id).await {
                    log::error!("IngestWorker: mark_done failed: {}", e);
                }
                emit_queue_update(&app_handle, &queue, &task.doc_id, "done").await;
            }
            Err(e) => {
                if let Some(id) = stage_hist_id {
                    if let Err(inner) = queue.record_stage_end(id, stage_duration_secs, false).await
                    {
                        log::warn!("IngestWorker: record_stage_end failed: {}", inner);
                    }
                }
                log::error!(
                    "IngestWorker: task {} stage {} failed: {}",
                    task.id,
                    task.stage,
                    e
                );
                emit_log(
                    Some(&queue),
                    &app_handle,
                    &task.doc_id,
                    &task.id,
                    &task.stage,
                    "error",
                    format!("{} 阶段失败 ({}): {}", task.stage, stage_dur_str, e),
                );
                if let Err(inner) = queue.mark_failed(&task.id, e.clone()).await {
                    log::error!("IngestWorker: mark_failed failed: {}", inner);
                }
                set_doc_status_error(&project_root, &task, &e);
                emit_queue_update(&app_handle, &queue, &task.doc_id, "failed").await;
            }
        }

        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    log::info!("IngestWorker: stopped for {}", project_root.display());
}

/// Stage result. With the unified pipeline, only `Done` is produced;
/// the legacy `Continue` arm has been removed.
enum StageResult {
    /// Task complete.
    Done,
}

/// 启动独立心跳任务，周期性 emit `EVT_INGEST_WORKER_HEARTBEAT`。
fn spawn_heartbeat(
    project_root: PathBuf,
    app_handle: AppHandle,
    running: Arc<AtomicBool>,
    last_heartbeat: Arc<AtomicU64>,
) {
    tauri::async_runtime::spawn(async move {
        let mut interval =
            tokio::time::interval(Duration::from_secs(WORKER_HEARTBEAT_INTERVAL_SECS));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        while running.load(Ordering::Relaxed) {
            interval.tick().await;
            let now = mbforge_infra::helpers::now_secs_u64();
            last_heartbeat.store(now, Ordering::Relaxed);
            let payload = serde_json::json!({
                "project_root": project_root.to_string_lossy(),
                "ts": now,
                "alive": true,
            });
            if let Err(e) = app_handle.emit(EVT_INGEST_WORKER_HEARTBEAT, &payload) {
                log::warn!("IngestWorker: emit heartbeat failed: {}", e);
            }
        }
    });
}

/// Validate a task file path against the project root.
fn validate_task_file_path(project_root: &Path, task: &IngestTask) -> Result<String, String> {
    let path = Path::new(&task.file_path);
    if !path.exists() {
        return Err(format!("source file not found: {}", path.display()));
    }
    let check =
        mbforge_infra::helpers::assert_within_root(project_root.to_string_lossy().as_ref(), path)
            .map_err(|e| format!("task file path safety check failed: {}", e))?;
    check
        .canonical
        .to_str()
        .map(|s| s.to_string())
        .ok_or_else(|| {
            format!(
                "task file path is not valid UTF-8: {}",
                check.canonical.display()
            )
        })
}

/// 每阶段开始前的预检：文件、项目目录、磁盘空间、index 可写、sidecar 健康。
async fn preflight_check(stage: &str, file_path: &Path, project_root: &Path) -> Result<(), String> {
    if !file_path.exists() {
        return Err(format!("source file not found: {}", file_path.display()));
    }
    if !project_root.exists() || !project_root.is_dir() {
        return Err(format!(
            "project root not found: {}",
            project_root.display()
        ));
    }

    const MIN_SPACE_MB: u64 = 100;
    let min_bytes = MIN_SPACE_MB * 1024 * 1024;
    match mbforge_infra::helpers::available_space_bytes(project_root) {
        Ok(space) if space < min_bytes => {
            return Err(format!(
                "磁盘空间不足: 仅剩 {} MB (需要至少 {} MB)",
                space / 1024 / 1024,
                MIN_SPACE_MB
            ));
        }
        Err(e) => log::warn!("IngestWorker: unable to check disk space: {}", e),
        _ => {}
    }

    let index_dir = project_root.join(mbforge_infra::config::constants::INDEX_DIR);
    if let Err(e) = std::fs::create_dir_all(&index_dir) {
        return Err(format!("无法创建 index 目录: {}", e));
    }
    let index_dir = mbforge_infra::helpers::safe_join(
        project_root,
        mbforge_infra::config::constants::INDEX_DIR,
    )
    .map_err(|e| format!("index directory path safety check failed: {}", e))?;
    let probe = index_dir.join(".write_probe");
    if let Err(e) = std::fs::write(&probe, b"1") {
        return Err(format!("index 目录不可写: {}", e));
    }
    if let Err(e) = std::fs::remove_file(&probe) {
        log::warn!("IngestWorker: failed to remove write probe: {}", e);
    }

    if stage == "moldet" || stage == "index" {
        let client = mbforge_infra::sidecar_client::get_or_init()
            .map_err(|e| format!("Sidecar client init failed: {}", e))?;
        if let Err(e) = client.health().await {
            return Err(format!("Sidecar 未就绪: {}", e));
        }
    }

    Ok(())
}

/// Single unified stage handler. Replaces the legacy 5-stage chain
/// (inspector / text_extract / ocr / moldet / index). Drives the v2
/// `run_pipeline` which executes extract → segment → enrich → persist
/// → index in one call. Legacy stage names in the queue are accepted
/// for backward compat and routed here.
async fn process_run_pipeline(
    project_root: &Path,
    queue: &Arc<IngestQueue>,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    let file_path = validate_task_file_path(project_root, task)?;
    preflight_check("run_pipeline", Path::new(&file_path), project_root).await?;

    queue
        .update_progress(&task.id, &task.stage, 10.0, 0, 0, "starting v2 pipeline")
        .await
        .map_err(|e| format!("update progress failed: {e}"))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        10.0,
        0,
        0,
        "starting v2 pipeline",
    );
    emit_log(
        Some(queue),
        app_handle,
        &task.doc_id,
        &task.id,
        &task.stage,
        "info",
        "启动 v2 pipeline (extract → segment → enrich → persist → index)"
            .to_string(),
    );

    let reporter = Arc::new(QueueStageReporter {
        app_handle: app_handle.clone(),
        doc_id: task.doc_id.clone(),
        queue: Some(Arc::clone(queue)),
        task_id: task.id.clone(),
    });
    let input = SourceInput::new(&file_path).with_allow_ocr(true);
    let ctx = PipelineContext::new(&file_path, "")
        .with_project_root(project_root)
        .with_reporter(reporter);

    let indexed = run_pipeline(input, &ctx)
        .await
        .map_err(|e| format!("v2 pipeline failed: {e}"))?;

    queue
        .update_progress(&task.id, &task.stage, 100.0, 0, 0, "pipeline complete")
        .await
        .map_err(|e| format!("update progress failed: {e}"))?;
    emit_progress(app_handle, task, &task.stage, 100.0, 0, 0, "pipeline complete");

    // Mark every status as done — v2 covers all stages now. Preserve
    // the legacy five status fields for UI compatibility.
    for (field, value) in [
        ("inspector_status", "done"),
        ("text_status", "done"),
        ("ocr_status", "done"),
        ("moldet_status", "done"),
        ("index_status", "done"),
    ] {
        if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
            match field {
                "inspector_status" => dp.set_inspector_status(value),
                "text_status" => dp.set_text_status(value),
                "ocr_status" => dp.set_ocr_status(value),
                "moldet_status" => dp.set_moldet_status(value, &[]),
                "index_status" => dp.set_index_status(value),
                _ => {}
            }
        }
        if let Some(mut proj) = Project::open(project_root) {
            proj.set_document_status(&task.doc_id, field, value);
        }
    }

    log::info!(
        "IngestWorker: run_pipeline done doc_id={} indexed_sections={}",
        task.doc_id,
        indexed.indexed_sections,
    );

    Ok(StageResult::Done)
}

/// Forwards v2 pipeline stage events to the ingest log panel and the DB.
struct QueueStageReporter {
    app_handle: AppHandle,
    doc_id: String,
    /// Optional queue reference for DB persistence (ingest_logs).
    queue: Option<Arc<IngestQueue>>,
    task_id: String,
}

impl PipelineReporter for QueueStageReporter {
    fn report(&self, event: PipelineEvent) {
        let (stage, message) = match &event {
            PipelineEvent::StageStart { stage } => {
                (stage.as_str(), format!("阶段 {} 开始", stage))
            }
            PipelineEvent::StageProgress { stage, message } => (stage.as_str(), message.clone()),
            PipelineEvent::StageComplete { stage } => {
                (stage.as_str(), format!("阶段 {} 完成", stage))
            }
            PipelineEvent::StageWarning { stage, message } => {
                (stage.as_str(), format!("阶段 {} 警告: {}", stage, message))
            }
            PipelineEvent::StageFailed { stage, error } => {
                (stage.as_str(), format!("阶段 {} 失败: {}", stage, error))
            }
        };
        let level = if matches!(event, PipelineEvent::StageFailed { .. }) {
            "error"
        } else {
            "info"
        };
        log::debug!("PipelineEvent {:?}: {}", event, message);
        emit_log(
            self.queue.as_ref(),
            &self.app_handle,
            &self.doc_id,
            &self.task_id,
            stage,
            level,
            message,
        );
    }
}



/// Mark all five status fields as error on the document. The worker now
/// runs a single `run_pipeline` stage, so on failure we mark every
/// legacy status field as error (preserves UI compatibility).
fn set_doc_status_error(project_root: &Path, task: &IngestTask, error: &str) {
    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        dp.set_inspector_status("error");
        dp.set_text_status("error");
        dp.set_ocr_status("error");
        dp.set_moldet_status("error", &[]);
        dp.set_index_status("error");
    }
    if let Some(mut proj) = Project::open(project_root) {
        for field in [
            "inspector_status",
            "text_status",
            "ocr_status",
            "moldet_status",
            "index_status",
        ] {
            proj.set_document_status(&task.doc_id, field, "error");
        }
    }
    log::warn!(
        "IngestWorker: marked doc_id={} all stages as error: {}",
        task.doc_id,
        error
    );
}

/// Structured log line for the frontend log panel. Mirrors the same
/// info into stderr via `log::`, emits a Tauri event so the UI can
/// render a per-task expandable log box, and best-effort writes the
/// line to `ingest_logs` so the UI has a DB-backed fallback when the
/// event channel fails.
fn emit_log(
    queue: Option<&Arc<IngestQueue>>,
    app_handle: &AppHandle,
    doc_id: &str,
    task_id: &str,
    stage: &str,
    level: &str,
    message: String,
) {
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);

    // Mirror to stderr so devs can grep the Tauri log.
    match level {
        "warn" => log::warn!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
        "error" => log::error!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
        _ => log::info!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
    }

    // Fire-and-forget DB write (ingest_logs 表的兜底通道)
    if let Some(q) = queue {
        let q = Arc::clone(q);
        let doc_id = doc_id.to_string();
        let task_id = task_id.to_string();
        let stage = stage.to_string();
        let level = level.to_string();
        let message = message.clone();
        tokio::spawn(async move {
            if let Err(e) = q
                .add_log(&doc_id, &stage, &level, &message, ts_ms, Some(&task_id))
                .await
            {
                log::warn!("IngestWorker: add_log failed: {}", e);
            }
        });
    }

    let payload = serde_json::json!({
        "doc_id": doc_id,
        "stage": stage,
        "level": level,
        "message": message,
        "ts_ms": ts_ms,
    });
    if let Err(e) = app_handle.emit(EVT_INGEST_LOG, &payload) {
        log::warn!("IngestWorker: emit log failed: {}", e);
    }
}

fn emit_progress(
    app_handle: &AppHandle,
    task: &IngestTask,
    stage: &str,
    progress_pct: f64,
    pages_done: i32,
    pages_total: i32,
    details: &str,
) {
    let payload = serde_json::json!({
        "doc_id": task.doc_id,
        "stage": stage,
        "progress_pct": progress_pct,
        "pages_done": pages_done,
        "pages_total": pages_total,
        "details": details,
    });
    if let Err(e) = app_handle.emit(EVT_INGEST_PROGRESS, &payload) {
        log::warn!("IngestWorker: emit progress failed: {}", e);
    }
}

async fn emit_queue_update(app_handle: &AppHandle, queue: &IngestQueue, doc_id: &str, stage: &str) {
    let stats: QueueStats = match queue.stats().await {
        Ok(s) => s,
        Err(e) => {
            log::warn!("IngestWorker: stats failed: {}", e);
            return;
        }
    };
    let payload = serde_json::json!({
        "doc_id": doc_id,
        "stage": stage,
        "stats": stats,
    });
    if let Err(e) = app_handle.emit(EVT_INGEST_QUEUE_UPDATE, &payload) {
        log::warn!("IngestWorker: emit queue update failed: {}", e);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    #[tokio::test]
    async fn test_preflight_check_ok() {
        let tmp = tempfile::TempDir::new().unwrap();
        let pdf = tmp.path().join("source.pdf");
        let mut f = std::fs::File::create(&pdf).unwrap();
        f.write_all(b"%PDF-1.4").unwrap();
        drop(f);

        let result = preflight_check("inspector", &pdf, tmp.path()).await;
        assert!(
            result.is_ok(),
            "preflight should pass for valid paths: {:?}",
            result
        );
    }

    #[tokio::test]
    async fn test_preflight_check_missing_file() {
        let tmp = tempfile::TempDir::new().unwrap();
        let missing = tmp.path().join("missing.pdf");

        let result = preflight_check("inspector", &missing, tmp.path()).await;
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("source file not found"));
    }
}
