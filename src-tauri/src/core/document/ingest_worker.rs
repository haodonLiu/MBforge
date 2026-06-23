//! Ingest queue background worker.
//!
//! 一个项目内只启动一个 worker，循环从 `IngestQueue` 取出任务并按阶段处理。
//! 阶段包括：inspector → text_extract/ocr → moldet → index。

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{AppHandle, Emitter};

use crate::core::constants::{
    EVT_INGEST_LOG, EVT_INGEST_PROGRESS, EVT_INGEST_QUEUE_UPDATE, EVT_INGEST_WORKER_HEARTBEAT,
    EVT_OCR_API_MISSING,
};
use crate::core::document::ingest_queue::{IngestQueue, IngestTask};
use crate::core::project::document_project::DocumentProject;
use crate::core::project::project::Project;
use crate::parsers::pdf::context::{PdfClassification, PdfInspectorContext};
use crate::parsers::pipeline::legacy::{
    classify_and_extract_from_context_with_path, quick_moldet_scan_pdf, ExtractProgressReporter,
};
use crate::parsers::pipeline::{
    context::PipelineContext, models::source::SourceInput, runner::run_pipeline,
};

const WORKER_HEARTBEAT_INTERVAL_SECS: u64 = 5;

/// App state that holds the active ingest worker.
#[derive(Default)]
pub struct IngestWorkerState {
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
        let last_heartbeat = Arc::new(AtomicU64::new(crate::core::helpers::now_secs_u64()));
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
        Ok(q) => q,
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

        let stage_started_at = crate::core::helpers::now_secs_f64();
        let stage_hist_id = queue
            .record_stage_start(&task.id, &task.doc_id, &task.stage)
            .await
            .ok();

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
            &app_handle,
            &task.doc_id,
            &task.stage,
            "info",
            format!("进入 {} 阶段 (task id={})", task.stage, task.id),
        );
        let result = match task.stage.as_str() {
            "inspector" => process_inspector(&project_root, &queue, &task, &app_handle).await,
            "text_extract" => process_text_extract(&project_root, &queue, &task, &app_handle).await,
            "ocr" => process_ocr(&project_root, &queue, &task, &app_handle).await,
            "moldet" => process_moldet(&project_root, &queue, &task, &app_handle).await,
            "index" => process_index(&project_root, &queue, &task, &app_handle).await,
            other => Err(format!("Unknown stage: {}", other)),
        };

        let stage_duration_secs = crate::core::helpers::now_secs_f64() - stage_started_at;
        let stage_dur_str = format!("{:.2}s", stage_duration_secs);
        match result {
            Ok(StageResult::Continue(next_stage)) => {
                if let Some(id) = stage_hist_id {
                    let _ = queue.record_stage_end(id, stage_duration_secs, true).await;
                }
                emit_log(
                    &app_handle,
                    &task.doc_id,
                    &task.stage,
                    "info",
                    format!(
                        "{} 阶段完成 ({}), 下一阶段: {}",
                        task.stage, stage_dur_str, next_stage
                    ),
                );
                // 阶段完成，切到下一阶段并重新置为 pending，让下一轮继续处理。
                if let Err(e) = queue
                    .update_progress(&task.id, &next_stage, 0.0, 0, 0, "")
                    .await
                {
                    log::error!("IngestWorker: failed to advance stage: {}", e);
                }
                // 把状态改回 pending 以便 dequeue 能再次取到同一任务。
                let _ = reset_pending(&queue, &task.id).await;
                emit_queue_update(&app_handle, &queue, &task.doc_id, &next_stage).await;
            }
            Ok(StageResult::Done) => {
                if let Some(id) = stage_hist_id {
                    let _ = queue.record_stage_end(id, stage_duration_secs, true).await;
                }
                if let Err(e) = queue.mark_done(&task.id).await {
                    log::error!("IngestWorker: mark_done failed: {}", e);
                }
                emit_queue_update(&app_handle, &queue, &task.doc_id, "done").await;
            }
            Err(e) => {
                if let Some(id) = stage_hist_id {
                    let _ = queue.record_stage_end(id, stage_duration_secs, false).await;
                }
                log::error!(
                    "IngestWorker: task {} stage {} failed: {}",
                    task.id,
                    task.stage,
                    e
                );
                emit_log(
                    &app_handle,
                    &task.doc_id,
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

/// 阶段处理结果。
enum StageResult {
    /// 继续下一阶段。
    Continue(String),
    /// 任务全部完成。
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
            let now = crate::core::helpers::now_secs_u64();
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
    match crate::core::helpers::available_space_bytes(project_root) {
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

    let index_dir = project_root.join(crate::core::constants::INDEX_DIR);
    if let Err(e) = std::fs::create_dir_all(&index_dir) {
        return Err(format!("无法创建 index 目录: {}", e));
    }
    let probe = index_dir.join(".write_probe");
    if let Err(e) = std::fs::write(&probe, b"1") {
        return Err(format!("index 目录不可写: {}", e));
    }
    let _ = std::fs::remove_file(&probe);

    if stage == "moldet" || stage == "index" {
        let client = crate::core::sidecar_client::get_or_init()
            .map_err(|e| format!("Sidecar client init failed: {}", e))?;
        if let Err(e) = client.health().await {
            return Err(format!("Sidecar 未就绪: {}", e));
        }
    }

    Ok(())
}

/// Try to load a `PdfInspectorContext` from cached `inspector.json` + `text.md`.
/// Returns `None` if the cache is missing or unreadable so callers can fall back.
async fn try_load_cached_context(
    inspector_path: &std::path::Path,
    text_path: &std::path::Path,
) -> Option<PdfInspectorContext> {
    if !inspector_path.exists() || !text_path.exists() {
        return None;
    }

    let content = match tokio::fs::read_to_string(inspector_path).await {
        Ok(c) => c,
        Err(e) => {
            log::warn!(
                "IngestWorker: failed to read inspector.json, falling back to PDF parse: {}",
                e
            );
            return None;
        }
    };
    let cached: serde_json::Value = match serde_json::from_str(&content) {
        Ok(v) => v,
        Err(e) => {
            log::warn!(
                "IngestWorker: failed to parse inspector.json, falling back to PDF parse: {}",
                e
            );
            return None;
        }
    };
    let classification: PdfClassification = match serde_json::from_value(cached.clone()) {
        Ok(c) => c,
        Err(e) => {
            log::warn!(
                "IngestWorker: failed to deserialize classification, falling back to PDF parse: {}",
                e
            );
            return None;
        }
    };
    let markdown = match tokio::fs::read_to_string(text_path).await {
        Ok(m) => m,
        Err(e) => {
            log::warn!(
                "IngestWorker: failed to read text.md, falling back to PDF parse: {}",
                e
            );
            return None;
        }
    };

    let page_count = cached["page_count"].as_u64().unwrap_or(0) as usize;
    let pages_needing_ocr: Vec<usize> = cached["pages_needing_ocr"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_u64().map(|n| n as usize))
                .collect()
        })
        .unwrap_or_default();

    Some(PdfInspectorContext::from_cached(
        classification,
        markdown,
        page_count,
        pages_needing_ocr,
    ))
}

/// Load a PdfInspectorContext from cached inspector.json + text.md.
/// Falls back to building from the original path if cache is missing or corrupt.
async fn load_cached_or_build_context(
    project_root: &std::path::Path,
    task: &IngestTask,
) -> Result<PdfInspectorContext, String> {
    let dp = DocumentProject::load(project_root, &task.doc_id)
        .ok_or_else(|| "DocumentProject not found".to_string())?;
    let paths = dp.paths();

    let inspector_path = paths.cache_dir.join("inspector.json");
    let text_path = paths.pages_cache_dir.join("text.md");

    if let Some(ctx) = try_load_cached_context(&inspector_path, &text_path).await {
        return Ok(ctx);
    }

    // Fallback: build from path (loads PDF once).
    PdfInspectorContext::from_path(&task.file_path).await
}

async fn process_inspector(
    project_root: &Path,
    queue: &IngestQueue,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    preflight_check("inspector", Path::new(&task.file_path), project_root).await?;

    let ctx = PdfInspectorContext::from_path(&task.file_path).await?;

    let pdf_type_str = match ctx.classification.pdf_type {
        pdf_inspector::PdfType::TextBased => "TextBased",
        pdf_inspector::PdfType::Scanned => "Scanned",
        pdf_inspector::PdfType::Mixed => "Mixed",
        pdf_inspector::PdfType::ImageBased => "ImageBased",
    };

    // 持久化 inspector 结果到 DocumentProject cache。
    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        let paths = dp.paths();
        if let Err(e) = std::fs::create_dir_all(&paths.cache_dir) {
            log::warn!("IngestWorker: failed to create cache directory: {}", e);
        }
        let inspector_json = serde_json::json!({
            "pdf_type": pdf_type_str,
            "confidence": ctx.classification.confidence,
            "page_count": ctx.page_count,
            "pages_needing_ocr": ctx.pages_needing_ocr,
            "has_complex_layout": ctx.classification.has_complex_layout,
            "has_encoding_issues": ctx.classification.has_encoding_issues,
            "title": ctx.classification.title,
            "inspected_at": chrono::Utc::now().to_rfc3339(),
        });
        let inspector_path = paths.cache_dir.join("inspector.json");
        let _ = crate::core::helpers::save_json(&inspector_path, &inspector_json);

        // Persist markdown so later stages can reuse the context without reloading the PDF.
        if let Err(e) = std::fs::create_dir_all(&paths.pages_cache_dir) {
            log::warn!(
                "IngestWorker: failed to create pages cache directory: {}",
                e
            );
        }
        let text_path = paths.pages_cache_dir.join("text.md");
        if let Err(e) = std::fs::write(&text_path, &ctx.markdown) {
            log::warn!(
                "IngestWorker: failed to write text.md in inspector stage: {}",
                e
            );
        }

        dp.set_inspector_status(pdf_type_str.to_lowercase().as_str());
        dp.set_text_status("pending");
        match ctx.classification.pdf_type {
            pdf_inspector::PdfType::TextBased => dp.set_ocr_status("not_needed"),
            _ => dp.set_ocr_status("pending_confirmation"),
        }
    }

    // 同步更新项目 index。
    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(
            &task.doc_id,
            "inspector_status",
            &pdf_type_str.to_lowercase(),
        );
        let ocr_status = match ctx.classification.pdf_type {
            pdf_inspector::PdfType::TextBased => "not_needed",
            _ => "pending_confirmation",
        };
        proj.set_document_status(&task.doc_id, "ocr_status", ocr_status);
    }

    let next_stage = match ctx.classification.pdf_type {
        pdf_inspector::PdfType::TextBased => "text_extract",
        _ => "ocr",
    };

    queue
        .update_progress(
            &task.id,
            &task.stage,
            100.0,
            ctx.page_count as i32,
            ctx.page_count as i32,
            &format!("detected {}", pdf_type_str),
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;

    emit_progress(
        app_handle,
        task,
        &task.stage,
        100.0,
        ctx.page_count as i32,
        ctx.page_count as i32,
        &format!("detected {}", pdf_type_str),
    );

    log::info!(
        "IngestWorker: inspector done doc_id={} type={} next={}",
        task.doc_id,
        pdf_type_str,
        next_stage
    );

    Ok(StageResult::Continue(next_stage.to_string()))
}

/// 把 `classify_and_extract` 内部的子步骤消息转发到前端日志面板与进度事件。
struct IngestProgressReporter<'a> {
    app_handle: &'a AppHandle,
    doc_id: &'a str,
    stage: &'a str,
}

impl ExtractProgressReporter for IngestProgressReporter<'_> {
    fn report(&self, message: &str) {
        emit_log(
            self.app_handle,
            self.doc_id,
            self.stage,
            "info",
            message.to_string(),
        );
    }
}

async fn process_text_extract(
    project_root: &Path,
    queue: &IngestQueue,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    preflight_check("text_extract", Path::new(&task.file_path), project_root).await?;

    queue
        .update_progress(&task.id, &task.stage, 10.0, 0, 0, "extracting text")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(app_handle, task, &task.stage, 10.0, 0, 0, "extracting text");
    emit_log(
        app_handle,
        &task.doc_id,
        &task.stage,
        "info",
        "开始文本提取".to_string(),
    );

    let ctx = load_cached_or_build_context(project_root, task).await?;
    let classified =
        classify_and_extract_from_context_with_path(&ctx, &task.file_path, false, None)
            .await
            .map_err(|e| format!("text extraction failed: {}", e))?;

    // 保存文本到 cache/pages/text.md。
    if let Some(dp) = DocumentProject::load(project_root, &task.doc_id) {
        let paths = dp.paths();
        let _ = std::fs::create_dir_all(&paths.pages_cache_dir);
        let text_path = paths.pages_cache_dir.join("text.md");
        if let Err(e) = std::fs::write(&text_path, &classified.text) {
            log::warn!("IngestWorker: failed to write text.md: {}", e);
        } else {
            emit_log(
                app_handle,
                &task.doc_id,
                &task.stage,
                "info",
                "文本已保存到 cache/pages/text.md".to_string(),
            );
        }
    }

    // 更新状态。
    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        dp.set_text_status("done");
    }
    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(&task.doc_id, "text_status", "done");
    }

    let progress_pct = 100.0;
    queue
        .update_progress(
            &task.id,
            &task.stage,
            progress_pct,
            classified.page_count as i32,
            classified.page_count as i32,
            "text extracted",
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        progress_pct,
        classified.page_count as i32,
        classified.page_count as i32,
        "text extracted",
    );

    log::info!(
        "IngestWorker: text_extract done doc_id={} pages={}",
        task.doc_id,
        classified.page_count
    );

    let config = crate::core::config::settings::AppConfig::load();
    let next = if config.moldet.auto_moldet_on_import {
        "moldet"
    } else {
        "index"
    };
    Ok(StageResult::Continue(next.to_string()))
}

async fn process_ocr(
    project_root: &Path,
    queue: &IngestQueue,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    preflight_check("ocr", Path::new(&task.file_path), project_root).await?;

    queue
        .update_progress(&task.id, &task.stage, 10.0, 0, 0, "running OCR")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(app_handle, task, &task.stage, 10.0, 0, 0, "running OCR");
    emit_log(
        app_handle,
        &task.doc_id,
        &task.stage,
        "info",
        "OCR 预检通过，准备解析 PDF".to_string(),
    );

    // Reuse the inspector context so the PDF is not loaded again.
    let ctx = load_cached_or_build_context(project_root, task).await?;

    // Pre-flight: if no online OCR API is configured for this scan, notify the
    // user via modal before extraction logs and silently skips. Only
    // emit when the PDF actually needs OCR (scanned) — text-based PDFs are
    // handled by pdf_inspector without any OCR backend.
    let is_scanned =
        (ctx.markdown.len() < 100 && ctx.page_count > 0) || !ctx.pages_needing_ocr.is_empty();

    if is_scanned {
        emit_log(
            app_handle,
            &task.doc_id,
            &task.stage,
            "info",
            format!("检测到扫描件（共 {} 页），将尝试 OCR", ctx.page_count),
        );
        queue
            .update_progress(&task.id, &task.stage, 20.0, 0, 0, "scanned PDF detected")
            .await
            .map_err(|e| format!("update progress failed: {}", e))?;
        emit_progress(
            app_handle,
            task,
            &task.stage,
            20.0,
            0,
            0,
            "scanned PDF detected",
        );

        for backend in [
            ("mineru", crate::parsers::ocr::mineru::is_available()),
            ("uniparser", crate::parsers::ocr::uniparser::is_available()),
            (
                "paddleocr-online",
                crate::parsers::ocr::paddle::online_is_available(),
            ),
        ] {
            if !backend.1 {
                let payload = serde_json::json!({
                    "backend": backend.0,
                    "doc_id": task.doc_id,
                    "file_path": task.file_path,
                });
                log::warn!(
                    "OCR backend '{}' unavailable for doc_id={} (env var not set)",
                    backend.0,
                    task.doc_id
                );
                if let Err(e) = app_handle.emit(EVT_OCR_API_MISSING, &payload) {
                    log::warn!("Failed to emit {}: {}", EVT_OCR_API_MISSING, e);
                }
            }
        }
    } else {
        emit_log(
            app_handle,
            &task.doc_id,
            &task.stage,
            "info",
            "PDF 为文本型，将直接提取文本".to_string(),
        );
    }

    queue
        .update_progress(&task.id, &task.stage, 30.0, 0, 0, " invoking OCR backend")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        30.0,
        0,
        0,
        " invoking OCR backend",
    );

    let reporter = IngestProgressReporter {
        app_handle,
        doc_id: &task.doc_id,
        stage: &task.stage,
    };
    let classified =
        classify_and_extract_from_context_with_path(&ctx, &task.file_path, true, Some(&reporter))
            .await
            .map_err(|e| format!("OCR extraction failed: {}", e))?;

    queue
        .update_progress(
            &task.id,
            &task.stage,
            50.0,
            classified.page_count as i32,
            classified.page_count as i32,
            &format!("OCR result ready ({})", classified.parser),
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        50.0,
        classified.page_count as i32,
        classified.page_count as i32,
        &format!("OCR result ready ({})", classified.parser),
    );
    emit_log(
        app_handle,
        &task.doc_id,
        &task.stage,
        "info",
        format!(
            "OCR 结果已生成（parser={}，pages={}）",
            classified.parser, classified.page_count
        ),
    );

    // 保存 OCR 结果到 cache/ocr/ocr.json。
    if let Some(dp) = DocumentProject::load(project_root, &task.doc_id) {
        let paths = dp.paths();
        let _ = std::fs::create_dir_all(&paths.ocr_cache_dir);
        let ocr_path = paths.ocr_cache_dir.join("ocr.json");
        let ocr_json = serde_json::json!({
            "text": classified.text,
            "page_count": classified.page_count,
            "parser": classified.parser,
            "ocr_blocks": classified.ocr_blocks,
            "images": classified.images,
        });
        if let Err(e) = crate::core::helpers::save_json(&ocr_path, &ocr_json) {
            log::warn!("IngestWorker: failed to save ocr.json: {}", e);
        } else {
            emit_log(
                app_handle,
                &task.doc_id,
                &task.stage,
                "info",
                "OCR 结果已保存到 cache/ocr/ocr.json".to_string(),
            );
        }
    }

    queue
        .update_progress(
            &task.id,
            &task.stage,
            80.0,
            classified.page_count as i32,
            classified.page_count as i32,
            "OCR result saved",
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        80.0,
        classified.page_count as i32,
        classified.page_count as i32,
        "OCR result saved",
    );

    // 更新状态。
    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        dp.set_ocr_status("done");
    }
    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(&task.doc_id, "ocr_status", "done");
    }

    let progress_pct = 100.0;
    queue
        .update_progress(
            &task.id,
            &task.stage,
            progress_pct,
            classified.page_count as i32,
            classified.page_count as i32,
            "OCR done",
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        progress_pct,
        classified.page_count as i32,
        classified.page_count as i32,
        "OCR done",
    );

    log::info!(
        "IngestWorker: ocr done doc_id={} pages={}",
        task.doc_id,
        classified.page_count
    );

    let config = crate::core::config::settings::AppConfig::load();
    let next = if config.moldet.auto_moldet_on_import {
        "moldet"
    } else {
        "index"
    };
    Ok(StageResult::Continue(next.to_string()))
}

async fn process_moldet(
    project_root: &Path,
    queue: &IngestQueue,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    preflight_check("moldet", Path::new(&task.file_path), project_root).await?;

    queue
        .update_progress(&task.id, &task.stage, 10.0, 0, 0, "scanning molecules")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        10.0,
        0,
        0,
        "scanning molecules",
    );

    let sidecar_url = crate::core::constants::sidecar_url();
    let config = crate::core::config::settings::AppConfig::load();
    let batch_size = config.moldet.moldet_batch_size.max(1);
    let result = quick_moldet_scan_pdf(
        &task.file_path,
        project_root,
        &sidecar_url,
        &task.doc_id,
        batch_size,
    )
    .await
    .map_err(|e| format!("MoldDet scan failed: {}", e))?;

    let status = if result.pages_with_molecules.is_empty() {
        "no_molecule"
    } else {
        "has_molecule"
    };

    // 更新 DocumentProject / Project index。
    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        dp.set_moldet_status(status, &result.pages_with_molecules);
    }
    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(&task.doc_id, "moldet_status", status);
    }

    let progress_pct = 100.0;
    queue
        .update_progress(
            &task.id,
            &task.stage,
            progress_pct,
            result.page_count as i32,
            result.page_count as i32,
            &format!("moldet {}", status),
        )
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        progress_pct,
        result.page_count as i32,
        result.page_count as i32,
        &format!("moldet {}", status),
    );

    log::info!(
        "IngestWorker: moldet done doc_id={} status={} molecule_pages={:?}",
        task.doc_id,
        status,
        result.pages_with_molecules
    );

    Ok(StageResult::Continue("index".to_string()))
}

async fn process_index(
    project_root: &Path,
    queue: &IngestQueue,
    task: &IngestTask,
    app_handle: &AppHandle,
) -> Result<StageResult, String> {
    preflight_check("index", Path::new(&task.file_path), project_root).await?;

    queue
        .update_progress(&task.id, &task.stage, 10.0, 0, 0, "extracting for index")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        10.0,
        0,
        0,
        "extracting for index",
    );

    let input = SourceInput::new(&task.file_path).with_allow_ocr(true);
    let mut ctx = PipelineContext::new(&task.file_path, "");
    ctx = ctx.with_project_root(project_root);

    queue
        .update_progress(&task.id, &task.stage, 40.0, 0, 0, "running v2 pipeline")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        40.0,
        0,
        0,
        "running v2 pipeline",
    );

    let indexed = run_pipeline(input, &ctx)
        .await
        .map_err(|e| format!("v2 pipeline failed: {}", e))?;

    queue
        .update_progress(&task.id, &task.stage, 70.0, 0, 0, "v2 pipeline complete")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(
        app_handle,
        task,
        &task.stage,
        70.0,
        0,
        0,
        "v2 pipeline complete",
    );

    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        dp.set_index_status("done");
    }
    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(&task.doc_id, "index_status", "done");
    }

    queue
        .update_progress(&task.id, &task.stage, 100.0, 0, 0, "indexed")
        .await
        .map_err(|e| format!("update progress failed: {}", e))?;
    emit_progress(app_handle, task, &task.stage, 100.0, 0, 0, "indexed");

    log::info!(
        "IngestWorker: index done doc_id={} indexed_sections={}",
        task.doc_id,
        indexed.indexed_sections,
    );

    Ok(StageResult::Done)
}

/// 把任务状态重置为 pending（用于阶段切换后继续处理）。
async fn reset_pending(queue: &IngestQueue, task_id: &str) -> Result<(), String> {
    queue
        .set_pending(task_id)
        .await
        .map_err(|e| format!("reset pending failed: {}", e))
}

/// 阶段失败时，把对应 DocumentProject 状态标记为 error。
fn set_doc_status_error(project_root: &Path, task: &IngestTask, error: &str) {
    let field = match task.stage.as_str() {
        "inspector" => "inspector_status",
        "text_extract" => "text_status",
        "ocr" => "ocr_status",
        "moldet" => "moldet_status",
        "index" => "index_status",
        _ => return,
    };

    if let Some(mut dp) = DocumentProject::load(project_root, &task.doc_id) {
        match task.stage.as_str() {
            "inspector" => dp.set_inspector_status("error"),
            "text_extract" => dp.set_text_status("error"),
            "ocr" => dp.set_ocr_status("error"),
            "moldet" => dp.set_moldet_status("error", &[]),
            "index" => dp.set_index_status("error"),
            _ => {}
        }
    }

    if let Some(mut proj) = Project::open(project_root) {
        proj.set_document_status(&task.doc_id, field, "error");
    }

    log::warn!(
        "IngestWorker: marked doc_id={} {} as error: {}",
        task.doc_id,
        field,
        error
    );
}

/// Structured log line for the frontend log panel. Mirrors the same
/// info into stderr via `log::` and emits a Tauri event so the UI can
/// render a per-task expandable log box.
fn emit_log(app_handle: &AppHandle, doc_id: &str, stage: &str, level: &str, message: String) {
    let payload = serde_json::json!({
        "doc_id": doc_id,
        "stage": stage,
        "level": level,
        "message": message,
        "ts_ms": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0),
    });
    // Mirror to stderr so devs can grep the Tauri log.
    match level {
        "warn" => log::warn!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
        "error" => log::error!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
        _ => log::info!("[IngestWorker:{}:{}] {}", doc_id, stage, message),
    }
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
    let stats = match queue.stats().await {
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
