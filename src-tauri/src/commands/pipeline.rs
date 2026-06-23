//! Tauri command entry point for the v2 PDF processing pipeline.

use std::path::PathBuf;
use std::sync::Arc;

use tauri::{AppHandle, Emitter};

use crate::core::constants::EVT_DOC_PROGRESS;
use crate::core::project::Project;
use crate::parsers::pipeline::context::{PipelineContext, PipelineEvent, PipelineReporter};
use crate::parsers::pipeline::models::source::SourceInput;
use crate::parsers::pipeline::runner::run_pipeline;

/// Processes a PDF document through the new Extract → Segment → Enrich → Persist → Index pipeline.
#[tauri::command]
pub async fn process_document(
    path: String,
    user_request: Option<String>,
    project_root: Option<String>,
    app: AppHandle,
) -> Result<(), String> {
    let input = SourceInput::new(&path).with_allow_ocr(true);

    let mut ctx = PipelineContext::new(&path, user_request.unwrap_or_default());
    if let Some(root) = project_root {
        ctx = ctx.with_project_root(&root);
    }

    let reporter = Arc::new(TauriReporter { app });
    ctx = ctx.with_reporter(reporter);

    run_pipeline(input, &ctx)
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())
}

/// Indexes all PDF documents in a project by running the pipeline for each one.
#[tauri::command]
pub async fn index_project(project_root: String, app: AppHandle) -> Result<String, String> {
    let root = PathBuf::from(&project_root);
    let project = Project::open(&root)
        .ok_or_else(|| format!("项目不存在: {project_root}"))?;

    let docs: Vec<_> = project
        .list_documents()
        .iter()
        .filter(|d| d.doc_type == "pdf")
        .cloned()
        .collect();

    let reporter = Arc::new(TauriReporter { app });
    let mut processed = 0usize;

    for doc in docs {
        let Some(source_path) = project.get_document_source_path(&doc.doc_id) else {
            log::warn!("未找到文档 source_path: {}", doc.doc_id);
            continue;
        };

        reporter.report(PipelineEvent::StageStart {
            stage: format!("index_project: {}", doc.doc_id),
        });

        let input = SourceInput::new(&source_path)
            .with_allow_ocr(true)
            .with_project_root(&project_root);

        let ctx = PipelineContext::new(&source_path, "")
            .with_project_root(&project_root)
            .with_reporter(reporter.clone());

        match run_pipeline(input, &ctx).await {
            Ok(_) => {
                processed += 1;
                reporter.report(PipelineEvent::StageComplete {
                    stage: format!("index_project: {}", doc.doc_id),
                });
            }
            Err(e) => {
                log::error!("处理文档失败 {}: {}", doc.doc_id, e);
                reporter.report(PipelineEvent::StageWarning {
                    stage: format!("index_project: {}", doc.doc_id),
                    message: e.to_string(),
                });
            }
        }
    }

    Ok(format!("indexed {processed} documents"))
}

/// Reports pipeline events as Tauri window events on `EVT_DOC_PROGRESS`.
struct TauriReporter {
    app: AppHandle,
}

impl PipelineReporter for TauriReporter {
    fn report(&self, event: PipelineEvent) {
        let payload = match event {
            PipelineEvent::StageStart { stage } => DocProgressEvent::Classify {
                parser: stage,
                page_count: 0,
            },
            PipelineEvent::StageProgress { stage, message } => DocProgressEvent::Section {
                name: stage,
                status: message,
                compounds: 0,
                activities: 0,
            },
            PipelineEvent::StageComplete { stage } => DocProgressEvent::Section {
                name: stage,
                status: "complete".into(),
                compounds: 0,
                activities: 0,
            },
            PipelineEvent::StageWarning { stage, message } => {
                DocProgressEvent::Error { stage, message }
            }
        };
        let _ = self.app.emit(EVT_DOC_PROGRESS, payload);
    }
}

/// Frontend-facing progress event payload.
#[derive(serde::Serialize, Clone)]
#[serde(tag = "stage", content = "payload")]
enum DocProgressEvent {
    #[serde(rename = "classify")]
    Classify { parser: String, page_count: usize },
    #[serde(rename = "section")]
    Section {
        name: String,
        status: String,
        compounds: usize,
        activities: usize,
    },
    #[serde(rename = "error")]
    Error { stage: String, message: String },
}
