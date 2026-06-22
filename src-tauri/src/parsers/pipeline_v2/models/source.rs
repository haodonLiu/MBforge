//! Source input model for the pipeline v2 parsing flow.

use std::path::PathBuf;

/// Input descriptor for a single document fed into the pipeline.
#[derive(Debug, Clone)]
pub struct SourceInput {
    /// Path to the source document.
    pub path: PathBuf,

    /// Optional project root used to resolve relative paths and place outputs.
    pub project_root: Option<PathBuf>,

    /// Whether OCR-based parsing backends are allowed for this source.
    pub allow_ocr: bool,
}

impl SourceInput {
    /// Creates a new [`SourceInput`] for the given path with OCR enabled by default.
    ///
    /// # Type Parameters
    ///
    /// * `P` - Any type that can be converted into a [`PathBuf`].
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self {
            path: path.into(),
            project_root: None,
            allow_ocr: true,
        }
    }

    /// Sets the project root for this input.
    ///
    /// # Type Parameters
    ///
    /// * `P` - Any type that can be converted into a [`PathBuf`].
    pub fn with_project_root(mut self, root: impl Into<PathBuf>) -> Self {
        self.project_root = Some(root.into());
        self
    }

    /// Sets whether OCR is permitted for this input.
    pub fn with_allow_ocr(mut self, allow: bool) -> Self {
        self.allow_ocr = allow;
        self
    }
}
