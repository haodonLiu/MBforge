//! Segmentation stage for the PDF processing pipeline.
//!
//! This stage turns an [`ExtractedDocument`] into a [`SegmentedDocument`] by:
//!
//! 1. Extracting Markdown headings from the raw text.
//! 2. Building contiguous [`SectionChunk`]s from headings or semantic boundaries.
//! 3. Constructing a hierarchical [`TreeNode`] document tree.

use std::sync::LazyLock;

use async_trait::async_trait;
use regex::Regex;
use text_splitter::{Characters, TextSplitter};

use crate::parsers::pipeline_v2::context::{PipelineContext, PipelineEvent};
use crate::parsers::pipeline_v2::error::PipelineError;
use crate::parsers::pipeline_v2::models::extracted::ExtractedDocument;
use crate::parsers::pipeline_v2::models::segmented::{
    Heading, SectionChunk, SegmentedDocument, TreeNode,
};
use crate::parsers::pipeline_v2::runner::{Stage, StageOutcome};

/// Semantic boundary keywords used to split text without explicit headings.
const SEMANTIC_BOUNDARY_PATTERNS: &[&str] = &[
    "figure",
    "fig.",
    "table",
    "example",
    "ex.",
    "step",
    "method",
    "results",
    "discussion",
    "conclusion",
    "introduction",
    "abstract",
    "experimental",
    "synthesis",
    "procedure",
    "materials",
    "apparatus",
    "background",
    "objective",
    "aim",
    "purpose",
    "图",
    "表",
    "示例",
    "步骤",
    "方法",
    "结果",
    "讨论",
    "结论",
    "引言",
    "摘要",
    "实验",
    "合成",
    "程序",
    "材料",
    "背景",
    "目的",
];

/// Regex matching Markdown headings (H1-H6).
static MD_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(#{1,6})\s+(.+)$").expect("valid md heading regex"));

/// Extracts all Markdown headings from `text`.
///
/// The input is expected to be normalized Markdown where headings use `#`
/// syntax. Headings are returned in reading order with their depth and line
/// number.
pub fn extract_headings(text: &str) -> Vec<Heading> {
    text.lines()
        .enumerate()
        .filter_map(|(i, line)| {
            let trimmed = line.trim();
            MD_RE.captures(trimmed).map(|caps| Heading {
                level: caps[1].len(),
                title: caps[2].trim().to_string(),
                line_num: i,
            })
        })
        .collect()
}

/// Builds [`SectionChunk`]s from raw text, headings and optional page text.
///
/// When no headings are present, the text is split using semantic boundaries.
/// Long sections are further split to respect `max_chars`.
pub fn build_sections(
    text: &str,
    headings: &[Heading],
    page_texts: Option<&[String]>,
    max_chars: usize,
) -> Vec<SectionChunk> {
    if headings.is_empty() {
        return build_semantic_sections(text, page_texts, max_chars);
    }

    let lines: Vec<&str> = text.lines().collect();
    let total_lines = lines.len();
    let mut sections = Vec::new();
    let mut path_stack: Vec<String> = Vec::new();

    for (i, heading) in headings.iter().enumerate() {
        let start_line = heading.line_num;
        let end_line = if i + 1 < headings.len() {
            headings[i + 1].line_num
        } else {
            total_lines
        };

        if start_line >= end_line {
            // Skip empty sections caused by duplicate heading line numbers.
            continue;
        }

        let section_text: String = lines[start_line..end_line].join("\n");
        update_path_stack(&mut path_stack, heading);

        let (page_start, page_end) = page_texts
            .map(|_pt| {
                let ps = line_to_page(start_line, &lines);
                let pe = line_to_page(end_line.saturating_sub(1), &lines);
                (ps, pe)
            })
            .unwrap_or((None, None));

        if section_text.len() > max_chars {
            let parts = split_long_section(&section_text, max_chars);
            for (j, part) in parts.iter().enumerate() {
                let part_title = if parts.len() > 1 {
                    format!("{} (part {})", heading.title, j + 1)
                } else {
                    heading.title.clone()
                };
                let part_path = if parts.len() > 1 {
                    format!("{} (part {})", path_stack.join(" > "), j + 1)
                } else {
                    path_stack.join(" > ")
                };
                sections.push(SectionChunk {
                    title: part_title,
                    path: part_path,
                    text: part.clone(),
                    page_start,
                    page_end,
                    line_start: start_line,
                    line_end: end_line,
                });
            }
        } else {
            sections.push(SectionChunk {
                title: heading.title.clone(),
                path: path_stack.join(" > "),
                text: section_text,
                page_start,
                page_end,
                line_start: start_line,
                line_end: end_line,
            });
        }
    }

    sections
}

/// Builds a hierarchical [`TreeNode`] tree from a flat list of sections.
///
/// The nesting level is derived from the section path, where each `>` separator
/// indicates one level of depth.
pub fn build_tree(sections: &[SectionChunk]) -> Vec<TreeNode> {
    let mut root_nodes: Vec<TreeNode> = Vec::new();
    let mut stack: Vec<TreeNode> = Vec::new();
    let mut level_stack: Vec<usize> = Vec::new();

    for (i, section) in sections.iter().enumerate() {
        let level = section.path.matches(" > ").count() + 1;
        let node = TreeNode {
            title: section.title.clone(),
            node_id: format!("node_{}", i),
            line_num: section.line_start,
            nodes: Vec::new(),
        };

        while let Some(&top_level) = level_stack.last() {
            if top_level >= level {
                if let Some(completed) = stack.pop() {
                    level_stack.pop();
                    if let Some(parent) = stack.last_mut() {
                        parent.nodes.push(completed);
                    } else {
                        root_nodes.push(completed);
                    }
                }
            } else {
                break;
            }
        }

        stack.push(node);
        level_stack.push(level);
    }

    while let Some(completed) = stack.pop() {
        level_stack.pop();
        if let Some(parent) = stack.last_mut() {
            parent.nodes.push(completed);
        } else {
            root_nodes.push(completed);
        }
    }

    root_nodes
}

/// Updates the path stack to reflect the current heading level.
fn update_path_stack(stack: &mut Vec<String>, heading: &Heading) {
    if heading.level <= stack.len() {
        stack.truncate(heading.level - 1);
    }
    stack.push(heading.title.clone());
}

/// Estimates the one-based page number for a given line.
fn line_to_page(line_num: usize, _lines: &[&str]) -> Option<usize> {
    // Simplified estimation: assume a fixed page length of 50 lines.
    Some(line_num / 50 + 1)
}

/// Splits a section that exceeds `max_chars` into smaller pieces.
///
/// First tries to split on semantic boundaries; falls back to a character-based
/// splitter and, as a last resort, to fixed-size byte chunks.
fn split_long_section(text: &str, max_chars: usize) -> Vec<String> {
    let semantic = split_semantic_chunks(text, max_chars);
    if semantic.len() > 1 {
        return semantic.into_iter().map(|(_, text)| text).collect();
    }

    TextSplitter::new(Characters)
        .chunks(text, max_chars)
        .map(|c: &str| c.to_string())
        .collect()
}

/// Detects whether a paragraph is a semantic boundary candidate.
fn is_semantic_boundary(para: &str) -> Option<String> {
    let trimmed = para.trim();
    if trimmed.len() > 120 {
        return None;
    }
    let lower = trimmed.to_lowercase();

    for pat in SEMANTIC_BOUNDARY_PATTERNS {
        let word_re = format!(r"^{}\b", regex::escape(pat));
        if let Ok(re) = Regex::new(&word_re) {
            if re.is_match(&lower) {
                return Some(trimmed.chars().take(60).collect());
            }
        }
    }

    if Regex::new(r"^\s*\d+[\.\)]\s+\w").ok()?.is_match(trimmed)
        || Regex::new(r"^\s*[\(\[]\d+[\)\]]\s+\w")
            .ok()?
            .is_match(trimmed)
    {
        return Some(trimmed.chars().take(60).collect());
    }

    None
}

/// Splits text into semantic chunks using paragraph boundaries and headings.
///
/// Returns `(title, text)` pairs. When no boundary is found, the whole text is
/// returned as a single chunk titled "全文".
fn split_semantic_chunks(text: &str, max_chars: usize) -> Vec<(String, String)> {
    let paragraphs: Vec<&str> = text.split("\n\n").collect();
    if paragraphs.len() <= 1 {
        return vec![("全文".to_string(), text.to_string())];
    }

    let mut chunks: Vec<(String, String)> = Vec::new();
    let mut current_title = "全文".to_string();
    let mut current_text = String::new();
    let total_len = text.len();
    let min_chunk_size = ((max_chars / 5).max(50)).min(total_len / 3).max(50);

    for para in &paragraphs {
        let boundary_title = is_semantic_boundary(para);

        if current_text.is_empty() {
            current_text = para.to_string();
            if let Some(ref t) = boundary_title {
                current_title = t.clone();
            }
            continue;
        }

        let should_split = boundary_title.is_some()
            && (current_text.len() >= min_chunk_size
                || current_text.len() + para.len() > max_chars);
        let would_overflow = current_text.len() + para.len() + 2 > max_chars;

        if should_split || would_overflow {
            chunks.push((current_title.clone(), current_text.clone()));
            current_text = para.to_string();
            current_title = boundary_title.unwrap_or_else(|| format!("Part {}", chunks.len() + 2));
        } else {
            current_text.push_str("\n\n");
            current_text.push_str(para);
        }
    }

    if !current_text.is_empty() {
        chunks.push((current_title, current_text));
    }

    if chunks.len() == 1 && chunks[0].1.len() > max_chars {
        let Some((_, text)) = chunks.into_iter().next() else {
            return Vec::new();
        };
        return text
            .as_bytes()
            .chunks(max_chars)
            .enumerate()
            .map(|(i, b)| {
                (
                    format!("Part {}", i + 1),
                    String::from_utf8_lossy(b).to_string(),
                )
            })
            .collect();
    }

    chunks
}

/// Builds sections for documents that contain no explicit headings.
fn build_semantic_sections(
    text: &str,
    page_texts: Option<&[String]>,
    max_chars: usize,
) -> Vec<SectionChunk> {
    let chunks = split_semantic_chunks(text, max_chars);
    let total_lines = text.lines().count();
    let page_start = page_texts.map(|_| 1);
    let page_end = page_texts.map(|pt| pt.len());

    chunks
        .into_iter()
        .enumerate()
        .map(|(i, (title, chunk_text))| SectionChunk {
            title,
            path: format!("Part {}", i + 1),
            text: chunk_text,
            page_start,
            page_end,
            line_start: 0,
            line_end: total_lines,
        })
        .collect()
}

/// Pipeline stage that segments an extracted document into sections and a tree.
pub struct SegmentStage {
    /// Maximum number of characters allowed per section chunk.
    pub max_chars: usize,
}

impl SegmentStage {
    /// Creates a new [`SegmentStage`] with the given chunk size limit.
    pub fn new(max_chars: usize) -> Self {
        Self { max_chars }
    }
}

#[async_trait]
impl Stage<ExtractedDocument, SegmentedDocument> for SegmentStage {
    async fn run(
        &self,
        input: ExtractedDocument,
        ctx: &PipelineContext,
    ) -> Result<StageOutcome<SegmentedDocument>, PipelineError> {
        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "segment".into(),
            message: "extracting headings".into(),
        });

        if input.raw_text.trim().is_empty() {
            return Ok(StageOutcome::new(SegmentedDocument {
                sections: Vec::new(),
                document_tree: Vec::new(),
                headings: Vec::new(),
            }));
        }

        let headings = extract_headings(&input.raw_text);
        let sections = build_sections(&input.raw_text, &headings, None, self.max_chars);
        let document_tree = build_tree(&sections);

        ctx.reporter.report(PipelineEvent::StageProgress {
            stage: "segment".into(),
            message: format!("built {} sections", sections.len()),
        });

        Ok(StageOutcome::new(SegmentedDocument {
            sections,
            document_tree,
            headings,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEFAULT_MAX_CHARS: usize = 8000;

    // ─── Heading tests (from headings.rs) ───

    #[test]
    fn test_heading_markdown() {
        let text = "# Title\nSome text\n## Section\n### Subsection\n#### H4\n##### H5\n###### H6";
        let headings = extract_headings(text);
        assert_eq!(headings.len(), 6);
        assert_eq!(headings[0].level, 1);
        assert_eq!(headings[0].title, "Title");
        assert_eq!(headings[5].level, 6);
        assert_eq!(headings[5].title, "H6");
    }

    #[test]
    fn test_no_headings() {
        let text = "This is just plain text without any headings.\nSecond line.";
        let headings = extract_headings(text);
        assert!(headings.is_empty());
    }

    // ─── Section tests ───

    #[test]
    fn test_build_sections_basic() {
        let text = "# Title\nSome intro.\n## Section A\nContent A.\n## Section B\nContent B.";
        let headings = extract_headings(text);
        let sections = build_sections(text, &headings, None, DEFAULT_MAX_CHARS);
        assert_eq!(sections.len(), 3); // Title + Section A + Section B
        assert_eq!(sections[0].title, "Title");
        assert_eq!(sections[1].title, "Section A");
        assert_eq!(sections[2].title, "Section B");
    }

    #[test]
    fn test_build_sections_no_headings() {
        let text = "Just plain text without any structure.";
        let sections = build_sections(text, &[], None, DEFAULT_MAX_CHARS);
        assert_eq!(sections.len(), 1);
        assert_eq!(sections[0].title, "全文");
    }

    #[test]
    fn test_build_sections_page_mapping() {
        let text = "# Title\nLine 1\nLine 2\n\n## Section\nMore content.";
        let headings = extract_headings(text);
        let page_texts = vec!["page 1 content".to_string(), "page 2 content".to_string()];
        let sections = build_sections(text, &headings, Some(&page_texts), DEFAULT_MAX_CHARS);
        assert!(sections[0].page_start.is_some());
    }

    #[test]
    fn test_build_tree() {
        let sections = vec![
            SectionChunk {
                title: "Title".into(),
                path: "Title".into(),
                text: "".into(),
                page_start: None,
                page_end: None,
                line_start: 0,
                line_end: 1,
            },
            SectionChunk {
                title: "Section A".into(),
                path: "Title > Section A".into(),
                text: "".into(),
                page_start: None,
                page_end: None,
                line_start: 2,
                line_end: 3,
            },
        ];
        let tree = build_tree(&sections);
        assert!(!tree.is_empty());
    }

    #[test]
    fn test_split_long_section() {
        let text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3.";
        let parts = split_long_section(text, 20);
        assert!(parts.len() > 1);
    }

    #[test]
    fn test_is_semantic_boundary() {
        assert!(is_semantic_boundary("Figure 1: Structure of compound A.").is_some());
        assert!(is_semantic_boundary("Table 1: Activity data.").is_some());
        assert!(is_semantic_boundary("Conclusion: The results show good activity.").is_some());
        assert!(is_semantic_boundary("1. Introduction").is_some());
        assert!(is_semantic_boundary("Just a normal paragraph.").is_none());
    }

    #[test]
    fn test_semantic_split_boundary_detection() {
        let text = "This is the introduction paragraph.\n\nFigure 1: Structure of compound A.\n\nSome description about the figure.\n\nTable 1: Activity data.\n\nIC50 values for various compounds.\n\nConclusion: The results show good activity.";
        let sections = build_sections(text, &[], None, 8000);
        // 应该按 Figure / Table / Conclusion 切分成多个 section
        assert!(
            sections.len() >= 2,
            "Expected at least 2 semantic sections, got {}",
            sections.len()
        );
        let titles: Vec<&str> = sections.iter().map(|s| s.title.as_str()).collect();
        assert!(titles
            .iter()
            .any(|t| t.contains("Figure") || t.contains("Table") || t.contains("Conclusion")));
    }

    #[test]
    fn test_semantic_split_no_boundary_fallback() {
        let text = "Just plain text without any structure. It keeps going and going.";
        let sections = build_sections(text, &[], None, 8000);
        assert_eq!(sections.len(), 1);
        assert_eq!(sections[0].title, "全文");
    }

    #[test]
    fn test_semantic_split_max_chars_force() {
        // 构造一个很长的文本，中间没有语义边界，超过 max_chars
        let text = (0..100)
            .map(|i| format!("Paragraph {} with some content.", i))
            .collect::<Vec<_>>()
            .join("\n\n");
        let sections = build_sections(&text, &[], None, 500);
        // 无边界但超过 500 字符，应该被硬切分
        assert!(
            sections.len() >= 2,
            "Expected forced split due to max_chars, got {}",
            sections.len()
        );
    }

    #[tokio::test]
    async fn test_segment_stage_splits_by_headings() {
        use std::path::Path;

        use crate::parsers::pipeline_v2::context::PipelineContext;
        use crate::parsers::pipeline_v2::models::extracted::ExtractedMetadata;

        let extracted = ExtractedDocument {
            raw_text: "# Title\n\nIntro.\n## Section A\nContent A.\n## Section B\nContent B."
                .into(),
            page_count: 1,
            parser: "test".into(),
            images: Vec::new(),
            ocr_blocks: Vec::new(),
            metadata: ExtractedMetadata::default(),
        };

        let ctx = PipelineContext::new(Path::new("dummy.pdf"), "");
        let stage = SegmentStage::new(8000);
        let outcome = stage.run(extracted, &ctx).await.unwrap();

        assert_eq!(outcome.output.sections.len(), 3);
        assert_eq!(outcome.output.sections[0].title, "Title");
        assert_eq!(outcome.output.sections[1].title, "Section A");
        assert!(!outcome.output.document_tree.is_empty());
    }
}
