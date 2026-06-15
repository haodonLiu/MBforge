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
use crate::parsers::doc_types::{ImageRef, OcrBlock};

/// Default description text when neither `ImageRef.description` nor a
/// VLM caption is available.
fn default_description(img: &ImageRef) -> String {
    format!("Image extracted from page {}", img.page)
}

/// Rewrite every `![alt](url)` whose `url` matches an extracted image's
/// filename or full path so it points to the local `rel_path`. The alt
/// text is replaced with a description when we have one.
///
/// Uses `pulldown-cmark` to tokenize the markdown. For each image event,
/// look up the dest URL in `images` and rebuild the reference with the
/// matched image's `rel_path` + description; otherwise pass the original
/// slice through unchanged.
fn rewrite_inline_references(markdown: &str, images: &[ImageRef]) -> String {
    use pulldown_cmark::{Event, Parser, Tag};

    let parser = Parser::new(markdown);
    let mut out = String::with_capacity(markdown.len());
    let mut last_end: usize = 0;

    for (event, span) in parser.into_offset_iter() {
        // Copy any text between the previous event's end and this event's start.
        if span.start > last_end {
            out.push_str(&markdown[last_end..span.start]);
        }
        match event {
            Event::Start(Tag::Image {
                dest_url, title, ..
            }) => {
                if let Some(img) = match_image(&dest_url, images) {
                    let new_url = img.rel_path.clone().unwrap_or_else(|| img.filename.clone());
                    let new_alt = img
                        .description
                        .clone()
                        .unwrap_or_else(|| default_description(img));
                    let title_opt = if title.is_empty() {
                        None
                    } else {
                        Some(title.as_ref())
                    };
                    write_image_ref(&mut out, &new_alt, &new_url, title_opt);
                } else {
                    // Pass through original slice unchanged
                    out.push_str(&markdown[span.start..span.end]);
                }
            }
            _ => {
                // Non-image event: pass through original slice unchanged.
                // This preserves any source-level formatting differences
                // (escapes, line breaks) that pulldown-cmark would normalize.
                out.push_str(&markdown[span.start..span.end]);
            }
        }
        last_end = span.end;
    }
    // Trailing text after the last event.
    if last_end < markdown.len() {
        out.push_str(&markdown[last_end..]);
    }
    out
}

/// Match `dest_url` against an extracted image (exact filename, exact rel_path,
/// or rel_path ending with the url — preserving the original three-tier
/// fallback from the hand-written scanner).
fn match_image<'a>(url: &str, images: &'a [ImageRef]) -> Option<&'a ImageRef> {
    images.iter().find(|img| {
        img.filename == url
            || img.rel_path.as_deref() == Some(url)
            || img.rel_path.as_deref().is_some_and(|p| p.ends_with(url))
    })
}

/// Serialize an image reference into `out`. Includes the optional title
/// (`"![alt](url \"title\")"`) so we don't lose the parser's view of it.
fn write_image_ref(out: &mut String, alt: &str, url: &str, title: Option<&str>) {
    out.push_str("![");
    out.push_str(alt);
    out.push_str("](");
    out.push_str(url);
    if let Some(t) = title {
        out.push_str(" \"");
        out.push_str(t);
        out.push('"');
    }
    out.push(')');
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
            let crop = d.crop_relpath.as_deref().unwrap_or("");
            // exact match
            crop == img_rel
                // cropped path is inside the extracted image
                || crop.ends_with(img_basename)
                // or the extracted image ends with the cropped path
                || img_rel.ends_with(crop)
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

/// Marker emitted at the start of each page section. Format mirrors
/// common OCR markdown conventions so external tools (pandoc, etc.)
/// also recognise it as a page break.
pub const PAGE_MARKER_PREFIX: &str = "<!-- page ";

/// Top-level entry point. Augments the markdown so every image
/// position has both a description and a working local link.
///
/// # Page-aware insertion
///
/// If `ocr_blocks` is `Some`, we attempt to split the markdown into
/// page sections (one per `OcrBlock.page`) by finding each block's
/// text content inside the markdown and inserting `<!-- page N -->`
/// markers. Images that aren't already referenced in the markdown are
/// then inserted at the end of their page section, not the global
/// appendix.
///
/// If `ocr_blocks` is `None`, or if we cannot derive page anchors
/// from them (e.g. text-based PDFs whose `OcrBlock.content` doesn't
/// match the MinerU/llama-parse markdown verbatim), we fall back to
/// the original behaviour: rewrite inline references and append
/// unreferenced images to a `## Extracted Images` section.
pub fn augment_markdown_with_images(
    markdown: &str,
    images: &[ImageRef],
    ocr_blocks: Option<&[OcrBlock]>,
) -> String {
    if images.is_empty() {
        return markdown.to_string();
    }

    // Pass 1: rewrite inline `![]()` references that point at extracted
    // images so the URL is the local path and the alt is a description.
    let rewritten = rewrite_inline_references(markdown, images);

    // Decide: page-aware mode or appendix mode?
    let (out, _unreferenced) = match ocr_blocks {
        Some(blocks) if has_text_blocks(blocks) => {
            insert_images_by_page(&rewritten, images, blocks)
        }
        _ => {
            // Fall back to the original "rewrite + appendix" behaviour.
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
            (out, unreferenced)
        }
    };
    out
}

fn has_text_blocks(blocks: &[OcrBlock]) -> bool {
    blocks.iter().any(|b| {
        b.block_type == "text" && b.content.as_deref().map(|s| !s.is_empty()).unwrap_or(false)
    })
}

/// Insert `<!-- page N -->` markers into the markdown by aligning each
/// text block's content with its first occurrence in the markdown, then
/// insert each unreferenced image at the end of its page section.
///
/// Returns the rewritten markdown. If alignment fails (no text block
/// matches), falls back to the un-sectioned markdown unchanged.
fn insert_images_by_page<'a>(
    markdown: &str,
    images: &'a [ImageRef],
    blocks: &'a [OcrBlock],
) -> (String, Vec<&'a ImageRef>) {
    // 1. Collect, per page, the text blocks in (page, index) order.
    //    Only blocks with non-empty text content can act as anchors.
    let mut by_page: std::collections::BTreeMap<usize, Vec<&OcrBlock>> =
        std::collections::BTreeMap::new();
    for b in blocks {
        if b.block_type != "text" {
            continue;
        }
        if b.content.as_deref().map(|s| s.is_empty()).unwrap_or(true) {
            continue;
        }
        by_page.entry(b.page).or_default().push(b);
    }
    if by_page.is_empty() {
        // Nothing to align on. Caller will fall back to appendix mode.
        let mut out = markdown.to_string();
        for img in images {
            let url = img.rel_path.as_deref().unwrap_or(&img.filename);
            if !out.contains(&format!("]({}", url)) && !out.contains(&format!("]({}", img.filename))
            {
                out.push_str(&build_appendix(&[img]));
            }
        }
        return (out, vec![]);
    }

    // 2. Find each (page, first-text-block-of-page) in the markdown
    //    and record the byte offset where the page section starts.
    //    We use the FIRST text block per page as the anchor — this is
    //    robust to OcrBlock noise (mid-page blocks may not align).
    let mut anchors: Vec<(usize, usize)> = Vec::new(); // (offset, page)
    for (page, mut blocks) in by_page {
        blocks.sort_by_key(|b| b.index);
        if let Some(first) = blocks.first() {
            if let Some(text) = first.content.as_deref() {
                if let Some(pos) = find_substring(markdown, text) {
                    anchors.push((pos, page));
                }
            }
        }
    }
    anchors.sort_by_key(|(pos, _)| *pos);

    // 3. Slice markdown into page sections at the anchor positions.
    //    A page section spans from its anchor (inclusive) to the next
    //    anchor (exclusive), or the end of the markdown.
    let mut sections: Vec<(usize, &str)> = Vec::new();
    for (i, (offset, page)) in anchors.iter().enumerate() {
        let start = *offset;
        let end = anchors
            .get(i + 1)
            .map(|(o, _)| *o)
            .unwrap_or(markdown.len());
        sections.push((*page, &markdown[start..end]));
    }

    // 4. For each image not already referenced in any section, insert
    //    it at the end of the section that corresponds to its page.
    //    Images whose page doesn't have a section get the appendix.
    let mut unreferenced: Vec<&ImageRef> = Vec::new();
    let mut out = String::with_capacity(markdown.len() + 256);
    for (i, (page, sec)) in sections.iter().enumerate() {
        if i == 0 {
            // Preserve any prefix the markdown had before page 1
            // (rare in practice, but handle gracefully).
            let first_anchor = anchors[0].0;
            out.push_str(&markdown[..first_anchor]);
        }
        // Emit the page marker BEFORE the section content.
        out.push_str(&format!("\n\n{}{} -->\n\n", PAGE_MARKER_PREFIX, page));
        out.push_str(sec);

        // Collect images for this page.
        let page_imgs: Vec<&ImageRef> = images
            .iter()
            .filter(|img| {
                img.page == *page
                    && !sec.contains(&format!(
                        "]({}",
                        img.rel_path.as_deref().unwrap_or(&img.filename)
                    ))
                    && !sec.contains(&format!("]({}", img.filename))
            })
            .collect();
        for img in &page_imgs {
            let url = img.rel_path.as_deref().unwrap_or(&img.filename);
            let desc = img
                .description
                .clone()
                .unwrap_or_else(|| default_description(img));
            out.push_str(&format!("\n![{}]({})\n", desc, url));
        }
    }
    // Track images that didn't make it into any section (page had no
    // anchor OR the page was outside the anchor map).
    let anchored_pages: std::collections::HashSet<usize> =
        sections.iter().map(|(p, _)| *p).collect();
    for img in images {
        let url = img.rel_path.as_deref().unwrap_or(&img.filename);
        let referenced =
            out.contains(&format!("]({}", url)) || out.contains(&format!("]({}", img.filename));
        if !referenced {
            unreferenced.push(img);
        }
        let _ = anchored_pages; // suppress unused warning if branch never taken
    }
    if !unreferenced.is_empty() {
        out.push_str(&build_appendix(&unreferenced));
    }
    (out, unreferenced)
}

/// Find the first occurrence of `needle` in `haystack`, returning the
/// byte offset. We try the full needle first, then progressively
/// shorter prefixes (so a block whose text was line-wrapped in the
/// markdown can still be located).
fn find_substring(haystack: &str, needle: &str) -> Option<usize> {
    if needle.is_empty() {
        return None;
    }
    if let Some(pos) = haystack.find(needle) {
        return Some(pos);
    }
    // Fallback: first 32 chars, then 16.
    let trimmed = needle.trim();
    for take in [32usize, 16].iter() {
        if trimmed.len() > *take {
            let prefix: String = trimmed.chars().take(*take).collect();
            if let Some(pos) = haystack.find(&prefix) {
                return Some(pos);
            }
        }
    }
    None
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
        assert_eq!(augment_markdown_with_images(md, &[], None), md);
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
        let out = augment_markdown_with_images(md, &images, None);
        assert!(out.contains("![Ethanol molecule diagram](media/doc-slug/img-001.png)"));
    }

    #[test]
    fn leaves_unrelated_inline_reference_alone() {
        // No images extracted at all → markdown passes through verbatim
        // (empty `images` short-circuits the early-return in the entry point).
        let md = "External: ![alt](https://example.com/photo.jpg) here.\n";
        let out = augment_markdown_with_images(md, &[], None);
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
        let out = augment_markdown_with_images(md, &images, None);
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
        let out = augment_markdown_with_images(md, &images, None);
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
        let out = augment_markdown_with_images(md, &images, None);
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
        let out = augment_markdown_with_images(md, &images, None);
        assert!(out.contains("Image extracted from page 7"));
    }
}
