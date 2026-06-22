//! Tauri command entry point for the v2 PDF processing pipeline.

use std::sync::Arc;

use tauri::{AppHandle, Emitter};

use crate::core::constants::EVT_DOC_PROGRESS;
use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent, PipelineReporter};
use crate::parsers::pipeline_v2::models::source::SourceInput;
use crate::parsers::pipeline_v2::runner::run_pipeline;

/// Processes a PDF document through the new Extract → Segment → Enrich → Persist → Index pipeline.
#[tauri::command]
pub async fn process_document_v2(
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
