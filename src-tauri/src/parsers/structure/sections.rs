/// Section 生成器 — 核心引擎（含 Heading 提取）
///
/// 输入: full_text + page_texts
/// 输出: Vec<SectionChunk>（唯一数据单元）
///
/// SectionChunk 是向量索引、结构树、页码缓存的同源数据。
pub use crate::core::types::{Heading, SectionChunk, TreeNode};

use regex::Regex;
use std::sync::LazyLock;

// ─── Heading 提取（原 headings.rs）────────────────────────────────

// 策略 A: Markdown # heading (最高优先级)
static MD_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(#{1,6})\s+(.+)$").expect("valid md heading regex"));
static UPPER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*([A-Z][A-Z\s]{2,})\s*$").expect("valid upper heading regex"));
static COLON_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^([A-Z][\w\s]+):\s*$").expect("valid colon heading regex"));
static NUM_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^(\d+)\.\s+([A-Z].+)$").expect("valid num heading regex"));

/// 从文本中提取所有 heading
///
/// 支持：
/// - 策略 A: Markdown `#` heading
/// - 策略 B: 全大写行 + 前后空行（专利格式：ABSTRACT, CLAIMS）
/// - 策略 C: 冒号终止行（"Field of Invention:"）
/// - 策略 D: 数字编号 + 大写开头（"1. Technical Field"）
pub fn extract_headings(text: &str) -> Vec<Heading> {
    let mut headings = Vec::new();
    let lines: Vec<&str> = text.lines().collect();

    for (i, line) in lines.iter().enumerate() {
        let trimmed = line.trim();

        // 策略 A: Markdown
        if let Some(caps) = MD_RE.captures(trimmed) {
            let level = caps[1].len();
            let title = caps[2].trim().to_string();
            headings.push(Heading {
                level,
                title,
                line_num: i,
            });
            continue;
        }

        // 策略 B: 全大写行（需要前后空行或首尾）
        if let Some(caps) = UPPER_RE.captures(trimmed) {
            let title = caps[1].trim().to_string();
            let prev_empty = i == 0 || lines[i - 1].trim().is_empty();
            let next_empty = i + 1 >= lines.len() || lines[i + 1].trim().is_empty();
            if prev_empty && next_empty && title.len() >= 3 {
                headings.push(Heading {
                    level: 1,
                    title,
                    line_num: i,
                });
                continue;
            }
        }

        // 策略 C: 冒号终止
        if let Some(caps) = COLON_RE.captures(trimmed) {
            let title = caps[1].trim().to_string();
            if title.len() >= 5 && title.len() <= 60 {
                headings.push(Heading {
                    level: 2,
                    title,
                    line_num: i,
                });
                continue;
            }
        }

        // 策略 D: 数字编号
        if let Some(caps) = NUM_RE.captures(trimmed) {
            let title = format!("{}. {}", &caps[1], caps[2].trim());
            headings.push(Heading {
                level: 2,
                title,
                line_num: i,
            });
        }
    }

    headings
}

/// 核心引擎：headings + text + page_texts → sections
pub fn build_sections(
    text: &str,
    headings: &[Heading],
    page_texts: Option<&[String]>,
    max_chars: usize,
) -> Vec<SectionChunk> {
    if headings.is_empty() {
        // 无 heading → 使用语义分块
        return build_semantic_sections(text, page_texts, max_chars);
    }

    let lines: Vec<&str> = text.lines().collect();
    let total_lines = lines.len();
    let mut sections = Vec::new();
    let mut path_stack: Vec<String> = Vec::new();

    for (i, heading) in headings.iter().enumerate() {
        // 确定 section 的文本范围
        let start_line = heading.line_num;
        let end_line = if i + 1 < headings.len() {
            headings[i + 1].line_num
        } else {
            total_lines
        };

        // 提取 section 文本
        if start_line >= end_line {
            // skip empty section (duplicate heading line_num)
            continue;
        }
        let section_text: String = lines[start_line..end_line].join("\n");

        // 更新 path stack
        update_path_stack(&mut path_stack, heading);

        // 计算 page 范围
        let (page_start, page_end) = page_texts
            .map(|_pt| {
                let ps = line_to_page(start_line, &lines);
                let pe = line_to_page(end_line.saturating_sub(1), &lines);
                (ps, pe)
            })
            .unwrap_or((None, None));

        // 如果 section 太长，拆分
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

/// 构建结构树
pub fn build_tree(sections: &[SectionChunk]) -> Vec<TreeNode> {
    let mut root_nodes: Vec<TreeNode> = Vec::new();
    let mut stack: Vec<TreeNode> = Vec::new();

    for (i, section) in sections.iter().enumerate() {
        let level = section.path.matches(" > ").count() + 1;
        let node = TreeNode {
            title: section.title.clone(),
            node_id: format!("node_{}", i),
            line_num: section.line_start,
            nodes: Vec::new(),
        };

        // 弹出同级或更低级别的节点
        while let Some(top) = stack.last() {
            let top_level = top.path_level();
            if top_level >= level {
                if let Some(completed) = stack.pop() {
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
    }

    // 弹出剩余节点
    while let Some(completed) = stack.pop() {
        if let Some(parent) = stack.last_mut() {
            parent.nodes.push(completed);
        } else {
            root_nodes.push(completed);
        }
    }

    root_nodes
}

// ---- 内部辅助 ----

fn update_path_stack(stack: &mut Vec<String>, heading: &Heading) {
    // 简化策略：根据 level 调整 stack
    // level 1 = push, level 2+ = 替换末尾或 push
    if heading.level <= stack.len() {
        stack.truncate(heading.level - 1);
    }
    stack.push(heading.title.clone());
}

fn line_to_page(line_num: usize, _lines: &[&str]) -> Option<usize> {
    // 通过分页标记（如 "\f" 或连续空行）估算页码
    // 简化实现：每 50 行一页
    Some(line_num / 50 + 1)
}

fn split_long_section(text: &str, max_chars: usize) -> Vec<String> {
    // 优先使用语义分块，回退时使用 `text-splitter` 按字符切分。
    let semantic = split_semantic_chunks(text, max_chars);
    if semantic.len() > 1 {
        return semantic.into_iter().map(|(_, text)| text).collect();
    }

    // Fallback: `text-splitter` 的默认 `TextSplitter` 是 recursive char-based
    // 切分（段落 → 句子 → 单词），自动处理单段超长场景。
    use text_splitter::{Characters, TextSplitter};
    TextSplitter::new(Characters)
        .chunks(text, max_chars)
        .map(|c: &str| c.to_string())
        .collect()
}

/// 语义边界检测关键词（中英文）
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

/// 检测段落是否是语义边界
fn is_semantic_boundary(para: &str) -> Option<String> {
    let trimmed = para.trim();
    if trimmed.len() > 120 {
        // 太长的段落不太可能是标题/边界
        return None;
    }
    let lower = trimmed.to_lowercase();

    // 1. 检查是否以边界词开头（作为独立单词，允许后面跟数字和标点）
    for pat in SEMANTIC_BOUNDARY_PATTERNS {
        let word_re = format!(r"^{}\b", regex::escape(pat));
        if let Ok(re) = Regex::new(&word_re) {
            if re.is_match(&lower) {
                return Some(trimmed.chars().take(60).collect());
            }
        }
    }

    // 2. 纯数字编号行（如 "1. Introduction", "(a) Method"）也视为弱边界
    if Regex::new(r"^\s*\d+[\.\)]\s+\w").ok()?.is_match(trimmed)
        || Regex::new(r"^\s*[(\[]\d+[)\]]\s+\w")
            .ok()?
            .is_match(trimmed)
    {
        return Some(trimmed.chars().take(60).collect());
    }
    None
}

/// 语义分块核心算法
///
/// 返回 Vec<(title, text)>，优先在语义边界处切分。
fn split_semantic_chunks(text: &str, max_chars: usize) -> Vec<(String, String)> {
    let paragraphs: Vec<&str> = text.split("\n\n").collect();
    if paragraphs.len() <= 1 {
        return vec![("全文".to_string(), text.to_string())];
    }

    let mut chunks: Vec<(String, String)> = Vec::new();
    let mut current_title = "全文".to_string();
    let mut current_text = String::new();
    let total_len = text.len();
    // 短文档（< max_chars）时，语义边界切分阈值低（50 字符）；
    // 长文档时，阈值随 max_chars 增长，但不超过总长的 1/3。
    let min_chunk_size = ((max_chars / 5).max(50)).min(total_len / 3).max(50);

    for para in &paragraphs {
        let boundary_title = is_semantic_boundary(para);

        // 如果当前 chunk 为空，直接开始
        if current_text.is_empty() {
            current_text = para.to_string();
            if let Some(ref t) = boundary_title {
                current_title = t.clone();
            }
            continue;
        }

        // 遇到语义边界且当前 chunk 已足够大 → 切分
        let should_split = boundary_title.is_some()
            && (current_text.len() >= min_chunk_size
                || current_text.len() + para.len() > max_chars);

        // 或者即将超出 max_chars → 强制切分
        let would_overflow = current_text.len() + para.len() + 2 > max_chars;

        if should_split || would_overflow {
            if !current_text.is_empty() {
                chunks.push((current_title.clone(), current_text.clone()));
            }
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

    // 如果只有一个 chunk 且超过了 max_chars，回退到硬切分
    if chunks.len() == 1 && chunks[0].1.len() > max_chars {
        return chunks
            .into_iter()
            .next()
            .map(|(_, text)| {
                text.as_bytes()
                    .chunks(max_chars)
                    .enumerate()
                    .map(|(i, b)| {
                        (
                            format!("Part {}", i + 1),
                            String::from_utf8_lossy(b).to_string(),
                        )
                    })
                    .collect()
            })
            .unwrap_or_default();
    }

    chunks
}

/// 无 heading 文档的语义分块入口
fn build_semantic_sections(
    text: &str,
    page_texts: Option<&[String]>,
    max_chars: usize,
) -> Vec<SectionChunk> {
    let chunks = split_semantic_chunks(text, max_chars);
    let total_lines = text.lines().count();
    let page_start = page_texts.and_then(|_pt| Some(1));
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

impl TreeNode {
    fn path_level(&self) -> usize {
        // 通过节点在树中的深度估算 level
        // 简化：用 title 中的数字前缀判断
        if let Some(num) = self.title.split('.').next() {
            if num.parse::<usize>().is_ok() {
                return num.parse::<usize>().unwrap_or(1);
            }
        }
        1
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const DEFAULT_MAX_CHARS: usize = 8000;

    // ─── Heading tests (from headings.rs) ───

    #[test]
    fn test_heading_markdown() {
        let text = "# Title\nSome text\n## Section\nMore text";
        let headings = extract_headings(text);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].level, 1);
        assert_eq!(headings[0].title, "Title");
        assert_eq!(headings[1].level, 2);
        assert_eq!(headings[1].title, "Section");
    }

    #[test]
    fn test_heading_patent_uppercase() {
        let text = "Some intro text.\n\nABSTRACT\n\nThis invention relates to...";
        let headings = extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "ABSTRACT"));
    }

    #[test]
    fn test_heading_colon_terminated() {
        let text = "Background\n\nField of Invention:\nThis invention relates to...";
        let headings = extract_headings(text);
        assert!(headings.iter().any(|h| h.title == "Field of Invention"));
    }

    #[test]
    fn test_heading_numbered() {
        let text = "1. Technical Field\nSome text\n2. Background\nMore text";
        let headings = extract_headings(text);
        assert_eq!(headings.len(), 2);
        assert_eq!(headings[0].title, "1. Technical Field");
        assert_eq!(headings[1].title, "2. Background");
    }

    #[test]
    fn test_heading_mixed() {
        let text = "# Patent Application\n\nABSTRACT\n\nThis invention...\n\n1. Field of Invention\nDetailed description.";
        let headings = extract_headings(text);
        assert!(headings.len() >= 2);
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
}
