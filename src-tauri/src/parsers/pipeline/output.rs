//! Per-document output writers for the PDF processing pipeline.
//!
//! Every processed PDF must produce two artifacts inside its
//! `DocumentProject` directory:
//!
//! - `text.md` — the OCR / extraction result. Markdown text enriched with
//!   inline image references, an "Extracted Images" appendix, and a
//!   "图片校对" section that flags any image whose semantic anchor
//!   (description / SMILES / inline reference / figure caption) is
//!   missing.
//! - `report.md` — the structured agent report. Re-uses
//!   `report::generate_full_report` to render `StructuredData` + SAR
//!   analysis. A minimal "no data" report is written when the agent
//!   stages produced nothing (e.g. empty PDF, parse error).
//!
//! Both files are written *unconditionally* on every successful
//! `process_document` run, regardless of whether the source PDF was
//! text-based or a scan.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::core::config::constants::PROJECTS_DIR;
use crate::parsers::doc_types::{ImageRef, StructuredData};
use crate::parsers::pipeline::markdown_augment::augment_markdown_with_images;
use crate::parsers::structure::report::generate_full_report;

/// Output paths written for a single document.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentOutputs {
    /// Absolute path of `text.md`. None if the writer could not resolve
    /// the DocumentProject directory.
    pub text_md: Option<PathBuf>,
    /// Absolute path of `report.md`.
    pub report_md: Option<PathBuf>,
    /// Number of images flagged for manual review.
    pub unverified_image_count: usize,
}

/// Resolve the canonical per-document output directory:
/// `<project_root>/projects/<doc_id>/`.
pub fn output_dir(project_root: &Path, doc_id: &str) -> PathBuf {
    project_root.join(PROJECTS_DIR).join(doc_id)
}

/// Status of a single document's mandatory output files.
///
/// A document is considered "fully read" only when **both**
/// `text.md` and `report.md` exist on disk. A missing file means the
/// pipeline has not finished (or failed) for that document and any
/// downstream operation (search, chat, KB) should treat the document
/// as not-yet-indexed.
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
///
/// Use this to gate downstream operations: search/chat should skip
/// documents that report `complete == false`.
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

/// One row in the "图片校对" appendix. An image is "verified" when it
/// has any of: a VLM description, a recognized SMILES, an inline
/// markdown reference, or a nearby figure-caption keyword in the text.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImageVerification {
    pub filename: String,
    pub page: usize,
    pub verified: bool,
    pub anchor: String, // "description" | "esmiles" | "inline_ref" | "caption" | "none"
}

const FIGURE_PREFIXES: &[&str] = &["figure ", "fig. ", "scheme ", "fig ", "sch ", "table "];

/// Run the image / text correspondence check.
///
/// `markdown` is the raw extracted text. `images` is the list extracted
/// from the PDF (and optionally VLM-captioned during the pipeline).
/// Each image receives a verdict + the strongest anchor we found.
pub fn verify_images(markdown: &str, images: &[ImageRef]) -> Vec<ImageVerification> {
    images
        .iter()
        .map(|img| {
            let anchor = detect_anchor(markdown, img);
            ImageVerification {
                filename: img.filename.clone(),
                page: img.page,
                verified: anchor != "none",
                anchor: anchor.to_string(),
            }
        })
        .collect()
}

fn detect_anchor(markdown: &str, img: &ImageRef) -> &'static str {
    if img.description.as_deref().map(str::trim).map(str::is_empty) == Some(false) {
        return "description";
    }
    if img.esmiles.as_deref().map(str::trim).map(str::is_empty) == Some(false) {
        return "esmiles";
    }
    // Inline markdown reference: `![](<filename>)` or `![](<rel_path>)`.
    let rel = img.rel_path.as_deref().unwrap_or(&img.filename);
    if markdown.contains(&format!("]({}", rel))
        || markdown.contains(&format!("]({}", img.filename))
    {
        return "inline_ref";
    }
    // Heuristic figure-caption keyword on the same page — we don't have
    // per-line page numbers in the raw markdown, so scan the whole text
    // for any line that mentions Figure/Fig/Scheme/Table plus a digit
    // (cheap and good enough for the right-pane flag).
    if has_figure_caption_keyword(markdown) {
        return "caption";
    }
    "none"
}

fn has_figure_caption_keyword(markdown: &str) -> bool {
    for line in markdown.lines() {
        let lower = line.trim_start().to_lowercase();
        for prefix in FIGURE_PREFIXES {
            if lower.starts_with(prefix) {
                let tail = &lower[prefix.len()..];
                if tail
                    .chars()
                    .next()
                    .map(|c| c.is_ascii_digit())
                    .unwrap_or(false)
                {
                    return true;
                }
            }
        }
    }
    false
}

// ---------------------------------------------------------------------------
// text.md writer
// ---------------------------------------------------------------------------

/// Write the augmented extraction markdown to
/// `<project_root>/projects/<doc_id>/text.md`.
///
/// Returns the absolute path of the written file. When `raw_text` is
/// empty (e.g. a scanned PDF whose OCR pass produced no text) the
/// function still writes a usable file: a header + a "扫描件 PDF"
/// notice + a per-page image index. The file always exists at the
/// returned path after the call.
pub fn write_text_markdown(
    project_root: &Path,
    doc_id: &str,
    raw_text: &str,
    images: &[ImageRef],
    page_count: usize,
    parser_label: &str,
) -> Result<(PathBuf, Vec<ImageVerification>), String> {
    let dir = output_dir(project_root, doc_id);
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("create output dir {}: {}", dir.display(), e))?;
    let path = dir.join("text.md");

    let body = build_text_body(raw_text, images, page_count, parser_label);
    let verifications = verify_images(&body, images);

    std::fs::write(&path, body).map_err(|e| format!("write text.md: {}", e))?;
    Ok((path, verifications))
}

fn build_text_body(
    raw_text: &str,
    images: &[ImageRef],
    page_count: usize,
    parser_label: &str,
) -> String {
    let mut out = String::new();

    // Header — keep it small and machine-greppable.
    out.push_str(&format!(
        "# 提取结果\n\n- doc_id: `{0}`\n- parser: `{1}`\n- pages: {2}\n\n",
        // doc_id is passed in by caller; no escaping needed beyond backticks
        // since we control the input format. The header is intentionally
        // not interpolated as raw markdown.
        "doc",
        escape_inline(parser_label),
        page_count
    ));

    let trimmed = raw_text.trim();
    if trimmed.is_empty() {
        out.push_str("> 扫描件 PDF — 当前未识别出可读文本（需要 OCR 后端补齐）。\n");
        out.push_str("> 本文档已提取以下图像（详见末尾「图片校对」一节）。\n\n");
    } else {
        // Pass the raw text through the existing augmentor: it rewrites
        // inline image references to local paths and appends an
        // "## Extracted Images" appendix for anything not referenced.
        let augmented = augment_markdown_with_images(trimmed, images, None);
        out.push_str(&augmented);
        out.push_str("\n\n");
    }

    // Image / text correspondence appendix.
    out.push_str("## 图片校对\n\n");
    if images.is_empty() {
        out.push_str("（本文档未提取到图像。）\n");
    } else {
        out.push_str("| 文件 | 页 | 状态 | 锚点 |\n");
        out.push_str("|------|----|------|------|\n");
        let verifications = verify_images(trimmed, images);
        for v in &verifications {
            let status = if v.verified { "✅" } else { "⚠️ 未校对" };
            out.push_str(&format!(
                "| `{}` | {} | {} | {} |\n",
                escape_inline(&v.filename),
                v.page,
                status,
                v.anchor
            ));
        }
        let unverified: Vec<&ImageVerification> =
            verifications.iter().filter(|v| !v.verified).collect();
        if !unverified.is_empty() {
            out.push_str("\n> 未校对图像没有可用锚点（VLM 描述 / SMILES / 内联引用 / 图注）。\n");
            out.push_str("> 请人工补一句与该图像对应的文字说明，或在 PDF 中确认图像位置。\n");
        }
    }

    out
}

// ---------------------------------------------------------------------------
// report.md writer
// ---------------------------------------------------------------------------

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
) -> Result<PathBuf, String> {
    let dir = output_dir(project_root, doc_id);
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("create output dir {}: {}", dir.display(), e))?;
    let path = dir.join("report.md");

    let body = match final_data {
        Some(data) if !data.summary.trim().is_empty() => {
            let mut s = generate_full_report(data, sar_analysis);
            s.push_str(&format!(
                "\n\n---\n\n*报告由 agent 处理生成。解析后端: `{}` · doc_id: `{}`*\n",
                escape_inline(parser_label),
                escape_inline(doc_id)
            ));
            s
        }
        _ => empty_report(doc_id, parser_label),
    };

    std::fs::write(&path, body).map_err(|e| format!("write report.md: {}", e))?;
    Ok(path)
}

fn empty_report(doc_id: &str, parser_label: &str) -> String {
    format!(
        "# 报告（无数据）\n\n\
         管线未产出 `StructuredData`（可能 PDF 为空、解析失败，或 agent 阶段被跳过）。\n\n\
         - doc_id: `{}`\n- parser: `{}`\n\n\
         请检查原始 PDF 与处理日志后重试。\n",
        escape_inline(doc_id),
        escape_inline(parser_label)
    )
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

/// Escape characters that would break inline backtick / pipe cells.
fn escape_inline(s: &str) -> String {
    s.replace('`', "'").replace('|', "\\|").replace('\n', " ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn img(filename: &str, page: usize, description: Option<&str>) -> ImageRef {
        ImageRef {
            filename: filename.to_string(),
            page,
            region: None,
            description: description.map(str::to_string),
            esmiles: None,
            rel_path: Some(format!("reports/figures/doc/{}", filename)),
        }
    }

    #[test]
    fn detect_anchor_prefers_description() {
        let md = "";
        let v = detect_anchor(md, &img("a.png", 1, Some("A scatter plot")));
        assert_eq!(v, "description");
    }

    #[test]
    fn detect_anchor_falls_back_to_esmiles() {
        let v = detect_anchor("", &img("a.png", 1, None));
        // No description, no esmiles, no inline ref, no caption → "none"
        assert_eq!(v, "none");
    }

    #[test]
    fn detect_anchor_finds_esmiles() {
        let mut with = img("a.png", 1, None);
        with.esmiles = Some("c1ccccc1".to_string());
        assert_eq!(detect_anchor("", &with), "esmiles");
    }

    #[test]
    fn detect_anchor_finds_inline_ref() {
        let md = "Look at ![](reports/figures/doc/a.png) for the structure.";
        assert_eq!(detect_anchor(md, &img("a.png", 2, None)), "inline_ref");
    }

    #[test]
    fn detect_anchor_finds_figure_caption() {
        let md = "Figure 3. Dose-response curve for compound 7.\nMore text.";
        assert_eq!(detect_anchor(md, &img("b.png", 3, None)), "caption");
    }

    #[test]
    fn detect_anchor_rejects_caption_without_digit() {
        let md = "Figure caption without a number.";
        assert_eq!(detect_anchor(md, &img("b.png", 3, None)), "none");
    }

    #[test]
    fn build_text_body_handles_scanned_pdf() {
        let body = build_text_body("", &[img("p1.png", 1, None)], 5, "pdf_inspector");
        assert!(body.contains("扫描件 PDF"));
        assert!(body.contains("图片校对"));
        assert!(body.contains("⚠️ 未校对"));
    }

    #[test]
    fn build_text_body_includes_augmented_images_section() {
        let body = build_text_body(
            "Body text.\n\n![desc](reports/figures/doc/a.png)\n\nMore text.",
            &[img("a.png", 1, Some("alt"))],
            2,
            "pdf_inspector",
        );
        assert!(body.contains("Body text"));
        assert!(body.contains("图片校对"));
        // Description is present → the row must be marked verified.
        assert!(body.contains("✅"));
    }

    #[test]
    fn write_text_markdown_creates_file_with_verifications() {
        let dir = tempfile::tempdir().unwrap();
        let (path, vers) = write_text_markdown(
            dir.path(),
            "doc-abc",
            "Hello world.",
            &[img("a.png", 1, Some("Plot"))],
            1,
            "pdf_inspector",
        )
        .unwrap();
        assert!(path.exists());
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("Hello world"));
        assert!(content.contains("图片校对"));
        assert_eq!(vers.len(), 1);
        assert!(vers[0].verified);
    }

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
            metadata: crate::parsers::doc_types::DocumentMetadata {
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
        let dir = output_dir(Path::new("/tmp/proj"), "doc-123");
        assert_eq!(dir, PathBuf::from("/tmp/proj/projects/doc-123"));
    }

    #[test]
    fn output_status_reports_missing_both() {
        let dir = tempfile::tempdir().unwrap();
        let s = output_status(dir.path(), "doc-missing");
        assert!(!s.text_md_exists);
        assert!(!s.report_md_exists);
        assert!(!s.complete);
        assert_eq!(
            IncompleteReason::from_status(&s),
            IncompleteReason::MissingBoth
        );
        assert!(!is_document_complete(dir.path(), "doc-missing"));
    }

    #[test]
    fn output_status_reports_partial() {
        let dir = tempfile::tempdir().unwrap();
        let proj = dir.path().join("projects").join("doc-partial");
        std::fs::create_dir_all(&proj).unwrap();
        std::fs::write(proj.join("text.md"), "x").unwrap();
        let s = output_status(dir.path(), "doc-partial");
        assert!(s.text_md_exists);
        assert!(!s.report_md_exists);
        assert!(!s.complete);
        assert_eq!(
            IncompleteReason::from_status(&s),
            IncompleteReason::MissingReportMd
        );
    }

    #[test]
    fn output_status_reports_complete() {
        let dir = tempfile::tempdir().unwrap();
        let proj = dir.path().join("projects").join("doc-ok");
        std::fs::create_dir_all(&proj).unwrap();
        std::fs::write(proj.join("text.md"), "x").unwrap();
        std::fs::write(proj.join("report.md"), "y").unwrap();
        let s = output_status(dir.path(), "doc-ok");
        assert!(s.complete);
        assert!(is_document_complete(dir.path(), "doc-ok"));
        assert_eq!(
            IncompleteReason::from_status(&s),
            IncompleteReason::Complete
        );
    }
}
