//! Pipeline runner and Stage trait.

use crate::pipeline::context::{PipelineContext, PipelineEvent};
use crate::pipeline::error::PipelineError;
use crate::pipeline::models::persisted::IndexedDocument;
use crate::pipeline::models::source::SourceInput;
use crate::pipeline::services::ocr::OcrService;
use crate::pipeline::stages::enrich::EnrichStage;
use crate::pipeline::stages::extract::ExtractStage;
use crate::pipeline::stages::index::IndexStage;
use crate::pipeline::stages::persist::PersistStage;
use crate::pipeline::stages::segment::SegmentStage;

/// A single progress log message produced by a pipeline stage.
#[derive(Debug, Clone)]
pub struct StageLog {
    /// Human-readable progress message.
    pub message: String,
}

/// The successful outcome of running a pipeline stage.
pub struct StageOutcome<T> {
    /// Output value produced by the stage.
    pub output: T,
    /// Progress logs collected during execution.
    pub logs: Vec<StageLog>,
    /// Non-fatal warnings collected during execution.
    pub warnings: Vec<String>,
}

impl<T> StageOutcome<T> {
    /// Creates a new outcome wrapping the given output.
    pub fn new(output: T) -> Self {
        Self {
            output,
            logs: Vec::new(),
            warnings: Vec::new(),
        }
    }

    /// Adds a progress log entry to this outcome.
    #[must_use]
    pub fn with_log(mut self, message: impl Into<String>) -> Self {
        self.logs.push(StageLog {
            message: message.into(),
        });
        self
    }

    /// Adds a non-fatal warning to this outcome.
    #[must_use]
    pub fn with_warning(mut self, message: impl Into<String>) -> Self {
        self.warnings.push(message.into());
        self
    }
}

/// Trait implemented by all pipeline stages.
#[async_trait::async_trait]
pub trait Stage<Input, Output>: Send + Sync {
    /// Executes the stage on `input` using the shared pipeline context.
    async fn run(
        &self,
        input: Input,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<Output>, PipelineError>;
}

/// Runner that orchestrates individual pipeline stages and emits lifecycle events.
pub struct PipelineRunner;

impl PipelineRunner {
    /// Creates a new `PipelineRunner`.
    #[must_use]
    pub fn new() -> Self {
        Self
    }

    /// Runs a single stage, emitting lifecycle events and returning its output.
    pub async fn run_stage<S, I, O>(
        &self,
        name: &str,
        stage: &S,
        input: I,
        ctx: &PipelineContext,
    ) -> Result<O, PipelineError>
    where
        S: Stage<I, O>,
    {
        let stage_name = name.to_string();
        ctx.reporter.report(PipelineEvent::StageStart {
            stage: stage_name.clone(),
        });

        let result = stage.run(input, ctx).await;
        let mut outcome = match result {
            Ok(o) => o,
            Err(e) => {
                ctx.reporter.report(PipelineEvent::StageFailed {
                    stage: stage_name.clone(),
                    error: e.to_string(),
                });
                return Err(e);
            }
        };
        for log in outcome.logs.drain(..) {
            ctx.reporter.report(PipelineEvent::StageProgress {
                stage: stage_name.clone(),
                message: log.message,
            });
        }

        for warning in outcome.warnings.drain(..) {
            ctx.reporter.report(PipelineEvent::StageWarning {
                stage: stage_name.clone(),
                message: warning,
            });
        }

        ctx.reporter
            .report(PipelineEvent::StageComplete { stage: stage_name });

        Ok(outcome.output)
    }
}

impl Default for PipelineRunner {
    fn default() -> Self {
        Self::new()
    }
}

/// Runs the full Extract → Segment → Enrich → Persist → Index pipeline.
pub async fn run_pipeline(
    input: SourceInput,
    ctx: &PipelineContext,
) -> Result<IndexedDocument, PipelineError> {
    let runner = PipelineRunner::new();

    let ocr = OcrService::new(crate::pipeline::services::ocr::default_backends());
    let extract_stage = ExtractStage::new(ocr);
    let extracted = runner
        .run_stage("extract", &extract_stage, input, ctx)
        .await?;

    let segment_stage = SegmentStage::new(ctx.config.chunk_max_chars);
    let segmented = runner
        .run_stage("segment", &segment_stage, extracted.clone(), ctx)
        .await?;

    let sidecar_url = mbforge_infra::config::constants::sidecar_url();
    let enrich_stage = EnrichStage::new(sidecar_url);
    let enriched = runner
        .run_stage("enrich", &enrich_stage, (extracted.clone(), segmented), ctx)
        .await?;

    let persist_stage = PersistStage::new();
    let persisted = runner
        .run_stage("persist", &persist_stage, (extracted, enriched), ctx)
        .await?;

    let index_stage = IndexStage::new();
    let indexed = runner
        .run_stage("index", &index_stage, persisted, ctx)
        .await?;

    Ok(indexed)
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use crate::pipeline::context::{CollectingReporter, PipelineContext};

    use super::*;

    struct DoubleStage;

    #[async_trait::async_trait]
    impl Stage<i32, i32> for DoubleStage {
        async fn run(
            &self,
            input: i32,
            _ctx: &PipelineContext,
        ) -> Result<StageOutcome<i32>, PipelineError> {
            Ok(StageOutcome::new(input * 2))
        }
    }

    struct WarningStage;

    #[async_trait::async_trait]
    impl Stage<(), ()> for WarningStage {
        async fn run(
            &self,
            _input: (),
            _ctx: &PipelineContext,
        ) -> Result<StageOutcome<()>, PipelineError> {
            Ok(StageOutcome::new(()).with_warning("something"))
        }
    }

    struct LoggingStage;

    #[async_trait::async_trait]
    impl Stage<(), ()> for LoggingStage {
        async fn run(
            &self,
            _input: (),
            _ctx: &PipelineContext,
        ) -> Result<StageOutcome<()>, PipelineError> {
            Ok(StageOutcome::new(()).with_log("progress message"))
        }
    }

    #[tokio::test]
    async fn runner_executes_stage_and_emits_events() {
        let reporter = Arc::new(CollectingReporter::new());
        let ctx = PipelineContext::new("/tmp/test.pdf", "").with_reporter(reporter.clone());
        let runner = PipelineRunner::new();
        let result = runner
            .run_stage("double", &DoubleStage, 21, &ctx)
            .await
            .unwrap();
        assert_eq!(result, 42);

        let events = reporter.events.lock().unwrap();
        assert!(events
            .iter()
            .any(|e| matches!(e, PipelineEvent::StageStart { stage } if stage == "double")));
        assert!(events
            .iter()
            .any(|e| matches!(e, PipelineEvent::StageComplete { stage } if stage == "double")));
    }

    #[tokio::test]
    async fn runner_emits_warning_events() {
        let reporter = Arc::new(CollectingReporter::new());
        let ctx = PipelineContext::new("/tmp/test.pdf", "").with_reporter(reporter.clone());
        let runner = PipelineRunner::new();
        let result = runner
            .run_stage("warn", &WarningStage, (), &ctx)
            .await
            .unwrap();
        assert_eq!(result, ());

        let events = reporter.events.lock().unwrap();
        assert!(events.iter().any(|e| matches!(
            e,
            PipelineEvent::StageWarning { stage, message }
            if stage == "warn" && message == "something"
        )));
    }

    #[tokio::test]
    async fn runner_forwards_logs_as_stage_progress() {
        let reporter = Arc::new(CollectingReporter::new());
        let ctx = PipelineContext::new("/tmp/test.pdf", "").with_reporter(reporter.clone());
        let runner = PipelineRunner::new();
        runner
            .run_stage("logging", &LoggingStage, (), &ctx)
            .await
            .unwrap();

        let events = reporter.events.lock().unwrap();
        assert!(events.iter().any(|e| matches!(
            e,
            PipelineEvent::StageProgress { stage, message }
            if stage == "logging" && message == "progress message"
        )));
    }
}
