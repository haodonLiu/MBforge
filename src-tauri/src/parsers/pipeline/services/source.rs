//! Source path and project root resolution for the extract stage.

use std::path::{Path, PathBuf};

use crate::parsers::pipeline::error::{ExtractError, PipelineError};

/// Resolves a source document path to its containing MBForge project root.
pub struct SourceResolver;

impl SourceResolver {
    /// Creates a new [`SourceResolver`].
    pub fn new() -> Self {
        Self
    }

    /// Determines the project root for `source_path`.
    ///
    /// If `hint` is provided and points to a directory, it is returned verbatim.
    /// Otherwise the filesystem is walked upward from `source_path` looking for
    /// an `.mbforge` directory or a `molecules.db` file. If neither is found,
    /// [`ExtractError::ProjectRootNotFound`] is returned.
    ///
    /// # Arguments
    /// - `source_path` - path to the PDF or source document being processed.
    /// - `hint` - optional trusted project root directory.
    ///
    /// # Errors
    /// Returns `PipelineError::Extract(ExtractError::ProjectRootNotFound)` when
    /// no project root can be determined.
    pub fn resolve_project_root(
        &self,
        source_path: &Path,
        hint: Option<&Path>,
    ) -> Result<PathBuf, PipelineError> {
        if let Some(root) = hint {
            if root.is_dir() {
                return Ok(root.to_path_buf());
            }
        }

        // NOTE: `crate::core::helpers::safe_join` is available and has a
        // matching signature, but it canonicalises the target path and therefore
        // requires the target to already exist. Root discovery must test for the
        // *absence* of `.mbforge` / `molecules.db` at every parent directory, so
        // `safe_join` is not suitable here. The relative components used below
        // are fixed literals with no path-segment separators, so `dir.join()`
        // cannot be influenced by caller input to escape the walked directory.
        let mut current = source_path.parent();
        while let Some(dir) = current {
            if dir.join(".mbforge").is_dir() || dir.join("molecules.db").exists() {
                return Ok(dir.to_path_buf());
            }
            current = dir.parent();
        }

        Err(PipelineError::Extract(ExtractError::ProjectRootNotFound {
            path: source_path.display().to_string(),
        }))
    }
}

impl Default for SourceResolver {
    fn default() -> Self {
        Self::new()
    }
}
