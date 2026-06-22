//! report.md writer for pipeline_v2.
//!
//! Every processed document writes a structured agent report inside its
//! DocumentProject directory. When the enrichment stage produced no
//! `StructuredData`, a minimal "no data" report is written so the file
//! exists for downstream consumers.

use std::path::{Path, PathBuf};

use crate::parsers::doc_types::StructuredData;
use crate::parsers::pipeline_v2::error::{PersistError, PipelineError};
use crate::parsers::structure::report::generate_full_report;

/// Write the structured agent report to
/// `<project_root>/projects/<doc_id>/report.md`.
///
/// When `final_data` is `None` (pipeline produced nothing) or its
/// `summary` is empty, the function still writes a minimal "no data"
/// report so the file exists for downstream consumers.
pub fn write_agent_report(
    project_root: &Path,
    doc_id: &str,
    final_data: Option<&StructuredData>,
    sar_analysis: Option<&str>,
    parser_label: &str,
) -> Result<PathBuf, PipelineError> {
    let dir = super::output_dir(project_root, doc_id);
    let dir = crate::core::helpers::assert_within_root_allow_missing(
        project_root.to_string_lossy().as_ref(),
        &dir,
    )
    .map_err(|e| {
        PipelineError::Persist(PersistError::ReportMdWriteFailed {
            path: dir.clone(),
            detail: e,
        })
    })?;
    std::fs::create_dir_all(&dir).map_err(|e| {
        PipelineError::Persist(PersistError::ReportMdWriteFailed {
            path: dir.clone(),
            detail: format!("create output dir: {e}"),
        })
    })?;

    let path = dir.join("report.md");
    let path = crate::core::helpers::assert_within_root_allow_missing(
        project_root.to_string_lossy().as_ref(),
        &path,
    )
    .map_err(|e| {
        PipelineError::Persist(PersistError::ReportMdWriteFailed {
            path: path.clone(),
            detail: e,
        })
    })?;

    let body = match final_data {
        Some(data) if !data.summary.trim().is_empty() => {
            let mut s = generate_full_report(data, sar_analysis);
            s.push_str(&format!(
                "\n\n---\n\n*报告由 agent 处理生成。解析后端: `{}` · doc_id: `{}`*\n",
                super::escape_inline(parser_label),
                super::escape_inline(doc_id)
            ));
            s
        }
        _ => empty_report(doc_id, parser_label),
    };

    std::fs::write(&path, body).map_err(|e| {
        PipelineError::Persist(PersistError::ReportMdWriteFailed {
            path: path.clone(),
            detail: format!("write report.md: {e}"),
        })
    })?;
    Ok(path)
}

fn empty_report(doc_id: &str, parser_label: &str) -> String {
    format!(
        "# 报告（无数据）\n\n\
         管线未产出 `StructuredData`（可能 PDF 为空、解析失败，或 agent 阶段被跳过）。\n\n\
         - doc_id: `{}`\n- parser: `{}`\n\n\
         请检查原始 PDF 与处理日志后重试。\n",
        super::escape_inline(doc_id),
        super::escape_inline(parser_label)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parsers::doc_types::DocumentMetadata;

    #[test]
    fn write_agent_report_writes_minimal_when_no_data() {
        let dir = tempfile::tempdir().unwrap();
        let path = write_agent_report(dir.path(), "doc-x", None, None, "pdf_inspector").unwrap();
        let body = std::fs::read_to_string(&path).unwrap();
        assert!(body.contains("报告（无数据）"));
        assert!(body.contains("doc-x"));
    }

    #[test]
    fn write_agent_report_writes_full_when_data_present() {
        let dir = tempfile::tempdir().unwrap();
        let data = StructuredData {
            metadata: DocumentMetadata {
                title: Some("Title".into()),
                authors: vec!["A".into()],
                document_type: "paper".into(),
                key_targets: vec![],
                source_file: Some("p.pdf".into()),
            },
            summary: "A short summary.".into(),
            compounds: vec![],
            activities: vec![],
            key_findings: vec![],
            uncertain_items: vec![],
        };
        let path = write_agent_report(
            dir.path(),
            "doc-y",
            Some(&data),
            Some("SAR shows activity depends on the substituent at C-3."),
            "pdf_inspector",
        )
        .unwrap();
        let body = std::fs::read_to_string(&path).unwrap();
        assert!(body.contains("A short summary"));
        assert!(body.contains("SAR"));
        assert!(body.contains("Title"));
    }

    #[test]
    fn output_dir_layout() {
        let dir =
            crate::parsers::pipeline_v2::writer::output_dir(Path::new("/tmp/proj"), "doc-123");
        assert_eq!(dir, PathBuf::from("/tmp/proj/projects/doc-123"));
    }
}
