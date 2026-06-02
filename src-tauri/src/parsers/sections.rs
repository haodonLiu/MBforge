/// Section 生成器 — 核心引擎
///
/// 输入: headings + full_text + page_texts
/// 输出: Vec<SectionChunk>（唯一数据单元）
///
/// SectionChunk 是向量索引、结构树、页码缓存的同源数据。
pub use crate::core::types::{SectionChunk, TreeNode};

use super::headings::Heading;

/// 核心引擎：headings + text + page_texts → sections
pub fn build_sections(
    text: &str,
    headings: &[Heading],
    page_texts: Option<&[String]>,
    max_chars: usize,
) -> Vec<SectionChunk> {
    if headings.is_empty() {
        // 无 heading → 全文作为一个 section
        let page_start = page_texts.and_then(|_pt| Some(1));
        let page_end = page_texts.map(|pt| pt.len());
        return vec![SectionChunk {
            title: "全文".to_string(),
            path: "全文".to_string(),
            text: text.to_string(),
            page_start,
            page_end,
            line_start: 0,
            line_end: text.lines().count(),
        }];
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
                let completed = stack.pop().expect("stack non-empty during tree build");
                if let Some(parent) = stack.last_mut() {
                    parent.nodes.push(completed);
                } else {
                    root_nodes.push(completed);
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
    let paragraphs: Vec<&str> = text.split("\n\n").collect();
    let mut parts = Vec::new();
    let mut current = String::new();

    for para in paragraphs {
        if current.len() + para.len() + 2 > max_chars && !current.is_empty() {
            parts.push(current);
            current = para.to_string();
        } else {
            if !current.is_empty() {
                current.push_str("\n\n");
            }
            current.push_str(para);
        }
    }
    if !current.is_empty() {
        parts.push(current);
    }

    // 如果单个段落仍超长，强制按字符切割
    let mut result = Vec::new();
    for part in parts {
        if part.len() > max_chars {
            for chunk in part.as_bytes().chunks(max_chars) {
                result.push(String::from_utf8_lossy(chunk).to_string());
            }
        } else {
            result.push(part);
        }
    }
    result
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
    use super::super::headings::extract_headings;
    use super::*;

    const DEFAULT_MAX_CHARS: usize = 8000;

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
}
