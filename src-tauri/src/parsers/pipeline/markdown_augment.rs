//! Post-process the OCR markdown so every image position has a
//! description + a working local storage link.
//!
//! Two passes:
//! 1. **Inline rewrite** — for every `![alt](xxx)` reference in the input
//!    markdown whose `xxx` matches an extracted image's filename or path,
//!    swap the URL for the local `rel_path` and ensure the alt text
//!    contains the description (VLM caption when available, else a
//!    page-N fallback).
//! 2. **Append** — any extracted image that is **not** referenced in the
//!    markdown gets a bullet entry under `## Extracted Images` so the
//!    user can still navigate to it from the markdown.
//!
//! `populate_descriptions_from_detection_cache` (separate helper) joins
//! each `ImageRef` against the per-page `DetectionCache` written by the
//! VLM chem pipeline and copies the resulting `vlm_caption` into
//! `ImageRef.description`. Run it after the VLM pass so the markdown
//! augmentation picks up real captions instead of fallbacks.

use std::path::Path;

use crate::core::document::detection_cache::DetectionCache;
use crate::parsers::doc_types::ImageRef;

/// Default description text when neither `ImageRef.description` nor a
/// VLM caption is available.
fn default_description(img: &ImageRef) -> String {
    format!("Image extracted from page {}", img.page)
}

/// Rewrite every `![alt](url)` whose `url` matches an extracted image's
/// filename or full path so it points to the local `rel_path`. The alt
/// text is replaced with a description when we have one.
fn rewrite_inline_references(markdown: &str, images: &[ImageRef]) -> String {
    let mut out = String::with_capacity(markdown.len());
    let mut rest = markdown;

    while let Some(start) = rest.find("![") {
        out.push_str(&rest[..start]);
        rest = &rest[start + 2..];

        // Find the closing `]`
        let Some(close_bracket) = rest.find(']') else {
            out.push_str("![");
            out.push_str(rest);
            return out;
        };
        let alt = &rest[..close_bracket];
        rest = &rest[close_bracket + 1..];

        // Expect `(`
        if !rest.starts_with('(') {
            out.push_str("![");
            out.push_str(alt);
            out.push(']');
            continue;
        }
        rest = &rest[1..];

        // Find the matching `)` (allow nested parens in URL)
        let mut depth = 1i32;
        let mut end = rest.len();
        for (i, ch) in rest.char_indices() {
            match ch {
                '(' => depth += 1,
                ')' => {
                    depth -= 1;
                    if depth == 0 {
                        end = i;
                        break;
                    }
                }
                _ => {}
            }
        }
        let url = &rest[..end];
        let after = if end < rest.len() { &rest[end + 1..] } else { "" };

        // Match against extracted images by filename OR full path
        let matched = images.iter().find(|img| {
            img.filename == url
                || img.rel_path.as_deref() == Some(url)
                || img.rel_path.as_deref().map(|p| p.ends_with(url)).unwrap_or(false)
        });

        if let Some(img) = matched {
            let new_url = img
                .rel_path
                .clone()
                .unwrap_or_else(|| img.filename.clone());
            let new_alt = img
                .description
                .clone()
                .unwrap_or_else(|| default_description(img));
            out.push_str(&format!("![{}]({})", new_alt, new_url));
        } else {
            // Leave the reference as-is
            out.push_str(&format!("![{}]({})", alt, url));
        }
        rest = after;
    }
    out.push_str(rest);
    out
}

/// Build the "Extracted Images" appendix for images that are not
/// referenced anywhere in the markdown.
fn build_appendix(unreferenced: &[&ImageRef]) -> String {
    if unreferenced.is_empty() {
        return String::new();
    }
    let mut s = String::new();
    s.push_str("\n\n---\n\n");
    s.push_str("## Extracted Images\n\n");
    s.push_str(
        "以下图片已从 PDF 中提取并保存到项目目录，但未在正文中嵌入。\
         可通过下方链接直接打开。\n\n",
    );
    for img in unreferenced {
        let url = img.rel_path.clone().unwrap_or_else(|| img.filename.clone());
        let desc = img
            .description
            .clone()
            .unwrap_or_else(|| default_description(img));
        s.push_str(&format!("- **page {}** — {}  \n", img.page, desc));
        s.push_str(&format!("  `{}`\n", url));
    }
    s
}

/// Look up each `ImageRef` in the per-page `DetectionCache` written by
/// the VLM chem pipeline and copy the matching detection's
/// `vlm_caption` into `ImageRef.description`.
///
/// Matching is best-effort because the `DetectionCache` stores the
/// *cropped* molecule path (a region of the original image), while
/// `ImageRef.rel_path` is the full extracted image. We match by:
/// - the cropped path being inside the extracted image (suffix match), or
/// - the cropped path's basename matching the extracted image's basename
///   (handles cases where the relative paths differ only by directory).
///
/// `images` whose `description` is already populated are skipped
/// (callers can pre-populate with VLM-direct captions to win over the
/// cache). `images` whose lookup misses the cache are left alone —
/// `augment_markdown_with_images` will fall back to "Image extracted
/// from page N".
///
/// Returns the number of images that received a new description.
pub fn populate_descriptions_from_detection_cache(
    images: &mut [ImageRef],
    project_root: &Path,
    doc_id: &str,
    pdf_hash: &str,
) -> usize {
    if images.is_empty() {
        return 0;
    }
    let cache = DetectionCache::new(project_root);
    let mut updated = 0usize;
    for img in images.iter_mut() {
        if img.description.is_some() {
            continue;
        }
        let page_det = match cache.get(doc_id, img.page, pdf_hash) {
            Some(p) => p,
            None => continue,
        };
        let img_rel = img.rel_path.as_deref().unwrap_or(&img.filename);
        let img_basename = std::path::Path::new(img_rel)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or(img_rel);
        let match_ = page_det.detections.iter().find(|d| {
            // exact match
            d.crop_relpath == img_rel
                // cropped path is inside the extracted image
                || d.crop_relpath.ends_with(img_basename)
                // or the extracted image ends with the cropped path
                || img_rel.ends_with(&d.crop_relpath)
        });
        if let Some(d) = match_ {
            if let Some(cap) = d.vlm_caption.as_ref() {
                if !cap.trim().is_empty() {
                    img.description = Some(cap.clone());
                    updated += 1;
                }
            }
        }
    }
    updated
}

/// Top-level entry point. Augments the markdown so every image
/// position has both a description and a working local link.
pub fn augment_markdown_with_images(markdown: &str, images: &[ImageRef]) -> String {
    if images.is_empty() {
        return markdown.to_string();
    }

    // Pass 1: rewrite inline `![]()` references that point at extracted
    // images so the URL is the local path and the alt is a description.
    let rewritten = rewrite_inline_references(markdown, images);

    // Pass 2: collect images that still aren't referenced (so we can
    // append them under a "## Extracted Images" section).
    let mut unreferenced: Vec<&ImageRef> = Vec::new();
    for img in images {
        let url = img.rel_path.as_deref().unwrap_or(&img.filename);
        let referenced = rewritten.contains(&format!("]({}", url))
            || rewritten.contains(&format!("]({}", img.filename));
        if !referenced {
            unreferenced.push(img);
        }
    }

    let mut out = rewritten;
    out.push_str(&build_appendix(&unreferenced));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn img(filename: &str, rel_path: &str, page: usize, desc: Option<&str>) -> ImageRef {
        ImageRef {
            filename: filename.to_string(),
            page,
            region: None,
            description: desc.map(|s| s.to_string()),
            esmiles: None,
            rel_path: Some(rel_path.to_string()),
        }
    }

    #[test]
    fn empty_images_returns_input_unchanged() {
        let md = "# Hello\n\nSome text.\n";
        assert_eq!(augment_markdown_with_images(md, &[]), md);
    }

    #[test]
    fn rewrites_inline_reference_to_local_path_and_alt() {
        let images = vec![img(
            "img-001.png",
            "media/doc-slug/img-001.png",
            3,
            Some("Ethanol molecule diagram"),
        )];
        let md = "Look at this: ![old-alt](img-001.png) is interesting.\n";
        let out = augment_markdown_with_images(md, &images);
        assert!(out.contains("![Ethanol molecule diagram](media/doc-slug/img-001.png)"));
    }

    #[test]
    fn leaves_unrelated_inline_reference_alone() {
        // No images extracted at all → markdown passes through verbatim
        // (empty `images` short-circuits the early-return in the entry point).
        let md = "External: ![alt](https://example.com/photo.jpg) here.\n";
        let out = augment_markdown_with_images(md, &[]);
        assert!(out.contains("![alt](https://example.com/photo.jpg)"));
        assert!(!out.contains("## Extracted Images"));
    }

    #[test]
    fn external_inline_ref_does_not_match_extracted_image() {
        // An external URL like https://example.com/photo.jpg must NOT be
        // treated as a match for an extracted image whose rel_path is
        // media/img-001.png. The extracted image ends up in the appendix.
        let images = vec![img("img-001.png", "media/img-001.png", 3, None)];
        let md = "External: ![alt](https://example.com/photo.jpg) here.\n";
        let out = augment_markdown_with_images(md, &images);
        assert!(out.contains("![alt](https://example.com/photo.jpg)"));
        // img-001 is unreferenced → goes to the appendix
        assert!(out.contains("## Extracted Images"));
        assert!(out.contains("`media/img-001.png`"));
    }

    #[test]
    fn appends_section_for_unreferenced_extracted_image() {
        let images = vec![img(
            "img-002.png",
            "media/doc-slug/img-002.png",
            5,
            Some("Catalyst structure"),
        )];
        let md = "# Paper\n\nNo images referenced here.\n";
        let out = augment_markdown_with_images(md, &images);
        assert!(out.contains("## Extracted Images"));
        assert!(out.contains("page 5"));
        assert!(out.contains("Catalyst structure"));
        assert!(out.contains("`media/doc-slug/img-002.png`"));
    }

    #[test]
    fn mix_rewrite_and_append() {
        let images = vec![
            img("img-001.png", "media/img-001.png", 3, Some("Caption A")),
            img("img-002.png", "media/img-002.png", 4, Some("Caption B")),
        ];
        let md = "Inline: ![](img-001.png) end.\n";
        let out = augment_markdown_with_images(md, &images);
        // img-001 got rewritten inline
        assert!(out.contains("![Caption A](media/img-001.png)"));
        // img-002 ends up in the appendix
        assert!(out.contains("## Extracted Images"));
        assert!(out.contains("Caption B"));
        assert!(out.contains("`media/img-002.png`"));
    }

    #[test]
    fn default_description_used_when_no_caption() {
        let images = vec![img("img.png", "media/img.png", 7, None)];
        let md = "No inline ref.\n";
        let out = augment_markdown_with_images(md, &images);
        assert!(out.contains("Image extracted from page 7"));
    }
}
