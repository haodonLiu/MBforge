//! Output writers for the pipeline module.

use std::path::{Path, PathBuf};

use mbforge_infra::config::constants::PROJECTS_DIR;

/// Markdown augmentation helpers that rewrite image references and
/// append unreferenced extracted images.
pub mod markdown_augment;
/// Per-document output-status tracking.
pub mod output_status;
/// Structured agent report markdown writer.
pub mod report_md;
/// Augmented extraction markdown writer with image verification appendix.
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
