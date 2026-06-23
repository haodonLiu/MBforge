//! Per-document output status for the PDF processing pipeline.
//!
//! A document is considered "fully read" only when **both** `text.md` and
//! `report.md` exist on disk. A missing file means the pipeline has not
//! finished (or failed) for that document and any downstream operation
//! (search, chat, KB) should treat the document as not-yet-indexed.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::core::config::constants::PROJECTS_DIR;

/// Resolve the canonical per-document output directory:
/// `<project_root>/projects/<doc_id>/`.
pub fn output_dir(project_root: &Path, doc_id: &str) -> PathBuf {
    project_root.join(PROJECTS_DIR).join(doc_id)
}

/// Status of a single document's mandatory output files.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OutputStatus {
    /// Absolute path of `text.md`. Always returned even when missing.
    pub text_md_path: PathBuf,
    pub text_md_exists: bool,
    /// Absolute path of `report.md`.
    pub report_md_path: PathBuf,
    pub report_md_exists: bool,
    /// Convenience flag: `text_md_exists && report_md_exists`.
    pub complete: bool,
}

/// Read the on-disk presence of the two mandatory output files for a
/// document. Pure filesystem check — no DB, no side-effects.
pub fn output_status(project_root: &Path, doc_id: &str) -> OutputStatus {
    let dir = output_dir(project_root, doc_id);
    let text_md_path = dir.join("text.md");
    let report_md_path = dir.join("report.md");
    let text_md_exists = text_md_path.is_file();
    let report_md_exists = report_md_path.is_file();
    OutputStatus {
        text_md_path,
        text_md_exists,
        report_md_path,
        report_md_exists,
        complete: text_md_exists && report_md_exists,
    }
}

/// Convenience: did the document finish producing both required files?
pub fn is_document_complete(project_root: &Path, doc_id: &str) -> bool {
    output_status(project_root, doc_id).complete
}

/// One-line reason string for the front-end "未完成" badge. Stable
/// vocabulary so the UI can switch on it without parsing free text.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum IncompleteReason {
    /// Both `text.md` and `report.md` are present.
    Complete,
    /// `text.md` is missing.
    MissingTextMd,
    /// `report.md` is missing.
    MissingReportMd,
    /// Both are missing.
    MissingBoth,
}

impl IncompleteReason {
    pub fn from_status(s: &OutputStatus) -> Self {
        match (s.text_md_exists, s.report_md_exists) {
            (true, true) => IncompleteReason::Complete,
            (false, true) => IncompleteReason::MissingTextMd,
            (true, false) => IncompleteReason::MissingReportMd,
            (false, false) => IncompleteReason::MissingBoth,
        }
    }
}
