//! Pipeline execution context.

use std::path::{Path, PathBuf};
use std::sync::Arc;

/// Configuration options controlling PDF pipeline behavior.
#[derive(Debug, Clone)]
pub struct PipelineConfig {
    /// Whether OCR backends may be invoked when text extraction fails.
    pub allow_ocr: bool,
    /// Maximum number of characters per document chunk.
    pub chunk_max_chars: usize,
    /// Max number of sections processed concurrently.
    pub section_concurrency: usize,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            allow_ocr: true,
            chunk_max_chars: 8000,
            section_concurrency: 4,
        }
    }
}

/// Shared, immutable context passed through every pipeline stage.
#[derive(Clone)]
pub struct PipelineContext {
    /// Absolute path to the source PDF being processed.
    pub source_path: PathBuf,
    /// Optional project root directory used for resolving relative paths.
    pub project_root: Option<PathBuf>,
    /// Free-text description of the user's extraction goal.
    pub user_request: String,
    /// Reporter used to emit progress and warning events.
    pub reporter: Arc<dyn PipelineReporter>,
    /// Pipeline behavior configuration.
    pub config: PipelineConfig,
}

impl std::fmt::Debug for PipelineContext {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PipelineContext")
            .field("source_path", &self.source_path)
            .field("project_root", &self.project_root)
            .field("user_request", &self.user_request)
            .field("reporter", &"Arc<dyn PipelineReporter>")
            .field("config", &self.config)
            .finish()
    }
}

impl PipelineContext {
    /// Creates a new context for the given source path and user request.
    pub fn new(source_path: impl AsRef<Path>, user_request: impl Into<String>) -> Self {
        Self {
            source_path: source_path.as_ref().to_path_buf(),
            project_root: None,
            user_request: user_request.into(),
            reporter: Arc::new(NoopReporter),
            config: PipelineConfig::default(),
        }
    }

    /// Sets the project root directory.
    pub fn with_project_root(mut self, root: impl AsRef<Path>) -> Self {
        self.project_root = Some(root.as_ref().to_path_buf());
        self
    }

    /// Sets the reporter used to emit pipeline events.
    pub fn with_reporter(mut self, reporter: Arc<dyn PipelineReporter>) -> Self {
        self.reporter = reporter;
        self
    }

    /// Sets the pipeline configuration.
    pub fn with_config(mut self, config: PipelineConfig) -> Self {
        self.config = config;
        self
    }
}

/// Event emitted by pipeline stages to report progress or warnings.
#[derive(Debug, Clone)]
pub enum PipelineEvent {
    /// A stage has started.
    StageStart { stage: String },
    /// A stage has made progress.
    StageProgress { stage: String, message: String },
    /// A stage has completed successfully.
    StageComplete { stage: String },
    /// A stage emitted a non-fatal warning.
    StageWarning { stage: String, message: String },
}

/// Trait for objects that receive pipeline events.
pub trait PipelineReporter: Send + Sync {
    /// Reports a pipeline event.
    fn report(&self, event: PipelineEvent);
}

/// Reporter that discards all events.
pub struct NoopReporter;

impl Default for NoopReporter {
    fn default() -> Self {
        Self
    }
}

impl PipelineReporter for NoopReporter {
    fn report(&self, _event: PipelineEvent) {}
}

/// Reporter that collects all reported events into a vector.
pub struct CollectingReporter {
    /// Collected pipeline events.
    pub events: std::sync::Mutex<Vec<PipelineEvent>>,
}

impl Default for CollectingReporter {
    fn default() -> Self {
        Self::new()
    }
}

impl CollectingReporter {
    /// Creates a new empty collecting reporter.
    pub fn new() -> Self {
        Self {
            events: std::sync::Mutex::new(Vec::new()),
        }
    }
}

impl PipelineReporter for CollectingReporter {
    fn report(&self, event: PipelineEvent) {
        if let Ok(mut events) = self.events.lock() {
            events.push(event);
        } else {
            log::warn!("Pipeline event dropped because CollectingReporter mutex was poisoned");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn collecting_reporter_records_events() {
        let reporter = Arc::new(CollectingReporter::new());
        reporter.report(PipelineEvent::StageStart {
            stage: "extract".into(),
        });
        let events = reporter.events.lock().unwrap();
        assert_eq!(events.len(), 1);
    }
}
