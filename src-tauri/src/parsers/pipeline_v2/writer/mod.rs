//! Output writers for pipeline_v2.

use std::path::{Path, PathBuf};

use crate::core::config::constants::PROJECTS_DIR;

pub mod report_md;
pub mod text_md;

/// Resolve the canonical per-document output directory:
/// `<project_root>/projects/<doc_id>/`.
pub fn output_dir(project_root: &Path, doc_id: &str) -> PathBuf {
    project_root.join(PROJECTS_DIR).join(doc_id)
}

/// Escape characters that would break inline backtick cells.
pub fn escape_inline(text: &str) -> String {
    text.replace('`', "\\`")
}
