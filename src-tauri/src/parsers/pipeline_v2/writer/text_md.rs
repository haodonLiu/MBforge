//! text.md writer for pipeline_v2.
//!
//! Every processed document writes an augmented extraction markdown file
//! inside its DocumentProject directory. The file contains the raw text
//! (or a scanned-PDF notice), an inline image rewrite pass, and an image
//! verification appendix that flags figures without a semantic anchor.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

use crate::parsers::doc_types::ImageRef as DocTypeImageRef;
use crate::parsers::pipeline::markdown_augment::augment_markdown_with_images;
use crate::parsers::pipeline_v2::error::{PersistError, PipelineError};

/// One row in the "图片校对" appendix. An image is "verified" when it
/// has any of: a VLM description, a recognized SMILES, an inline
/// markdown reference, or a nearby figure-caption keyword in the text.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ImageVerification {
    /// Extracted image filename.
    pub filename: String,
    /// One-based page number where the image appears.
    pub page: usize,
    /// Whether a semantic anchor was detected for this image.
    pub verified: bool,
    /// The strongest anchor found: "description", "esmiles",
    /// "inline_ref", "caption", or "none".
    pub anchor: String,
}

const FIGURE_PREFIXES: &[&str] = &["figure ", "fig. ", "scheme ", "fig ", "sch ", "table "];

/// Run the image / text correspondence check.
///
/// `markdown` is the raw extracted text. `images` is the list extracted
/// from the PDF (and optionally VLM-captioned during the pipeline).
/// Each image receives a verdict plus the strongest anchor we found.
pub fn verify_images(markdown: &str, images: &[DocTypeImageRef]) -> Vec<ImageVerification> {
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

fn detect_anchor(markdown: &str, img: &DocTypeImageRef) -> &'static str {
    if img.description.as_deref().map(str::trim).map(str::is_empty) == Some(false) {
        return "description";
    }
    if img.esmiles.as_deref().map(str::trim).map(str::is_empty) == Some(false) {
        return "esmiles";
    }
    // Inline markdown reference: `![](<filename>)` or `![](<rel_path>)`.
    let rel = img.rel_path.as_deref().unwrap_or(&img.filename);
    if markdown.contains(&format!("]({}", rel)) || markdown.contains(&format!("]({}", img.filename))
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

/// Write the augmented extraction markdown to
/// `<project_root>/projects/<doc_id>/text.md`.
///
/// Returns the absolute path of the written file and the image
/// verification table. When `raw_text` is empty (e.g. a scanned PDF whose
/// OCR pass produced no text) the function still writes a usable file: a
/// header, a scanned-PDF notice, and a per-page image index. The file
/// always exists at the returned path after the call.
pub fn write_text_markdown(
    project_root: &Path,
    doc_id: &str,
    raw_text: &str,
    images: &[crate::parsers::pipeline_v2::models::extracted::ImageRef],
    page_count: usize,
    parser_label: &str,
) -> Result<(PathBuf, Vec<ImageVerification>), PipelineError> {
    let dir = super::output_dir(project_root, doc_id);
    let dir = crate::core::helpers::assert_within_root_allow_missing(
        project_root.to_string_lossy().as_ref(),
        &dir,
    )
    .map_err(|e| {
        PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: dir.clone(),
            detail: e,
        })
    })?;
    std::fs::create_dir_all(&dir).map_err(|e| {
        PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: dir.clone(),
            detail: format!("create output dir: {e}"),
        })
    })?;

    let path = dir.join("text.md");
    let path = crate::core::helpers::assert_within_root_allow_missing(
        project_root.to_string_lossy().as_ref(),
        &path,
    )
    .map_err(|e| {
        PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: path.clone(),
            detail: e,
        })
    })?;

    let doc_type_images = to_doc_type_image_refs(images);
    let trimmed = raw_text.trim();
    let verifications = verify_images(trimmed, &doc_type_images);
    let body = build_text_body(
        doc_id,
        trimmed,
        &doc_type_images,
        page_count,
        parser_label,
        &verifications,
    );

    std::fs::write(&path, body).map_err(|e| {
        PipelineError::Persist(PersistError::TextMdWriteFailed {
            path: path.clone(),
            detail: format!("write text.md: {e}"),
        })
    })?;
    Ok((path, verifications))
}

fn build_text_body(
    doc_id: &str,
    trimmed: &str,
    images: &[DocTypeImageRef],
    page_count: usize,
    parser_label: &str,
    verifications: &[ImageVerification],
) -> String {
    let mut out = String::new();

    // Header — keep it small and machine-greppable.
    out.push_str(&format!(
        "# 提取结果\n\n- doc_id: `{0}`\n- parser: `{1}`\n- pages: {2}\n\n",
        super::escape_inline(doc_id),
        super::escape_inline(parser_label),
        page_count
    ));

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
        for v in verifications {
            let status = if v.verified {
                "✅"
            } else {
                "⚠️ 未校对"
            };
            out.push_str(&format!(
                "| `{}` | {} | {} | {} |\n",
                super::escape_inline(&v.filename),
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

/// Convert pipeline_v2 `ImageRef` values into the `doc_types::ImageRef`
/// shape expected by the existing markdown augmentation helpers.
fn to_doc_type_image_refs(
    images: &[crate::parsers::pipeline_v2::models::extracted::ImageRef],
) -> Vec<DocTypeImageRef> {
    images
        .iter()
        .map(|img| DocTypeImageRef {
            filename: img.filename.clone(),
            page: img.page,
            region: img.region.clone(),
            description: img.description.clone(),
            esmiles: img.esmiles.clone(),
            rel_path: img.rel_path.clone(),
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn img(filename: &str, page: usize, description: Option<&str>) -> DocTypeImageRef {
        DocTypeImageRef {
            filename: filename.to_string(),
            page,
            region: None,
            description: description.map(str::to_string),
            esmiles: None,
            rel_path: Some(format!("reports/figures/doc/{}", filename)),
        }
    }

    fn p2_img(
        filename: &str,
        page: usize,
        description: Option<&str>,
    ) -> crate::parsers::pipeline_v2::models::extracted::ImageRef {
        crate::parsers::pipeline_v2::models::extracted::ImageRef {
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
        let verifications = verify_images("", &[img("p1.png", 1, None)]);
        let body = build_text_body(
            "doc-123",
            "",
            &[img("p1.png", 1, None)],
            5,
            "pdf_inspector",
            &verifications,
        );
        assert!(body.contains("扫描件 PDF"));
        assert!(body.contains("图片校对"));
        assert!(body.contains("⚠️ 未校对"));
    }

    #[test]
    fn build_text_body_includes_augmented_images_section() {
        let images = &[img("a.png", 1, Some("alt"))];
        let trimmed = "Body text.\n\n![desc](reports/figures/doc/a.png)\n\nMore text.";
        let verifications = verify_images(trimmed, images);
        let body = build_text_body(
            "doc-123",
            trimmed,
            images,
            2,
            "pdf_inspector",
            &verifications,
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
            &[p2_img("a.png", 1, Some("Plot"))],
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
    fn write_text_markdown_uses_doc_id_in_header() {
        let dir = tempfile::tempdir().unwrap();
        let (path, _vers) = write_text_markdown(
            dir.path(),
            "doc-xyz",
            "Hello world.",
            &[],
            1,
            "pdf_inspector",
        )
        .unwrap();
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(content.contains("- doc_id: `doc-xyz`"));
    }

    #[test]
    fn output_dir_layout() {
        let dir = super::output_dir(Path::new("/tmp/proj"), "doc-123");
        assert_eq!(dir, PathBuf::from("/tmp/proj/projects/doc-123"));
    }
}
